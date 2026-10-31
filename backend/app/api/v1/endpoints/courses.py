"""Course management endpoints (Module 2A).

Teachers create, update, and manage course rosters. Students list their
enrolled courses and view details of courses they are actively enrolled in.
"""

from collections.abc import Callable
import logging
from typing import Annotated, NoReturn, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.v1.endpoints.auth import AUTH_ERROR_RESPONSES
from app.core.dependencies import (
    api_error,
    get_bearer_token,
    require_authenticated_user,
    require_teacher,
)
from app.schemas.auth import ErrorResponse
from app.schemas.course import (
    CourseCreate,
    CourseResponse,
    CourseStudentResponse,
    CourseUpdate,
    EnrollmentCreate,
    EnrollmentResponse,
)
from app.services.auth_service import CurrentUser
from app.services.course_service import (
    CourseIntegrationNotConfiguredError,
    CourseNotFoundError,
    CoursePermissionError,
    CourseRecord,
    CourseRepository,
    CourseRepositoryError,
    CourseService,
    CourseValidationError,
    DuplicateEnrollmentError,
    EnrolledStudent,
    EnrollmentNotFoundError,
    EnrollmentRecord,
    InvalidEnrollmentTargetError,
    get_course_repository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["courses"])

TeacherUser = Annotated[CurrentUser, Depends(require_teacher)]
AnyUser = Annotated[CurrentUser, Depends(require_authenticated_user)]
AccessToken = Annotated[str, Depends(get_bearer_token)]

ERROR_RESPONSES: dict[int | str, dict] = {
    **AUTH_ERROR_RESPONSES,
    403: {"model": ErrorResponse, "description": "Role not allowed or permission denied."},
    404: {"model": ErrorResponse, "description": "Course or enrollment not found or not accessible."},
    409: {"model": ErrorResponse, "description": "Duplicate enrollment or conflict."},
    422: {"model": ErrorResponse, "description": "Validation error or invalid target student."},
    503: {"model": ErrorResponse, "description": "Course storage is unavailable."},
}


def get_course_service(
    repository: Annotated[CourseRepository, Depends(get_course_repository)],
) -> CourseService:
    return CourseService(repository)


Service = Annotated[CourseService, Depends(get_course_service)]


def _raise_http(exc: Exception) -> NoReturn:
    if isinstance(exc, CourseNotFoundError):
        raise api_error(status.HTTP_404_NOT_FOUND, "course_not_found", "Course not found.") from None
    if isinstance(exc, CoursePermissionError):
        raise api_error(
            status.HTTP_403_FORBIDDEN, "forbidden", "You do not have permission to perform this action."
        ) from None
    if isinstance(exc, CourseValidationError):
        raise api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code, exc.message) from None
    if isinstance(exc, DuplicateEnrollmentError):
        raise api_error(status.HTTP_409_CONFLICT, "duplicate_enrollment", str(exc)) from None
    if isinstance(exc, InvalidEnrollmentTargetError):
        raise api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code, exc.message) from None
    if isinstance(exc, EnrollmentNotFoundError):
        raise api_error(status.HTTP_404_NOT_FOUND, "enrollment_not_found", str(exc)) from None
    if isinstance(exc, CourseIntegrationNotConfiguredError):
        logger.error("Course integration is not configured yet")
    else:
        logger.error("Course repository failure: %s", type(exc).__name__)
    raise api_error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "course_service_unavailable",
        "Course service is temporarily unavailable.",
    ) from None


_HANDLED_ERRORS = (
    CourseNotFoundError,
    CoursePermissionError,
    CourseValidationError,
    DuplicateEnrollmentError,
    InvalidEnrollmentTargetError,
    EnrollmentNotFoundError,
    CourseIntegrationNotConfiguredError,
    CourseRepositoryError,
)

T = TypeVar("T")


def _call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except _HANDLED_ERRORS as exc:
        _raise_http(exc)


