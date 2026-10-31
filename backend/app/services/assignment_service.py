"""Assignment management business logic (Module 2).

Persistence goes through an ``AssignmentRepository``. Every repository call
receives the caller's verified access token so a Supabase implementation can
run under the user's RLS context. The service also enforces ownership and
publication rules itself, as defence in depth.

INTEGRATION PENDING: no concrete repository exists yet. Person 4 still has to
confirm the assignments/questions storage (tables, columns, id type, status
values), how student access is scoped (course/enrollment), the RLS policies,
and the delete/archive policy. Until then ``UnconfiguredAssignmentRepository``
is used and every assignment route returns 503; nothing is stored in memory.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from app.schemas.assignment import (
    AssignmentContent,
    AssignmentCreate,
    AssignmentStatus,
    AssignmentUpdate,
)
from app.schemas.user import Role
from app.services.auth_service import CurrentUser

logger = logging.getLogger(__name__)


class AssignmentRecord(BaseModel):
    """An assignment as returned by the repository."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    teacher_id: UUID
    status: AssignmentStatus
    content: AssignmentContent
    course_id: UUID | None = None


class AssignmentRepositoryError(Exception):
    """The assignment store failed or returned something unusable."""


class AssignmentIntegrationNotConfiguredError(AssignmentRepositoryError):
    """No confirmed assignment persistence is available yet."""


class AssignmentInUseError(Exception):
    """The store refused to delete the assignment because other data depends on it."""


class AssignmentRepository(Protocol):
    """Persistence for assignments. ``access_token`` is the caller's verified token."""

    def create(
        self, teacher_id: UUID, content: AssignmentCreate, *, access_token: str
    ) -> AssignmentRecord:
        """Store a new assignment as a draft owned by ``teacher_id``."""
        ...

    def get(self, assignment_id: UUID, *, access_token: str) -> AssignmentRecord | None: ...

    def owns_course(self, course_id: UUID, teacher_id: UUID, *, access_token: str) -> bool: ...

    def is_owned_by(self, assignment_id: UUID, teacher_id: UUID, *, access_token: str) -> bool:
        """Cheap ownership check (no questions/answer keys). Optional: callers fall back to get()."""
        ...

    def list_by_teacher(self, teacher_id: UUID, *, access_token: str) -> list[AssignmentRecord]: ...

    def list_published_for_student(self, student_id: UUID, *, access_token: str) -> list[AssignmentRecord]:
        """Published assignments this student is allowed to access."""
        ...

    def get_published_for_student(
        self, assignment_id: UUID, student_id: UUID, *, access_token: str
    ) -> AssignmentRecord | None:
        """The assignment, only if it is published and this student may access it."""
        ...

    def replace_content(
        self, assignment_id: UUID, content: AssignmentContent, *, access_token: str
    ) -> AssignmentRecord | None: ...

    def set_status(
        self, assignment_id: UUID, status: AssignmentStatus, *, access_token: str
    ) -> AssignmentRecord | None: ...

    def delete(self, assignment_id: UUID, *, access_token: str) -> bool:
        """Return False if nothing was deleted; raise AssignmentInUseError if refused."""
        ...


class UnconfiguredAssignmentRepository:
    """Placeholder until Person 4 confirms the assignment storage contract."""

    def _fail(self, *args: Any, **kwargs: Any) -> Any:
        raise AssignmentIntegrationNotConfiguredError("assignment repository is not configured")

    create = get = owns_course = is_owned_by = list_by_teacher = list_published_for_student = _fail
    get_published_for_student = replace_content = set_status = delete = _fail


def get_assignment_repository() -> AssignmentRepository:
    # TODO(db-contract): return the Supabase-backed repository once Person 4
    # confirms the assignment tables, student access scoping and RLS policies.
    from app.database.assignment_repository import SupabaseAssignmentRepository

    return SupabaseAssignmentRepository()


class AssignmentNotFoundError(Exception):
    """The assignment does not exist or is not accessible to the caller."""


class AssignmentPermissionError(Exception):
    """The caller's role may not perform this operation."""


