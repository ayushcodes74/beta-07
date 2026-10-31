"""Supabase repository for public.review_requests (see phase3a_review_requests.sql).

All calls run under the caller's JWT, so RLS limits students to their own requests and
teachers to requests on submissions to their own assignments.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any, Optional, Protocol
from uuid import UUID

from app.database.supabase import get_user_supabase
from app.schemas.review import ReviewRequestResponse, ReviewRequestStatus

logger = logging.getLogger(__name__)

_COLUMNS = (
    "id, submission_id, student_id, reason, status, teacher_response, "
    "resolved_by, resolved_at, created_at, updated_at"
)


class ReviewRequestRepositoryError(Exception):
    """Storage failure (including a missing review_requests table)."""


class DuplicateOpenReviewRequestError(ReviewRequestRepositoryError):
    """The submission already has an open review request."""


class ReviewRequestRepository(Protocol):
    def create(
        self, submission_id: UUID, student_id: UUID, reason: str, *, access_token: str
    ) -> ReviewRequestResponse: ...

    def get(self, request_id: UUID, *, access_token: str) -> Optional[ReviewRequestResponse]: ...

    def list_by_submission_ids(
        self, submission_ids: list[UUID], *, access_token: str
    ) -> list[ReviewRequestResponse]: ...

    def list_by_student(self, student_id: UUID, *, access_token: str) -> list[ReviewRequestResponse]: ...

    def resolve(
        self,
        request_id: UUID,
        status: ReviewRequestStatus,
        teacher_response: Optional[str],
        resolved_by: UUID,
        *,
        access_token: str,
    ) -> Optional[ReviewRequestResponse]: ...


def _is_unique_violation(exc: Exception) -> bool:
    text = str(exc)
    return "23505" in text or "duplicate key" in text.lower()


class SupabaseReviewRequestRepository:
    def create(
        self, submission_id: UUID, student_id: UUID, reason: str, *, access_token: str
    ) -> ReviewRequestResponse:
        client = get_user_supabase(access_token)
        # Only these three columns are insertable (column grants); status defaults to 'open'.
        payload = {"submission_id": str(submission_id), "student_id": str(student_id), "reason": reason}
        try:
            resp = client.table("review_requests").insert(payload).execute()
        except Exception as exc:
            if _is_unique_violation(exc):
                raise DuplicateOpenReviewRequestError("An open review request already exists") from exc
            logger.exception("Failed to create review request: %s", exc)
            raise ReviewRequestRepositoryError("Failed to create review request") from exc
        rows = resp.data or []
        if not rows:
            raise ReviewRequestRepositoryError("Review request insert returned no row (check RLS)")
        return ReviewRequestResponse.model_validate(rows[0])

    def get(self, request_id: UUID, *, access_token: str) -> Optional[ReviewRequestResponse]:
        rows = self._select(access_token, lambda q: q.eq("id", str(request_id)))
        return rows[0] if rows else None

    def list_by_submission_ids(
        self, submission_ids: list[UUID], *, access_token: str
    ) -> list[ReviewRequestResponse]:
        if not submission_ids:
            return []
        ids = [str(i) for i in submission_ids]
        return self._select(access_token, lambda q: q.in_("submission_id", ids))

    def list_by_student(self, student_id: UUID, *, access_token: str) -> list[ReviewRequestResponse]:
        return self._select(access_token, lambda q: q.eq("student_id", str(student_id)))

    def resolve(
        self,
        request_id: UUID,
        status: ReviewRequestStatus,
        teacher_response: Optional[str],
        resolved_by: UUID,
        *,
        access_token: str,
    ) -> Optional[ReviewRequestResponse]:
        client = get_user_supabase(access_token)
        now = datetime.now(UTC).isoformat()
        payload = {
            "status": status.value,
            "teacher_response": teacher_response,
            "resolved_by": str(resolved_by),
            "resolved_at": now,
            "updated_at": now,
        }
        try:
            resp = (
                client.table("review_requests")
                .update(payload)
                .eq("id", str(request_id))
                .eq("status", ReviewRequestStatus.OPEN.value)
                .execute()
            )
        except Exception as exc:
            logger.exception("Failed to resolve review request: %s", exc)
            raise ReviewRequestRepositoryError("Failed to update review request") from exc
        rows = resp.data or []
        return ReviewRequestResponse.model_validate(rows[0]) if rows else None

    @staticmethod
    def _select(access_token: str, where: Any) -> list[ReviewRequestResponse]:
        client = get_user_supabase(access_token)
        try:
            query = client.table("review_requests").select(_COLUMNS)
            resp = where(query).order("created_at", desc=False).execute()
        except Exception as exc:
            logger.exception("Failed to read review requests: %s", exc)
            raise ReviewRequestRepositoryError("Failed to read review requests") from exc
        return [ReviewRequestResponse.model_validate(row) for row in (resp.data or [])]
