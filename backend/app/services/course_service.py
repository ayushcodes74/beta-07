"""Course management business logic and repository protocol (Module 2A).

Persistence goes through a CourseRepository. Every repository call receives
the caller's verified Supabase access token so queries execute under the user's
Row-Level Security (RLS) context.
"""

from collections.abc import Callable
from datetime import UTC, datetime
import logging
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.course import CourseCreate, CourseUpdate
from app.schemas.user import Role
from app.services.auth_service import CurrentUser

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Domain Records
# --------------------------------------------------------------------------


class CourseRecord(BaseModel):
    """A course as returned by the repository."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    teacher_id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    students_count: int = 0
    instructor_name: str = ""


class EnrollmentRecord(BaseModel):
    """An enrollment record in course_enrollments."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    course_id: UUID
    student_id: UUID
    status: str
    enrolled_at: datetime


class EnrolledStudent(BaseModel):
    """Enrolled student data for teacher course roster."""

    model_config = ConfigDict(frozen=True)

    student_id: UUID
    name: str | None = None
    email: str | None = None
    status: str = "active"
    enrolled_at: datetime


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------


class CourseRepositoryError(Exception):
    """The course store failed or returned unusable data."""


class CourseIntegrationNotConfiguredError(CourseRepositoryError):
    """Course storage is not configured yet."""


class CourseNotFoundError(Exception):
    """Course does not exist or caller is not authorized to see it."""


class CoursePermissionError(Exception):
    """Caller's role is not permitted to perform this operation."""


class CourseValidationError(Exception):
    """Business rule validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DuplicateEnrollmentError(Exception):
    """The student is already actively enrolled in this course."""


class InvalidEnrollmentTargetError(Exception):
    """Student profile cannot be enrolled (not found, wrong role, or disabled)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EnrollmentNotFoundError(Exception):
    """Active enrollment for student was not found in this course."""


# --------------------------------------------------------------------------
# Repository Protocol
# --------------------------------------------------------------------------