class AssignmentValidationError(Exception):
    """A business rule rejected the request (as opposed to schema validation)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AssignmentService:
    def __init__(self, repository: AssignmentRepository, clock: Callable[[], datetime] = _utcnow) -> None:
        self._repository = repository
        self._clock = clock

    # ---- creation ---------------------------------------------------------

    def create(self, teacher: CurrentUser, payload: AssignmentCreate, *, access_token: str) -> AssignmentRecord:
        self._require_role(teacher, Role.TEACHER)
        self._require_future_deadline(payload.due_at)
        if payload.course_id and not self._repository.owns_course(
            payload.course_id, teacher.id, access_token=access_token
        ):
            raise AssignmentNotFoundError
        # Always a draft: publishing is a separate, explicit action.
        record = self._repository.create(teacher.id, payload, access_token=access_token)
        self._check_owned(teacher, record)
        if record.status is not AssignmentStatus.DRAFT:
            logger.error("Repository created an assignment that is not a draft")
            raise AssignmentRepositoryError("new assignment is not a draft")
        return record

    # ---- reading ----------------------------------------------------------

    def list_for(self, user: CurrentUser, *, access_token: str) -> list[AssignmentRecord]:
        if user.role is Role.TEACHER:
            records = self._repository.list_by_teacher(user.id, access_token=access_token)
            return [record for record in records if record.teacher_id == user.id]
        if user.role is Role.STUDENT:
            records = self._repository.list_published_for_student(user.id, access_token=access_token)
            return [record for record in records if record.status is AssignmentStatus.PUBLISHED]
        raise AssignmentPermissionError

    def owned_ids(self, teacher: CurrentUser, *, access_token: str) -> list[UUID]:
        """Ids of the teacher's own assignments, without loading questions or answer keys."""
        self._require_role(teacher, Role.TEACHER)
        list_ids = getattr(self._repository, "list_ids_by_teacher", None)
        if list_ids is not None:
            return list(list_ids(teacher.id, access_token=access_token))
        return [record.id for record in self.list_for(teacher, access_token=access_token)]

    def get_for(self, user: CurrentUser, assignment_id: UUID, *, access_token: str) -> AssignmentRecord:
        if user.role is Role.TEACHER:
            return self._get_owned(user, assignment_id, access_token)
        if user.role is Role.STUDENT:
            record = self._repository.get_published_for_student(assignment_id, user.id, access_token=access_token)
            if record is None or record.id != assignment_id or record.status is not AssignmentStatus.PUBLISHED:
                raise AssignmentNotFoundError
            return record
        raise AssignmentPermissionError

    # ---- modification (owning teacher only) --------------------------------

    def update(
        self, teacher: CurrentUser, assignment_id: UUID, payload: AssignmentUpdate, *, access_token: str
    ) -> AssignmentRecord:
        current = self._get_owned(teacher, assignment_id, access_token)
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise AssignmentValidationError("empty_update", "No updatable fields were provided.")
        if "due_at" in changes:
            self._require_future_deadline(changes["due_at"])
        # Published assignments stay editable, but must remain something students can answer.
        if current.status is AssignmentStatus.PUBLISHED and changes.get("questions") == []:
            raise AssignmentValidationError(
                "not_publishable", "A published assignment needs at least one question. Unpublish it first."
            )

        try:
            merged = AssignmentContent.model_validate({**current.content.model_dump(), **changes})
        except ValidationError as exc:
            message = exc.errors()[0]["msg"].removeprefix("Value error, ")
            raise AssignmentValidationError("invalid_assignment", message) from None

        record = self._repository.replace_content(assignment_id, merged, access_token=access_token)
        return self._check_owned(teacher, record)

    def publish(self, teacher: CurrentUser, assignment_id: UUID, *, access_token: str) -> AssignmentRecord:
        current = self._get_owned(teacher, assignment_id, access_token)
        if current.status is AssignmentStatus.PUBLISHED:
            return current
        if not current.content.questions:
            raise AssignmentValidationError("not_publishable", "An assignment needs at least one question.")
        self._require_future_deadline(current.content.due_at)
        record = self._repository.set_status(assignment_id, AssignmentStatus.PUBLISHED, access_token=access_token)
        return self._check_owned(teacher, record)

    def unpublish(self, teacher: CurrentUser, assignment_id: UUID, *, access_token: str) -> AssignmentRecord:
        current = self._get_owned(teacher, assignment_id, access_token)
        if current.status is AssignmentStatus.DRAFT:
            return current
        record = self._repository.set_status(assignment_id, AssignmentStatus.DRAFT, access_token=access_token)
        return self._check_owned(teacher, record)

    def delete(self, teacher: CurrentUser, assignment_id: UUID, *, access_token: str) -> None:
        # POLICY PENDING: whether assignments with submissions are archived or
        # protected is not decided. The repository may refuse with
        # AssignmentInUseError; this service never cascades on its own.
        self._get_owned(teacher, assignment_id, access_token)
        if not self._repository.delete(assignment_id, access_token=access_token):
            raise AssignmentNotFoundError

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def _require_role(user: CurrentUser, role: Role) -> None:
        if user.role is not role:
            raise AssignmentPermissionError

    def require_owned(self, teacher: CurrentUser, assignment_id: UUID, *, access_token: str) -> None:
        """Raise AssignmentNotFoundError unless ``teacher`` owns the assignment.

        Uses the repository's single-row ownership query when available, instead of loading the
        whole assignment with its questions and answer keys (3 round trips to Supabase).
        """
        self._require_role(teacher, Role.TEACHER)
        is_owned_by = getattr(self._repository, "is_owned_by", None)
        if is_owned_by is None:
            self._get_owned(teacher, assignment_id, access_token)
            return
        if not is_owned_by(assignment_id, teacher.id, access_token=access_token):
            raise AssignmentNotFoundError

    def _get_owned(self, teacher: CurrentUser, assignment_id: UUID, access_token: str) -> AssignmentRecord:
        """Fetch an assignment the teacher owns. Others' assignments look like 404."""
        self._require_role(teacher, Role.TEACHER)
        record = self._repository.get(assignment_id, access_token=access_token)
        if record is None or record.id != assignment_id or record.teacher_id != teacher.id:
            raise AssignmentNotFoundError
        return record

    @staticmethod
    def _check_owned(teacher: CurrentUser, record: AssignmentRecord | None) -> AssignmentRecord:
        if record is None:
            raise AssignmentNotFoundError
        if record.teacher_id != teacher.id:
            logger.error("Assignment repository returned a record owned by another teacher")
            raise AssignmentRepositoryError("owner mismatch")
        return record

    def _require_future_deadline(self, due_at: datetime) -> None:
        if due_at <= self._clock():
            raise AssignmentValidationError("due_date_in_past", "The due date must be in the future.")
