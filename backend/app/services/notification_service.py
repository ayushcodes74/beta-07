"""Dashboard notifications: who is told what, when.

teacher -> students
  - assignment published (draft -> published) / published assignment edited
  - result published / re-published (updated)
  - late-submission decision (accepted / rejected)
  - review request answered (resolved / dismissed)
student -> teacher
  - assignment submitted (on time or late)
  - review request opened

The ``notify_*`` methods are best-effort and never raise: they run as FastAPI background
tasks after the main action has already succeeded, so a missing notifications table, an
RLS refusal or a network error only logs a warning and never fails the teacher's or
student's request.
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import Any, Callable, Optional
from uuid import UUID

from app.database.notification_repository import NotificationRepository
from app.schemas.notification import NotificationListResponse, NotificationType
from app.services.auth_service import CurrentUser

logger = logging.getLogger(__name__)

MAX_LIST = 50
_BODY_LIMIT = 1000


def get_notification_repository() -> NotificationRepository:
    from app.database.notification_repository import SupabaseNotificationRepository

    return SupabaseNotificationRepository()


def _name(user: CurrentUser, fallback: str) -> str:
    name = (user.display_name or "").strip()
    return name or fallback


def _quote(title: Optional[str]) -> str:
    title = (title or "").strip() or "an assignment"
    return title if len(title) <= 120 else title[:117] + "..."


def _excerpt(text: Optional[str], limit: int = 280) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _fmt_number(value: Any) -> str:
    try:
        number = Decimal(str(value)).normalize()
    except Exception:
        return str(value)
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


class NotificationService:
    def __init__(self, repository: NotificationRepository) -> None:
        self.repo = repository

    # ------------------------------------------------------------------ reading

    def list_for(self, user: CurrentUser, *, access_token: str, limit: int = MAX_LIST) -> NotificationListResponse:
        items = self.repo.list_for_recipient(user.id, min(max(limit, 1), MAX_LIST), access_token=access_token)
        unread = self.repo.count_unread(user.id, access_token=access_token)
        return NotificationListResponse(items=items, unread_count=unread)

    def mark_read(self, user: CurrentUser, ids: Optional[list[UUID]], *, access_token: str) -> None:
        self.repo.mark_read(user.id, ids, access_token=access_token)

    # ------------------------------------------------------- lookups (best effort)

    def assignment_status(self, assignment_id: UUID, *, access_token: str) -> Optional[str]:
        """Current status of an assignment, read BEFORE a change so transitions can be detected."""
        return self._safe(lambda: (self.repo.assignment_info(assignment_id, access_token=access_token) or {}).get("status"))

    def submission_status(self, submission_id: UUID, *, access_token: str) -> Optional[str]:
        return self._safe(lambda: (self.repo.submission_info(submission_id, access_token=access_token) or {}).get("status"))

    # ------------------------------------------------------- teacher -> students

    def notify_assignment_published(
        self, teacher: CurrentUser, assignment_id: UUID, *, updated: bool, access_token: str
    ) -> None:
        def run() -> None:
            info = self.repo.assignment_info(assignment_id, access_token=access_token)
            if not info or info.get("status") != "published":
                return  # drafts are invisible to students: nothing to announce
            course_id = info.get("course_id")
            # Assignments without a course are visible to every student; tell the teacher's students.
            course_ids = (
                [UUID(str(course_id))]
                if course_id
                else self.repo.course_ids_for_teacher(teacher.id, access_token=access_token)
            )
            students = self.repo.active_student_ids(course_ids, access_token=access_token)
            title = _quote(info.get("title"))
            who = _name(teacher, "Your teacher")
            if updated:
                kind = NotificationType.ASSIGNMENT_UPDATED
                heading = f"Assignment updated: {title}"
                body = f"{who} updated this assignment. Check the latest questions and due date."
            else:
                kind = NotificationType.ASSIGNMENT_PUBLISHED
                heading = f"New assignment: {title}"
                body = f"{who} published a new assignment. Open it to see the questions and due date."
            self._send(
                teacher,
                students,
                kind,
                heading,
                body,
                f"/app/student/submit/{assignment_id}",
                assignment_id=assignment_id,
                access_token=access_token,
            )

        self._run("assignment", run)

    def notify_result_published(
        self,
        teacher: CurrentUser,
        submission_id: UUID,
        *,
        updated: bool,
        final_score: Any,
        max_score: Any,
        access_token: str,
    ) -> None:
        def run() -> None:
            submission = self.repo.submission_info(submission_id, access_token=access_token)
            if not submission:
                return
            assignment = self.repo.assignment_info(UUID(str(submission["assignment_id"])), access_token=access_token)
            title = _quote((assignment or {}).get("title"))
            score = _fmt_number(final_score) + (f"/{_fmt_number(max_score)}" if max_score is not None else "")
            if updated:
                kind = NotificationType.RESULT_UPDATED
                heading = f"Result updated: {title}"
                body = f"{_name(teacher, 'Your teacher')} updated your grade. New score: {score}."
            else:
                kind = NotificationType.RESULT_PUBLISHED
                heading = f"Result published: {title}"
                body = f"{_name(teacher, 'Your teacher')} checked your submission. Score: {score}."
            self._send(
                teacher,
                [UUID(str(submission["student_id"]))],
                kind,
                heading,
                body,
                "/app/results",
                assignment_id=UUID(str(submission["assignment_id"])),
                submission_id=submission_id,
                access_token=access_token,
            )

        self._run("result", run)

    def notify_late_decision(
        self,
        teacher: CurrentUser,
        *,
        submission_id: UUID,
        assignment_id: UUID,
        student_id: UUID,
        decision: str,
        penalty_percent: Optional[float],
        note: Optional[str],
        access_token: str,
    ) -> None:
        if decision not in ("accepted", "rejected"):
            return  # re-opening a decision is not news for the student

        def run() -> None:
            assignment = self.repo.assignment_info(assignment_id, access_token=access_token)
            title = _quote((assignment or {}).get("title"))
            if decision == "accepted":
                heading = f"Late submission accepted: {title}"
                body = "Your teacher accepted your late submission"
                body += f" with a {_fmt_number(penalty_percent)}% penalty." if penalty_percent else "."
            else:
                heading = f"Late submission rejected: {title}"
                body = "Your teacher did not accept your late submission."
            if note and note.strip():
                body += f" Note: {_excerpt(note)}"
            self._send(
                teacher,
                [student_id],
                NotificationType.LATE_DECISION,
                heading,
                body,
                "/app/submissions",
                assignment_id=assignment_id,
                submission_id=submission_id,
                access_token=access_token,
            )

        self._run("late decision", run)

    def notify_review_resolved(
        self,
        teacher: CurrentUser,
        *,
        submission_id: UUID,
        student_id: UUID,
        status: str,
        teacher_response: Optional[str],
        access_token: str,
    ) -> None:
        def run() -> None:
            title = self._title_for_submission(submission_id, access_token)
            verb = "resolved" if status == "resolved" else "dismissed"
            body = f"{_name(teacher, 'Your teacher')} {verb} your review request."
            if teacher_response and teacher_response.strip():
                body += f" Reply: {_excerpt(teacher_response)}"
            self._send(
                teacher,
                [student_id],
                NotificationType.REVIEW_RESOLVED,
                f"Review request {verb}: {title}",
                body,
                "/app/results",
                submission_id=submission_id,
                access_token=access_token,
            )

        self._run("review resolved", run)

    # ------------------------------------------------------- student -> teacher

    def notify_submission_received(
        self, student: CurrentUser, *, assignment_id: UUID, submission_id: UUID, late: bool, access_token: str
    ) -> None:
        def run() -> None:
            assignment = self.repo.assignment_info(assignment_id, access_token=access_token)
            if not assignment or not assignment.get("teacher_id"):
                return
            title = _quote(assignment.get("title"))
            who = _name(student, "A student")
            if late:
                heading = f"Late submission: {title}"
                body = f"{who} submitted after the due date. Accept or reject it in Late submissions."
                link = "/app/late-submissions"
            else:
                heading = f"New submission: {title}"
                body = f"{who} submitted this assignment."
                link = "/app/submissions"
            self._send(
                student,
                [UUID(str(assignment["teacher_id"]))],
                NotificationType.SUBMISSION_RECEIVED,
                heading,
                body,
                link,
                assignment_id=assignment_id,
                submission_id=submission_id,
                access_token=access_token,
            )

        self._run("submission", run)

    def notify_review_requested(
        self, student: CurrentUser, *, submission_id: UUID, reason: str, access_token: str
    ) -> None:
        def run() -> None:
            submission = self.repo.submission_info(submission_id, access_token=access_token)
            if not submission:
                return
            assignment = self.repo.assignment_info(UUID(str(submission["assignment_id"])), access_token=access_token)
            if not assignment or not assignment.get("teacher_id"):
                return
            self._send(
                student,
                [UUID(str(assignment["teacher_id"]))],
                NotificationType.REVIEW_REQUESTED,
                f"Review requested: {_quote(assignment.get('title'))}",
                f"{_name(student, 'A student')} asked you to re-check their grade: {_excerpt(reason)}",
                "/app/reviews?tab=requests",
                assignment_id=UUID(str(submission["assignment_id"])),
                submission_id=submission_id,
                access_token=access_token,
            )

        self._run("review request", run)

    # ------------------------------------------------------------------ helpers

    def _title_for_submission(self, submission_id: UUID, access_token: str) -> str:
        submission = self.repo.submission_info(submission_id, access_token=access_token)
        if not submission:
            return _quote(None)
        assignment = self.repo.assignment_info(UUID(str(submission["assignment_id"])), access_token=access_token)
        return _quote((assignment or {}).get("title"))

    def _send(
        self,
        actor: CurrentUser,
        recipients: list[UUID],
        kind: NotificationType,
        title: str,
        body: str,
        link: str,
        *,
        assignment_id: Optional[UUID] = None,
        submission_id: Optional[UUID] = None,
        access_token: str,
    ) -> None:
        rows = [
            {
                "recipient_id": str(recipient),
                "actor_id": str(actor.id),
                "type": kind.value,
                "title": title[:200],
                "body": body[:_BODY_LIMIT],
                "link": link,
                "assignment_id": str(assignment_id) if assignment_id else None,
                "submission_id": str(submission_id) if submission_id else None,
            }
            for recipient in dict.fromkeys(recipients)
            if recipient != actor.id
        ]
        self.repo.insert_many(rows, access_token=access_token)

    @staticmethod
    def _run(label: str, operation: Callable[[], None]) -> None:
        try:
            operation()
        except Exception as exc:  # best effort: never fail the action that triggered it
            logger.warning("Could not send %s notification: %s", label, exc)

    @staticmethod
    def _safe(operation: Callable[[], Any]) -> Any:
        try:
            return operation()
        except Exception as exc:
            logger.warning("Notification lookup failed: %s", exc)
            return None