class CourseRepository(Protocol):
    """Persistence interface for course and enrollment operations."""

    def create(
        self, teacher_id: UUID, name: str, description: str | None, *, access_token: str
    ) -> CourseRecord: ...

    def get(self, course_id: UUID, *, access_token: str) -> CourseRecord | None: ...

    def list_by_teacher(self, teacher_id: UUID, *, access_token: str) -> list[CourseRecord]: ...

    def list_by_student(self, student_id: UUID, *, access_token: str) -> list[CourseRecord]: ...

    def is_student_enrolled(self, course_id: UUID, student_id: UUID, *, access_token: str) -> bool: ...

    def update(
        self, course_id: UUID, name: str | None, description: str | None, *, access_token: str
    ) -> CourseRecord | None: ...

    def get_student_profile(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> dict[str, Any] | None: ...

    def get_enrollment(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> EnrollmentRecord | None: ...

    def enroll_student(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> EnrollmentRecord: ...

    def reactivate_enrollment(
        self, enrollment_id: UUID, *, access_token: str
    ) -> EnrollmentRecord: ...

    def list_enrolled_students(
        self, course_id: UUID, *, access_token: str
    ) -> list[EnrolledStudent]: ...

    def deactivate_enrollment(
        self, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> bool: ...

    def find_student_id_by_email(
        self, course_id: UUID, email: str, *, access_token: str
    ) -> UUID | None: ...


class UnconfiguredCourseRepository:
    """Fallback repository when Supabase connection is unconfigured."""

    def _fail(self, *args: Any, **kwargs: Any) -> Any:
        raise CourseIntegrationNotConfiguredError("Course repository is not configured")

    create = get = list_by_teacher = list_by_student = is_student_enrolled = _fail
    update = get_student_profile = get_enrollment = enroll_student = _fail
    reactivate_enrollment = list_enrolled_students = deactivate_enrollment = _fail
    find_student_id_by_email = _fail


def get_course_repository() -> CourseRepository:
    from app.database.course_repository import SupabaseCourseRepository

    return SupabaseCourseRepository()


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------
# Course Service
# --------------------------------------------------------------------------


class CourseService:
    def __init__(self, repository: CourseRepository, clock: Callable[[], datetime] = _utcnow) -> None:
        self._repository = repository
        self._clock = clock

    @staticmethod
    def _require_role(user: CurrentUser, expected: Role) -> None:
        if user.role is not expected:
            raise CoursePermissionError

    # ---- Course CRUD ----

    def create(self, teacher: CurrentUser, payload: CourseCreate, *, access_token: str) -> CourseRecord:
        self._require_role(teacher, Role.TEACHER)
        return self._repository.create(
            teacher.id,
            payload.name,
            payload.description,
            access_token=access_token,
        )

    def list_for(self, user: CurrentUser, *, access_token: str) -> list[CourseRecord]:
        if user.role is Role.TEACHER:
            return self._repository.list_by_teacher(user.id, access_token=access_token)
        if user.role is Role.STUDENT:
            return self._repository.list_by_student(user.id, access_token=access_token)
        raise CoursePermissionError

    def get_for(self, user: CurrentUser, course_id: UUID, *, access_token: str) -> CourseRecord:
        if user.role is Role.TEACHER:
            record = self._repository.get(course_id, access_token=access_token)
            if record is None or record.teacher_id != user.id:
                raise CourseNotFoundError
            return record

        if user.role is Role.STUDENT:
            if not self._repository.is_student_enrolled(course_id, user.id, access_token=access_token):
                raise CourseNotFoundError
            record = self._repository.get(course_id, access_token=access_token)
            if record is None:
                raise CourseNotFoundError
            return record

        raise CoursePermissionError

    def update(
        self, teacher: CurrentUser, course_id: UUID, payload: CourseUpdate, *, access_token: str
    ) -> CourseRecord:
        self._require_role(teacher, Role.TEACHER)
        existing = self._repository.get(course_id, access_token=access_token)
        if existing is None or existing.teacher_id != teacher.id:
            raise CourseNotFoundError

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise CourseValidationError("empty_update", "No updatable fields were provided.")

        updated = self._repository.update(
            course_id,
            changes.get("name"),
            changes.get("description"),
            access_token=access_token,
        )
        if updated is None:
            raise CourseNotFoundError
        return updated

    # ---- Enrollments ----

    def enroll_student(
        self, teacher: CurrentUser, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> EnrollmentRecord:
        self._require_role(teacher, Role.TEACHER)
        course = self._repository.get(course_id, access_token=access_token)
        if course is None or course.teacher_id != teacher.id:
            raise CourseNotFoundError

        # Validate target student profile scoped to this course
        profile = self._repository.get_student_profile(course_id, student_id, access_token=access_token)
        if profile is None:
            raise InvalidEnrollmentTargetError("student_not_found", "The specified student was not found.")

        if profile.get("_validation_error"):
            err_code = profile["_validation_error"]
            err_msg = profile.get("_validation_message", "Invalid student account.")
            if err_code == "course_not_found":
                raise CourseNotFoundError
            raise InvalidEnrollmentTargetError(err_code, err_msg)

        if profile.get("role") != "student":
            raise InvalidEnrollmentTargetError("invalid_role", "Only student accounts can be enrolled in courses.")

        if profile.get("is_disabled", False):
            raise InvalidEnrollmentTargetError("account_disabled", "Cannot enroll a disabled student account.")

        # Check existing enrollment
        existing = self._repository.get_enrollment(course_id, student_id, access_token=access_token)
        if existing:
            if existing.status == "active":
                raise DuplicateEnrollmentError("Student is already actively enrolled in this course.")
            # Reactivate inactive enrollment
            return self._repository.reactivate_enrollment(existing.id, access_token=access_token)

        # Fresh enrollment
        return self._repository.enroll_student(course_id, student_id, access_token=access_token)

    def enroll_student_by_email(
        self, teacher: CurrentUser, course_id: UUID, email: str, *, access_token: str
    ) -> EnrollmentRecord:
        """Resolve a student's sign-in email, then enroll them with the same checks as enroll_student."""
        self._require_role(teacher, Role.TEACHER)
        course = self._repository.get(course_id, access_token=access_token)
        if course is None or course.teacher_id != teacher.id:
            raise CourseNotFoundError

        student_id = self._repository.find_student_id_by_email(course_id, email, access_token=access_token)
        if student_id is None:
            # One message for unknown email, non-student and disabled accounts, so teachers
            # cannot use this to probe which emails belong to which kind of account.
            raise InvalidEnrollmentTargetError(
                "student_not_found", "No active student account uses that email address."
            )
        return self.enroll_student(teacher, course_id, student_id, access_token=access_token)

    def list_students(
        self, teacher: CurrentUser, course_id: UUID, *, access_token: str
    ) -> list[EnrolledStudent]:
        self._require_role(teacher, Role.TEACHER)
        course = self._repository.get(course_id, access_token=access_token)
        if course is None or course.teacher_id != teacher.id:
            raise CourseNotFoundError

        return self._repository.list_enrolled_students(course_id, access_token=access_token)

    def deactivate_enrollment(
        self, teacher: CurrentUser, course_id: UUID, student_id: UUID, *, access_token: str
    ) -> None:
        self._require_role(teacher, Role.TEACHER)
        course = self._repository.get(course_id, access_token=access_token)
        if course is None or course.teacher_id != teacher.id:
            raise CourseNotFoundError

        success = self._repository.deactivate_enrollment(course_id, student_id, access_token=access_token)
        if not success:
            raise EnrollmentNotFoundError("Active enrollment not found for this student.")

