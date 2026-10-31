"""Assignment management endpoints (Module 2).

Teachers create, edit, publish and delete their own assignments. Students only
ever receive published assignments through answer-free response models.

Privacy convention: an assignment the caller may not access (another teacher's
assignment, or a draft for a student) is reported as 404, so its existence is
not revealed. 403 is used when the caller's role cannot use the endpoint at all.
"""

import logging
from collections.abc import Callable
from typing import Annotated, NoReturn, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.v1.endpoints.auth import AUTH_ERROR_RESPONSES
from app.core.dependencies import api_error, get_bearer_token, require_authenticated_user, require_teacher
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentStudentResponse,
    AssignmentTeacherResponse,
    AssignmentUpdate,
    McqOptionStudentView,
    McqQuestion,
    McqQuestionStudentView,
    McqQuestionTeacherView,
    SubjectiveQuestionStudentView,
    SubjectiveQuestionTeacherView,
)
from app.schemas.auth import ErrorResponse
from app.schemas.user import Role
from app.services.assignment_service import (
    AssignmentInUseError,
    AssignmentIntegrationNotConfiguredError,
    AssignmentNotFoundError,
    AssignmentPermissionError,
    AssignmentRecord,
    AssignmentRepository,
    AssignmentRepositoryError,
    AssignmentService,
    AssignmentValidationError,
    get_assignment_repository,
)
from app.services.auth_service import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assignments", tags=["assignments"])

TeacherUser = Annotated[CurrentUser, Depends(require_teacher)]
AnyUser = Annotated[CurrentUser, Depends(require_authenticated_user)]
AccessToken = Annotated[str, Depends(get_bearer_token)]

ANY_ROLE_RESPONSE = list[AssignmentTeacherResponse] | list[AssignmentStudentResponse]

ERROR_RESPONSES: dict[int | str, dict] = {
    **AUTH_ERROR_RESPONSES,
    403: {"model": ErrorResponse, "description": "Role not allowed, missing profile, or invalid role."},
    404: {"model": ErrorResponse, "description": "Assignment does not exist or is not accessible."},
    503: {"model": ErrorResponse, "description": "Authentication or assignment storage is unavailable."},
}
COLLECTION_ERROR_RESPONSES = {code: value for code, value in ERROR_RESPONSES.items() if code != 404}


def get_assignment_service(
    repository: Annotated[AssignmentRepository, Depends(get_assignment_repository)],
) -> AssignmentService:
    return AssignmentService(repository)


Service = Annotated[AssignmentService, Depends(get_assignment_service)]


# --------------------------------------------------------------------------
# Error mapping and response builders
# --------------------------------------------------------------------------


def _raise_http(exc: Exception) -> NoReturn:
    if isinstance(exc, AssignmentNotFoundError):
        raise api_error(status.HTTP_404_NOT_FOUND, "assignment_not_found", "Assignment not found.") from None
    if isinstance(exc, AssignmentPermissionError):
        raise api_error(
            status.HTTP_403_FORBIDDEN, "forbidden", "You do not have permission to perform this action."
        ) from None
    if isinstance(exc, AssignmentValidationError):
        raise api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code, exc.message) from None
    if isinstance(exc, AssignmentInUseError):
        raise api_error(
            status.HTTP_409_CONFLICT,
            "assignment_in_use",
            str(exc) or "This assignment cannot be changed because it is in use.",
        ) from None
    if isinstance(exc, AssignmentIntegrationNotConfiguredError):
        logger.error("Assignment integration is not configured yet")
    else:
        logger.error("Assignment repository failure: %s", type(exc).__name__)
    raise api_error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "assignment_service_unavailable",
        "Assignments are temporarily unavailable.",
    ) from None


_HANDLED_ERRORS = (
    AssignmentNotFoundError,
    AssignmentPermissionError,
    AssignmentValidationError,
    AssignmentInUseError,
    AssignmentRepositoryError,
)


T = TypeVar("T")


def _call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except _HANDLED_ERRORS as exc:
        _raise_http(exc)


def teacher_view(record: AssignmentRecord) -> AssignmentTeacherResponse:
    content = record.content
    questions = [
        (McqQuestionTeacherView if isinstance(question, McqQuestion) else SubjectiveQuestionTeacherView)(
            **question.model_dump(), position=position
        )
        for position, question in enumerate(content.questions, start=1)
    ]
    return AssignmentTeacherResponse(
        id=record.id,
        teacher_id=record.teacher_id,
        course_id=record.course_id,
        status=record.status,
        title=content.title,
        instructions=content.instructions,
        due_at=content.due_at,
        total_marks=content.total_marks,
        questions=questions,
    )


def student_view(record: AssignmentRecord) -> AssignmentStudentResponse:
    """Explicit allow-list: answers and teacher-only data are never copied."""
    content = record.content
    questions: list[McqQuestionStudentView | SubjectiveQuestionStudentView] = []
    for position, question in enumerate(content.questions, start=1):
        if isinstance(question, McqQuestion):
            questions.append(
                McqQuestionStudentView(
                    position=position,
                    text=question.text,
                    marks=question.marks,
                    options=[McqOptionStudentView(id=option.id, text=option.text) for option in question.options],
                )
            )
        else:
            questions.append(
                SubjectiveQuestionStudentView(
                    position=position,
                    text=question.text,
                    marks=question.marks,
                    instructions=question.instructions,
                )
            )
    return AssignmentStudentResponse(
        id=record.id,
        course_id=record.course_id,
        title=content.title,
        instructions=content.instructions,
        due_at=content.due_at,
        total_marks=content.total_marks,
        questions=questions,
    )


def _view_for(user: CurrentUser, record: AssignmentRecord) -> AssignmentTeacherResponse | AssignmentStudentResponse:
    return teacher_view(record) if user.role is Role.TEACHER else student_view(record)


