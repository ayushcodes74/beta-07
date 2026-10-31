"""Supabase repository for public.course_messages (see phase3c_course_messages.sql).

All calls run under the caller's JWT, so RLS limits students to their own thread in courses they
are enrolled in, and teachers to threads in their own courses with enrolled students.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any, Optional, Protocol
from uuid import UUID

from app.database.supabase import get_user_supabase
from app.schemas.message import MessageResponse

logger = logging.getLogger(__name__)

_COLUMNS = "id, course_id, student_id, sender_id, body, read_at, created_at"


class MessageRepositoryError(Exception):
    """Storage failure (including phase3c_course_messages.sql not applied yet)."""


class MessageRepository(Protocol):
    def list_thread(
        self,
        course_id: UUID,
        student_id: UUID,
        *,
        after: Optional[datetime],
        limit: int,
        access_token: str,
    ) -> list[MessageResponse]: ...

    def create(
        self, course_id: UUID, student_id: UUID, sender_id: UUID, body: str, *, access_token: str
    ) -> MessageResponse: ...

    def mark_read(self, course_id: UUID, student_id: UUID, reader_id: UUID, *, access_token: str) -> int: ...

    def list_threads(self, *, access_token: str) -> list[dict[str, Any]]: ...


class SupabaseMessageRepository:
    def list_thread(
        self,
        course_id: UUID,
        student_id: UUID,
        *,
        after: Optional[datetime],
        limit: int,
        access_token: str,
    ) -> list[MessageResponse]:
        client = get_user_supabase(access_token)
        try:
            query = (
                client.table("course_messages")
                .select(_COLUMNS)
                .eq("course_id", str(course_id))
                .eq("student_id", str(student_id))
            )
            if after is not None:
                query = query.gt("created_at", after.isoformat())
            # Newest first so the limit keeps the most recent messages; reversed below.
            resp = query.order("created_at", desc=True).order("id", desc=True).limit(limit).execute()
        except Exception as exc:
            logger.exception("Failed to read messages: %s", exc)
            raise MessageRepositoryError("Failed to read messages") from exc
        rows = [MessageResponse.model_validate(row) for row in (resp.data or [])]
        rows.reverse()
        return rows

    def create(
        self, course_id: UUID, student_id: UUID, sender_id: UUID, body: str, *, access_token: str
    ) -> MessageResponse:
        client = get_user_supabase(access_token)
        # Only these four columns are insertable (column grants).
        payload = {
            "course_id": str(course_id),
            "student_id": str(student_id),
            "sender_id": str(sender_id),
            "body": body,
        }
        try:
            resp = client.table("course_messages").insert(payload).execute()
        except Exception as exc:
            logger.exception("Failed to send message: %s", exc)
            raise MessageRepositoryError("Failed to send message") from exc
        rows = resp.data or []
        if not rows:
            raise MessageRepositoryError("Message insert returned no row (check RLS)")
        return MessageResponse.model_validate(rows[0])

    def mark_read(self, course_id: UUID, student_id: UUID, reader_id: UUID, *, access_token: str) -> int:
        client = get_user_supabase(access_token)
        try:
            resp = (
                client.table("course_messages")
                .update({"read_at": datetime.now(UTC).isoformat()})
                .eq("course_id", str(course_id))
                .eq("student_id", str(student_id))
                .neq("sender_id", str(reader_id))
                .is_("read_at", "null")
                .execute()
            )
        except Exception as exc:
            logger.exception("Failed to mark messages read: %s", exc)
            raise MessageRepositoryError("Failed to update messages") from exc
        return len(resp.data or [])

    def list_threads(self, *, access_token: str) -> list[dict[str, Any]]:
        try:
            client = get_user_supabase(access_token)
            resp = client.rpc("course_message_threads", {}).execute()
        except Exception as exc:
            logger.error("course_message_threads RPC failed: %s", exc)
            raise MessageRepositoryError("Failed to read conversations") from exc
        return list(resp.data or [])
