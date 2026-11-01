"""Assignment question attachments: rows in public.assignment_attachments + files in Supabase Storage.

Everything runs under the caller's JWT, so the RLS policies in phase3e_assignment_attachments.sql decide
access (owning teacher manages; enrolled students read published assignments). Storage is called through
its REST API with the user's token because the shared supabase-py client only forwards the user's JWT to
PostgREST, not to Storage.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Optional, Protocol
from urllib.parse import quote
from uuid import UUID

import httpx

from app.core.config import settings
from app.database.supabase import get_user_supabase
from app.schemas.attachment import AttachmentRecord

logger = logging.getLogger(__name__)

BUCKET = "assignment-files"
SIGNED_URL_SECONDS = 15 * 60
_COLUMNS = (
    "id, assignment_id, question_number, storage_path, filename, content_type, size_bytes, "
    "extraction_status, extracted_text, extraction_error, uploaded_by, created_at"
)


class AttachmentRepositoryError(Exception):
    """Storage failure (including phase3e_assignment_attachments.sql not applied yet)."""


class AttachmentRepository(Protocol):
    def upload_file(self, path: str, data: bytes, content_type: str, *, access_token: str) -> None: ...
    def delete_file(self, path: str, *, access_token: str) -> None: ...
    def signed_urls(self, paths: list[str], *, access_token: str) -> dict[str, str]: ...
    def download_file(self, path: str, *, access_token: str) -> bytes: ...
    def insert(self, record: dict, *, access_token: str) -> AttachmentRecord: ...
    def get(self, attachment_id: UUID, *, access_token: str) -> Optional[AttachmentRecord]: ...
    def list_for_assignment(self, assignment_id: UUID, *, access_token: str) -> list[AttachmentRecord]: ...
    def set_extraction(
        self, attachment_id: UUID, status: str, text: Optional[str], error: Optional[str], *, access_token: str
    ) -> None: ...
    def delete(self, attachment_id: UUID, *, access_token: str) -> None: ...


class SupabaseAttachmentRepository:
    def __init__(self, transport: Optional[httpx.BaseTransport] = None) -> None:
        self._transport = transport

    # ---- Storage (REST, user's JWT) --------------------------------------------------------

    def _storage(self, access_token: str) -> httpx.Client:
        base = (settings.SUPABASE_URL or "").rstrip("/")
        if not base or not settings.SUPABASE_KEY:
            raise AttachmentRepositoryError("Supabase is not configured")
        return httpx.Client(
            base_url=f"{base}/storage/v1",
            headers={"apikey": settings.SUPABASE_KEY, "Authorization": f"Bearer {access_token}"},
            timeout=60.0,
            transport=self._transport,
        )

    @staticmethod
    def _check(response: httpx.Response, action: str) -> None:
        if response.status_code >= 400:
            logger.error("Storage %s failed (%s): %s", action, response.status_code, response.text[:200])
            raise AttachmentRepositoryError(f"Storage {action} failed ({response.status_code})")

    def upload_file(self, path: str, data: bytes, content_type: str, *, access_token: str) -> None:
        try:
            with self._storage(access_token) as client:
                response = client.post(
                    f"/object/{BUCKET}/{quote(path)}",
                    content=data,
                    headers={"Content-Type": content_type, "x-upsert": "false"},
                )
        except httpx.HTTPError as exc:
            raise AttachmentRepositoryError("Storage upload failed") from exc
        self._check(response, "upload")

    def delete_file(self, path: str, *, access_token: str) -> None:
        try:
            with self._storage(access_token) as client:
                response = client.request("DELETE", f"/object/{BUCKET}", json={"prefixes": [path]})
        except httpx.HTTPError as exc:
            raise AttachmentRepositoryError("Storage delete failed") from exc
        self._check(response, "delete")

    def signed_urls(self, paths: list[str], *, access_token: str) -> dict[str, str]:
        """path -> absolute signed URL (only for files the caller may read; others are omitted)."""
        if not paths:
            return {}
        try:
            with self._storage(access_token) as client:
                response = client.post(
                    f"/object/sign/{BUCKET}", json={"expiresIn": SIGNED_URL_SECONDS, "paths": paths}
                )
        except httpx.HTTPError as exc:
            raise AttachmentRepositoryError("Storage signing failed") from exc
        self._check(response, "sign")
        base = f"{(settings.SUPABASE_URL or '').rstrip('/')}/storage/v1"
        urls = {}
        for item in response.json() or []:
            signed = item.get("signedURL") or item.get("signedUrl")
            if item.get("path") and signed and not item.get("error"):
                urls[item["path"]] = signed if signed.startswith("http") else f"{base}{signed}"
        return urls

    def download_file(self, path: str, *, access_token: str) -> bytes:
        try:
            with self._storage(access_token) as client:
                response = client.get(f"/object/authenticated/{BUCKET}/{quote(path)}")
        except httpx.HTTPError as exc:
            raise AttachmentRepositoryError("Storage download failed") from exc
        self._check(response, "download")
        return response.content

    # ---- Rows (PostgREST, user's JWT) -------------------------------------------------------

    def insert(self, record: dict, *, access_token: str) -> AttachmentRecord:
        try:
            resp = get_user_supabase(access_token).table("assignment_attachments").insert(record).execute()
        except Exception as exc:
            logger.exception("Failed to save attachment: %s", exc)
            raise AttachmentRepositoryError("Failed to save attachment") from exc
        rows = resp.data or []
        if not rows:
            raise AttachmentRepositoryError("Attachment insert returned no row (check RLS)")
        return AttachmentRecord.model_validate(rows[0])

    def get(self, attachment_id: UUID, *, access_token: str) -> Optional[AttachmentRecord]:
        rows = self._select(access_token, lambda q: q.eq("id", str(attachment_id)))
        return rows[0] if rows else None

    def list_for_assignment(self, assignment_id: UUID, *, access_token: str) -> list[AttachmentRecord]:
        return self._select(access_token, lambda q: q.eq("assignment_id", str(assignment_id)))

    def set_extraction(
        self, attachment_id: UUID, status: str, text: Optional[str], error: Optional[str], *, access_token: str
    ) -> None:
        payload = {
            "extraction_status": status,
            "extracted_text": text,
            "extraction_error": error,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        try:
            get_user_supabase(access_token).table("assignment_attachments").update(payload).eq(
                "id", str(attachment_id)
            ).execute()
        except Exception as exc:
            logger.exception("Failed to store attachment text: %s", exc)
            raise AttachmentRepositoryError("Failed to update attachment") from exc

    def set_question_number(self, attachment_id: UUID, question_number: int, *, access_token: str) -> None:
        try:
            get_user_supabase(access_token).table("assignment_attachments").update(
                {"question_number": question_number, "updated_at": datetime.now(UTC).isoformat()}
            ).eq("id", str(attachment_id)).execute()
        except Exception as exc:
            logger.exception("Failed to move attachment: %s", exc)
            raise AttachmentRepositoryError("Failed to update attachment") from exc

    def delete(self, attachment_id: UUID, *, access_token: str) -> None:
        try:
            get_user_supabase(access_token).table("assignment_attachments").delete().eq(
                "id", str(attachment_id)
            ).execute()
        except Exception as exc:
            logger.exception("Failed to delete attachment: %s", exc)
            raise AttachmentRepositoryError("Failed to delete attachment") from exc

    @staticmethod
    def _select(access_token: str, where) -> list[AttachmentRecord]:
        try:
            query = get_user_supabase(access_token).table("assignment_attachments").select(_COLUMNS)
            resp = where(query).order("question_number").order("created_at").execute()
        except Exception as exc:
            logger.exception("Failed to read attachments: %s", exc)
            raise AttachmentRepositoryError("Failed to read attachments") from exc
        return [AttachmentRecord.model_validate(row) for row in (resp.data or [])]