def course_view(record: CourseRecord) -> CourseResponse:
    words = [w for w in record.name.replace("-", " ").split() if w]
    code = "".join(w[0] for w in words[:4]).upper() if words else "CRS"
    return CourseResponse(
        id=record.id,
        teacher_id=record.teacher_id,
        name=record.name,
        description=record.description,
        created_at=record.created_at,
        code=code,
        instructor=record.instructor_name or "Course Instructor",
        students=record.students_count,
        assignments=0,
        activity=0,
        average=0.0,
    )


def enrollment_view(record: EnrollmentRecord) -> EnrollmentResponse:
    return EnrollmentResponse(
        id=record.id,
        course_id=record.course_id,
        student_id=record.student_id,
        status=record.status,
        enrolled_at=record.enrolled_at,
    )


def student_view(record: EnrolledStudent) -> CourseStudentResponse:
    return CourseStudentResponse(
        student_id=record.student_id,
        name=record.name,
        email=record.email,
        status=record.status,
        enrolled_at=record.enrolled_at,
    )


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CourseResponse,
    summary="Create a course (teacher)",
    description="Creates a new course owned by the authenticated teacher.",
    responses=ERROR_RESPONSES,
)
def create_course(
    payload: CourseCreate, teacher: TeacherUser, token: AccessToken, service: Service
) -> CourseResponse:
    record = _call(lambda: service.create(teacher, payload, access_token=token))
    return course_view(record)


@router.get(
    "",
    response_model=list[CourseResponse],
    summary="List courses",
    description="Teachers receive courses they own. Students receive courses in which they are actively enrolled.",
    responses=ERROR_RESPONSES,
)
def list_courses(user: AnyUser, token: AccessToken, service: Service) -> list[CourseResponse]:
    records = _call(lambda: service.list_for(user, access_token=token))
    return [course_view(r) for r in records]


@router.get(
    "/{course_id}",
    response_model=CourseResponse,
    summary="Get course details",
    description="Accessible to the course owner teacher or any actively enrolled student.",
    responses=ERROR_RESPONSES,
)
def get_course(course_id: UUID, user: AnyUser, token: AccessToken, service: Service) -> CourseResponse:
    record = _call(lambda: service.get_for(user, course_id, access_token=token))
    return course_view(record)


@router.patch(
    "/{course_id}",
    response_model=CourseResponse,
    summary="Update course (owning teacher)",
    description="Update name and description. Only permitted for the teacher who owns the course.",
    responses=ERROR_RESPONSES,
)
def update_course(
    course_id: UUID, payload: CourseUpdate, teacher: TeacherUser, token: AccessToken, service: Service
) -> CourseResponse:
    record = _call(lambda: service.update(teacher, course_id, payload, access_token=token))
    return course_view(record)


@router.post(
    "/{course_id}/enrollments",
    status_code=status.HTTP_201_CREATED,
    response_model=EnrollmentResponse,
    summary="Enroll student in course (owning teacher)",
    description="Enrolls a student in the course. Rejects duplicate active enrollments, disabled accounts, and teacher accounts.",
    responses=ERROR_RESPONSES,
)
def enroll_student(
    course_id: UUID, payload: EnrollmentCreate, teacher: TeacherUser, token: AccessToken, service: Service
) -> EnrollmentResponse:
    record = _call(lambda: service.enroll_student(teacher, course_id, payload.student_id, access_token=token))
    return enrollment_view(record)


@router.get(
    "/{course_id}/students",
    response_model=list[CourseStudentResponse],
    summary="List enrolled students (owning teacher)",
    description="Returns active enrolled students for the course roster.",
    responses=ERROR_RESPONSES,
)
def list_course_students(
    course_id: UUID, teacher: TeacherUser, token: AccessToken, service: Service
) -> list[CourseStudentResponse]:
    records = _call(lambda: service.list_students(teacher, course_id, access_token=token))
    return [student_view(r) for r in records]


@router.delete(
    "/{course_id}/enrollments/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Deactivate student enrollment (owning teacher)",
    description="Deactivates a student's enrollment in the course rather than deleting historical records.",
    responses=ERROR_RESPONSES,
)
def deactivate_student_enrollment(
    course_id: UUID, student_id: UUID, teacher: TeacherUser, token: AccessToken, service: Service
) -> Response:
    _call(lambda: service.deactivate_enrollment(teacher, course_id, student_id, access_token=token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

