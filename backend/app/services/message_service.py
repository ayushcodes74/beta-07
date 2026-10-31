"""Student <-> teacher chat: one private conversation per (course, student) with the course's teacher.

Access is checked here first (for clear errors) and enforced again by RLS in the database:
  - students may only use their own thread, in courses they are actively enrolled in
  - teachers may only use threads in courses they own, with actively enrolled students
Anyone else gets CourseNotFoundError (404), the same as for the course itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.database.message_repository import MessageRepository
from app.schemas.message import MessageResponse, MessageThread
from app.schemas.user import Role
from app.services.auth_service import CurrentUser
from app.services.course_service import (
    CourseNotFoundError,
    CoursePermissionError,
    CourseRepository,
    CourseService,
    CourseValidationError,
)

# Most recent messages returned when a conversation is opened; polling then asks only for newer ones.
DEFAULT_PAGE_SIZE = 200


class MessageService:
    def __init__(self, courses: CourseService, course_repo: CourseRepository, repository: MessageRepository) -> None:
        self.courses = courses
        self.course_repo = course_repo
        self.repository = repository

    def _thread_student(
        self, user: CurrentUser, course_id: UUID, student_id: Optional[UUID], *, access_token: str
    ) -> UUID:
        """Validate access to the (course, student) thread and return its student id."""
        # Owning teacher or actively enrolled student; anyone else -> CourseNotFoundError.
        self.courses.get_for(user, course_id, access_token=access_token)
        if user.role is Role.STUDENT:
            if student_id is not None and student_id != user.id:
                raise CourseNotFoundError  # never reveal other students' conversations
            return user.id
        if user.role is Role.TEACHER:
            if student_id is None:
                raise CourseValidationError("student_required", "Choose which student to message.")
            if not self.course_repo.is_student_enrolled(course_id, student_id, access_token=access_token):
                raise CourseValidationError("student_not_enrolled", "That student is not enrolled in this course.")
            return student_id
        raise CoursePermissionError

    def get_messages(
        self,
        user: CurrentUser,
        course_id: UUID,
        student_id: Optional[UUID] = None,
        *,
        after: Optional[datetime] = None,
        access_token: str,
    ) -> list[MessageResponse]:
        thread_student = self._thread_student(user, course_id, student_id, access_token=access_token)
        rows = self.repository.list_thread(
            course_id, thread_student, after=after, limit=DEFAULT_PAGE_SIZE, access_token=access_token
        )
        return [row.model_copy(update={"is_mine": row.sender_id == user.id}) for row in rows]

    def send(
        self,
        user: CurrentUser,
        course_id: UUID,
        body: str,
        student_id: Optional[UUID] = None,
        *,
        access_token: str,
    ) -> MessageResponse:
        thread_student = self._thread_student(user, course_id, student_id, access_token=access_token)
        message = self.repository.create(course_id, thread_student, user.id, body, access_token=access_token)
        return message.model_copy(update={"is_mine": True})

    def mark_read(
        self, user: CurrentUser, course_id: UUID, student_id: Optional[UUID] = None, *, access_token: str
    ) -> int:
        thread_student = self._thread_student(user, course_id, student_id, access_token=access_token)
        return self.repository.mark_read(course_id, thread_student, user.id, access_token=access_token)

    def list_threads(self, user: CurrentUser, *, access_token: str) -> list[MessageThread]:
        if user.role not in (Role.STUDENT, Role.TEACHER):
            raise CoursePermissionError
        rows = self.repository.list_threads(access_token=access_token)
        threads = [_thread(row, user) for row in rows]
        threads.sort(key=lambda t: t.last_message_at, reverse=True)
        return threads


def _thread(row: dict[str, Any], user: CurrentUser) -> MessageThread:
    return MessageThread(
        course_id=UUID(str(row["course_id"])),
        course_name=(row.get("course_name") or "").strip() or "Course",
        student_id=UUID(str(row["student_id"])),
        student_name=(row.get("student_name") or "").strip() or "Student",
        teacher_id=UUID(str(row["teacher_id"])),
        teacher_name=(row.get("teacher_name") or "").strip() or "Teacher",
        last_message=row.get("last_body") or "",
        last_message_is_mine=str(row.get("last_sender_id")) == str(user.id),
        last_message_at=datetime.fromisoformat(str(row["last_at"]).replace("Z", "+00:00")),
        unread_count=int(row.get("unread_count") or 0),
    )
