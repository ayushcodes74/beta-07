"""Supabase repository for public.notifications (see phase3d_notifications.sql).

Every call runs under the caller's JWT:
  - reads / mark-read: RLS limits the caller to notifications addressed to them
  - inserts: RLS only lets the caller (the actor) notify users they share a course or
    submission with. Inserts use ``returning=minimal`` because the actor cannot SELECT
    a row addressed to somebody else.
The lookup helpers read assignments / submissions / enrollments the caller can already see.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any, Optional, Protocol
from uuid import UUID

from postgrest import CountMethod, ReturnMethod

from app.database.supabase import get_user_supabase
from app.schemas.notification import NotificationResponse

logger = logging.getLogger(__name__)

_COLUMNS = "id, type, title, body, link, actor_id, assignment_id, submission_id, read_at, created_at"


class NotificationRepositoryError(Exception):
    """Storage failure (including a missing notifications table)."""


class NotificationRepository(Protocol):
    def insert_many(self, rows: list[dict[str, Any]], *, access_token: str) -> None: ...

    def list_for_recipient(
        self, recipient_id: UUID, limit: int, *, access_token: str
    ) -> list[NotificationResponse]: ...

    def count_unread(self, recipient_id: UUID, *, access_token: str) -> int: ...

    def mark_read(self, recipient_id: UUID, ids: Optional[list[UUID]], *, access_token: str) -> None: ...

    def active_student_ids(self, course_ids: list[UUID], *, access_token: str) -> list[UUID]: ...

    def course_ids_for_teacher(self, teacher_id: UUID, *, access_token: str) -> list[UUID]: ...

    def assignment_info(self, assignment_id: UUID, *, access_token: str) -> Optional[dict[str, Any]]: ...

    def submission_info(self, submission_id: UUID, *, access_token: str) -> Optional[dict[str, Any]]: ...


class SupabaseNotificationRepository:
    def insert_many(self, rows: list[dict[str, Any]], *, access_token: str) -> None:
        if not rows:
            return
        client = get_user_supabase(access_token)
        try:
            client.table("notifications").insert(rows, returning=ReturnMethod.minimal).execute()
        except Exception as exc:
            raise NotificationRepositoryError(f"Failed to create notifications: {exc}") from exc

    def list_for_recipient(
        self, recipient_id: UUID, limit: int, *, access_token: str
    ) -> list[NotificationResponse]:
        client = get_user_supabase(access_token)
        try:
            resp = (
                client.table("notifications")
                .select(_COLUMNS)
                .eq("recipient_id", str(recipient_id))
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            raise NotificationRepositoryError(f"Failed to read notifications: {exc}") from exc
        return [NotificationResponse.model_validate(row) for row in (resp.data or [])]

    def count_unread(self, recipient_id: UUID, *, access_token: str) -> int:
        client = get_user_supabase(access_token)
        try:
            resp = (
                client.table("notifications")
                .select("id", count=CountMethod.exact, head=True)
                .eq("recipient_id", str(recipient_id))
                .is_("read_at", "null")
                .execute()
            )
        except Exception as exc:
            raise NotificationRepositoryError(f"Failed to count notifications: {exc}") from exc
        return int(resp.count or 0)

    def mark_read(self, recipient_id: UUID, ids: Optional[list[UUID]], *, access_token: str) -> None:
        client = get_user_supabase(access_token)
        try:
            query = (
                client.table("notifications")
                .update({"read_at": datetime.now(UTC).isoformat()}, returning=ReturnMethod.minimal)
                .eq("recipient_id", str(recipient_id))
                .is_("read_at", "null")
            )
            if ids is not None:
                query = query.in_("id", [str(i) for i in ids])
            query.execute()
        except Exception as exc:
            raise NotificationRepositoryError(f"Failed to update notifications: {exc}") from exc

    def active_student_ids(self, course_ids: list[UUID], *, access_token: str) -> list[UUID]:
        if not course_ids:
            return []
        client = get_user_supabase(access_token)
        try:
            resp = (
                client.table("course_enrollments")
                .select("student_id")
                .in_("course_id", [str(c) for c in course_ids])
                .eq("status", "active")
                .execute()
            )
        except Exception as exc:
            raise NotificationRepositoryError(f"Failed to read enrollments: {exc}") from exc
        return list(dict.fromkeys(UUID(str(row["student_id"])) for row in (resp.data or [])))

    def course_ids_for_teacher(self, teacher_id: UUID, *, access_token: str) -> list[UUID]:
        client = get_user_supabase(access_token)
        try:
            resp = client.table("courses").select("id").eq("teacher_id", str(teacher_id)).execute()
        except Exception as exc:
            raise NotificationRepositoryError(f"Failed to read courses: {exc}") from exc
        return [UUID(str(row["id"])) for row in (resp.data or [])]

    def assignment_info(self, assignment_id: UUID, *, access_token: str) -> Optional[dict[str, Any]]:
        """``{id, teacher_id, course_id, title, status}`` or None."""
        client = get_user_supabase(access_token)
        try:
            resp = (
                client.table("assignments")
                .select("id, teacher_id, course_id, title, status")
                .eq("id", str(assignment_id))
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise NotificationRepositoryError(f"Failed to read assignment: {exc}") from exc
        rows = resp.data or []
        return rows[0] if rows else None

    def submission_info(self, submission_id: UUID, *, access_token: str) -> Optional[dict[str, Any]]:
        """``{id, student_id, assignment_id, status}`` or None."""
        client = get_user_supabase(access_token)
        try:
            resp = (
                client.table("submissions")
                .select("id, student_id, assignment_id, status")
                .eq("id", str(submission_id))
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise NotificationRepositoryError(f"Failed to read submission: {exc}") from exc
        rows = resp.data or []
        return rows[0] if rows else None