AUTH_HEADER_DOC = "**Authentication:** `Authorization: Bearer <Supabase access token>`."


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AssignmentTeacherResponse,
    summary="Create an assignment (teacher)",
    description=(
        f"{AUTH_HEADER_DOC} Teachers only.\n\n"
        "Creates a **draft** owned by the caller; it is not visible to students until published. "
        "`due_at` must include a timezone offset and be in the future. Total question marks may not "
        "exceed `total_marks`. An optional `course_id` must refer to a course owned by the caller. "
        "`status`, `id` and `teacher_id` cannot be supplied."
    ),
    responses={**COLLECTION_ERROR_RESPONSES, 422: {"description": "Invalid assignment data."}},
)
def create_assignment(
    payload: AssignmentCreate, teacher: TeacherUser, token: AccessToken, service: Service
) -> AssignmentTeacherResponse:
    record = _call(lambda: service.create(teacher, payload, access_token=token))
    return teacher_view(record)


@router.get(
    "",
    response_model=ANY_ROLE_RESPONSE,
    summary="List assignments",
    description=(
        f"{AUTH_HEADER_DOC}\n\n"
        "- **Teachers** get the assignments they own (drafts and published), including answers.\n"
        "- **Students** get published assignments they can access, without correct answers or "
        "expected solutions."
    ),
    responses=COLLECTION_ERROR_RESPONSES,
)
def list_assignments(
    user: AnyUser, token: AccessToken, service: Service
) -> list[AssignmentTeacherResponse] | list[AssignmentStudentResponse]:
    records = _call(lambda: service.list_for(user, access_token=token))
    if user.role is Role.TEACHER:
        return [teacher_view(record) for record in records]
    return [student_view(record) for record in records]


@router.get(
    "/{assignment_id}",
    response_model=AssignmentTeacherResponse | AssignmentStudentResponse,
    summary="Get an assignment",
    description=(
        f"{AUTH_HEADER_DOC}\n\n"
        "Teachers can read their own assignments (with answers). Students can read published "
        "assignments they can access (without answers). Anything else returns 404."
    ),
    responses=ERROR_RESPONSES,
)
def get_assignment(
    assignment_id: UUID, user: AnyUser, token: AccessToken, service: Service
) -> AssignmentTeacherResponse | AssignmentStudentResponse:
    record = _call(lambda: service.get_for(user, assignment_id, access_token=token))
    return _view_for(user, record)


@router.patch(
    "/{assignment_id}",
    response_model=AssignmentTeacherResponse,
    summary="Update an assignment (owning teacher)",
    description=(
        f"{AUTH_HEADER_DOC} Owning teacher only.\n\n"
        "Partial update; works for drafts and published assignments alike. The resulting assignment "
        "is re-validated as a whole. `questions`, when given, replaces the full question list; "
        "existing questions are updated in place by position so student answers stay attached. "
        "Removing a question students have already answered returns 409. A published assignment "
        "cannot be left without questions. A new `due_at` must be in the future. "
        "`status`, `id` and `teacher_id` cannot be changed here."
    ),
    responses={
        **ERROR_RESPONSES,
        409: {"model": ErrorResponse, "description": "A removed question already has student answers."},
        422: {"description": "Invalid update or resulting assignment."},
    },
)
def update_assignment(
    assignment_id: UUID, payload: AssignmentUpdate, teacher: TeacherUser, token: AccessToken, service: Service
) -> AssignmentTeacherResponse:
    record = _call(lambda: service.update(teacher, assignment_id, payload, access_token=token))
    return teacher_view(record)


@router.delete(
    "/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete an assignment (owning teacher)",
    description=(
        f"{AUTH_HEADER_DOC} Owning teacher only.\n\n"
        "Policy pending: the archive-vs-delete rule for assignments with submissions is not decided "
        "yet. If storage refuses the deletion because the assignment is in use, 409 is returned."
    ),
    responses={**ERROR_RESPONSES, 409: {"model": ErrorResponse, "description": "Assignment is in use."}},
)
def delete_assignment(assignment_id: UUID, teacher: TeacherUser, token: AccessToken, service: Service) -> Response:
    _call(lambda: service.delete(teacher, assignment_id, access_token=token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{assignment_id}/publish",
    response_model=AssignmentTeacherResponse,
    summary="Publish an assignment (owning teacher)",
    description=(
        f"{AUTH_HEADER_DOC} Owning teacher only.\n\n"
        "Makes the assignment visible to students. Requires at least one question and a due date in "
        "the future. Publishing an already-published assignment returns it unchanged."
    ),
    responses={**ERROR_RESPONSES, 422: {"model": ErrorResponse, "description": "Assignment is not publishable."}},
)
def publish_assignment(
    assignment_id: UUID, teacher: TeacherUser, token: AccessToken, service: Service
) -> AssignmentTeacherResponse:
    record = _call(lambda: service.publish(teacher, assignment_id, access_token=token))
    return teacher_view(record)


@router.post(
    "/{assignment_id}/unpublish",
    response_model=AssignmentTeacherResponse,
    summary="Unpublish an assignment (owning teacher)",
    description=(
        f"{AUTH_HEADER_DOC} Owning teacher only.\n\n"
        "Returns the assignment to draft so students can no longer see it. Unpublishing a draft "
        "returns it unchanged."
    ),
    responses=ERROR_RESPONSES,
)
def unpublish_assignment(
    assignment_id: UUID, teacher: TeacherUser, token: AccessToken, service: Service
) -> AssignmentTeacherResponse:
    record = _call(lambda: service.unpublish(teacher, assignment_id, access_token=token))
    return teacher_view(record)
