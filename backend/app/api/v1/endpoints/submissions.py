"""Submission and OCR Integration Endpoints (Module 5 Backend Integration).

Endpoints:
  - POST /assignments/{assignment_id}/submissions (Students upload assignment PDF)
  - GET /submissions/{submission_id}/status (Authorized status check and OCR polling)
  - GET /submissions/{submission_id}/ocr-result (Authorized structured OCR result retrieval; returns 202 while processing)
  - DELETE /submissions/{submission_id}/ocr-job (Authorized cancellation and cleanup of OCR processing)

Privacy Convention:
  - Unauthorized access attempts to another student's submission or another teacher's
    course assignment return 404, never revealing the existence of the resource.
"""

import logging
from typing import Annotated, Any, NoReturn, Union
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.v1.endpoints.assignments import get_assignment_service
from app.api.v1.endpoints.auth import AUTH_ERROR_RESPONSES
from app.core.dependencies import (
    api_error,
    get_bearer_token,
    require_authenticated_user,
    require_student,
    require_teacher,
)
from app.schemas.auth import ErrorResponse
from app.database.grading_repository import GradingRepositoryError
from app.schemas.grading import GradePublishRequest, GradingSuggestionResponse, PublishedGradeResponse
from app.schemas.integrity import IntegrityReport
from app.schemas.ocr import (
    JobStatusResponse,
    OCRDocumentResult,
    SubmissionOCRStatusResponse,
)
from app.services.assignment_service import (
    AssignmentNotFoundError,
    AssignmentRepositoryError,
    AssignmentService,
)
from app.services.ai_generation_service import (
    AIGenerationError,
    AIRateLimitedError,
    AIServiceUnavailableError,
    AITimeoutError,
)
from app.services.auth_service import CurrentUser
from app.services.grading_service import GradingService
from app.services.ocr_client import (
    OCRInvalidFileError,
    OCRJobCancelledError,
    OCRJobFailedError,
    OCRJobNotFoundError,
    OCRServiceUnavailableError,
    OCRTimeoutError,
    get_ocr_client,
)
from app.services.submission_service import (
    SubmissionIntegrationNotConfiguredError,
    SubmissionNotFoundError,
    SubmissionPermissionError,
    SubmissionRepository,
    SubmissionRepositoryError,
    SubmissionService,
    SubmissionValidationError,
    get_submission_repository,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["submissions"])

StudentUser = Annotated[CurrentUser, Depends(require_student)]
TeacherUser = Annotated[CurrentUser, Depends(require_teacher)]
AnyUser = Annotated[CurrentUser, Depends(require_authenticated_user)]
AccessToken = Annotated[str, Depends(get_bearer_token)]


def get_submission_service(
    repo: Annotated[SubmissionRepository, Depends(get_submission_repository)],
    assignment_service: Annotated[AssignmentService, Depends(get_assignment_service)],
    ocr_client=Depends(get_ocr_client),
) -> SubmissionService:
    return SubmissionService(repo, assignment_service, ocr_client)


Service = Annotated[SubmissionService, Depends(get_submission_service)]

ERROR_RESPONSES: dict[int | str, dict] = {
    **AUTH_ERROR_RESPONSES,
    400: {"model": ErrorResponse, "description": "Invalid submission PDF or OCR failure."},
    403: {"model": ErrorResponse, "description": "Permission denied for this role."},
    404: {"model": ErrorResponse, "description": "Assignment or submission not found or not accessible."},
    422: {"model": ErrorResponse, "description": "Validation error."},
    503: {"model": ErrorResponse, "description": "Database or OCR service unavailable."},
    504: {"model": ErrorResponse, "description": "OCR service timeout."},
}


def _handle_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (SubmissionNotFoundError, AssignmentNotFoundError, OCRJobNotFoundError)):
        raise api_error(status.HTTP_404_NOT_FOUND, "not_found", "Requested resource was not found.") from None
    if isinstance(exc, AssignmentRepositoryError):
        logger.error("Assignment repository error: %s", type(exc).__name__)
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "storage_unavailable", "Storage service unavailable.") from None
    if isinstance(exc, SubmissionPermissionError):
        raise api_error(status.HTTP_403_FORBIDDEN, "forbidden", "You do not have permission for this action.") from None
    if isinstance(exc, SubmissionValidationError):
        raise api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code, exc.message) from None
    if isinstance(exc, OCRInvalidFileError):
        raise api_error(status.HTTP_400_BAD_REQUEST, "invalid_pdf", str(exc)) from None
    if isinstance(exc, OCRJobFailedError):
        raise api_error(status.HTTP_400_BAD_REQUEST, "ocr_job_failed", str(exc)) from None
    if isinstance(exc, OCRJobCancelledError):
        raise api_error(status.HTTP_400_BAD_REQUEST, "ocr_job_cancelled", str(exc)) from None
    if isinstance(exc, OCRTimeoutError):
        raise api_error(status.HTTP_504_GATEWAY_TIMEOUT, "ocr_timeout", "OCR service request timed out.") from None
    if isinstance(exc, (OCRServiceUnavailableError, SubmissionIntegrationNotConfiguredError)):
        logger.error("Service unavailable: %s", type(exc).__name__)
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "service_unavailable", "Service temporarily unavailable.") from None
    if isinstance(exc, SubmissionRepositoryError):
        logger.error("Submission repository error: %s", type(exc).__name__)
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "storage_unavailable", "Storage service unavailable.") from None

    logger.exception("Unexpected error in submission endpoint: %s", exc)
    raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "An internal error occurred.") from None


@router.post(
    "/assignments/{assignment_id}/submissions",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmissionOCRStatusResponse,
    summary="Submit assignment PDF (students only)",
    description=(
        "Enrolled students upload a PDF containing handwritten/printed assignment answers. "
        "The submission is validated and queued for OCR processing."
    ),
    responses=ERROR_RESPONSES,
)
async def submit_assignment(
    assignment_id: UUID,
    student: StudentUser,
    token: AccessToken,
    service: Service,
    file: UploadFile = File(..., description="Student scanned answer PDF"),
) -> SubmissionOCRStatusResponse:
    try:
        content = await file.read()
        filename = file.filename or "submission.pdf"
        record = await service.submit_assignment_pdf(
            student=student,
            assignment_id=assignment_id,
            filename=filename,
            file_bytes=content,
            access_token=token,
        )
        return await service.get_submission_status(student, record.id, access_token=token)
    except Exception as exc:
        _handle_error(exc)


@router.get(
    "/submissions",
    response_model=list[SubmissionOCRStatusResponse],
    summary="List accessible submissions",
    description="Students receive their own submissions; teachers receive submissions for assignments they own.",
    responses=ERROR_RESPONSES,
)
def list_submissions(
    user: AnyUser,
    token: AccessToken,
    service: Service,
) -> list[SubmissionOCRStatusResponse]:
    try:
        records = service.list_submissions(user, access_token=token)
        return [
            SubmissionOCRStatusResponse(
                submission_id=record.id,
                assignment_id=record.assignment_id,
                student_id=record.student_id,
                status=record.status,
                ocr_job_id=record.ocr_job_id,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record in records
        ]
    except Exception as exc:
        _handle_error(exc)


@router.get(
    "/submissions/{submission_id}/status",
    response_model=SubmissionOCRStatusResponse,
    summary="Get submission status and OCR progress",
    description="Check submission lifecycle and live OCR stage progress. Enforces strict student/teacher authorization.",
    responses=ERROR_RESPONSES,
)
async def get_submission_status(
    submission_id: UUID,
    user: AnyUser,
    token: AccessToken,
    service: Service,
) -> SubmissionOCRStatusResponse:
    try:
        return await service.get_submission_status(user, submission_id, access_token=token)
    except Exception as exc:
        _handle_error(exc)


@router.get(
    "/submissions/{submission_id}/ocr-result",
    response_model=OCRDocumentResult,
    summary="Get structured OCR document result",
    description="Retrieve completed OCR results (pages, text blocks, math formulas, quality scores). Returns 202 while processing.",
    responses={
        **ERROR_RESPONSES,
        202: {"description": "OCR processing still underway."},
    },
)
async def get_submission_ocr_result(
    submission_id: UUID,
    user: AnyUser,
    token: AccessToken,
    service: Service,
) -> Any:
    try:
        res = await service.get_submission_ocr_result(user, submission_id, access_token=token)
        if isinstance(res, JobStatusResponse):
            # Processing still underway: return 202 Accepted without parsing as completed result
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "job_id": res.job_id,
                    "status": res.status,
                    "stage": res.stage,
                    "progress": res.progress,
                    "message": f"OCR processing is currently in stage '{res.stage}' ({res.progress}%). Retry shortly.",
                },
            )
        return res
    except Exception as exc:
        _handle_error(exc)


@router.get(
    "/submissions/{submission_id}/integrity",
    response_model=IntegrityReport,
    summary="Compare submission text with same-assignment submissions",
    description=(
        "Teacher-only, request-time comparison of OCR passages from submissions for the same assignment. "
        "Similarity is review evidence, not a misconduct finding. No external web search is performed."
    ),
    responses=ERROR_RESPONSES,
)
async def get_submission_integrity(
    submission_id: UUID,
    teacher: TeacherUser,
    token: AccessToken,
    service: Service,
) -> IntegrityReport:
    try:
        return await service.analyze_submission_integrity(teacher, submission_id, access_token=token)
    except Exception as exc:
        _handle_error(exc)


def get_grading_service(
    repo: Annotated[SubmissionRepository, Depends(get_submission_repository)],
    assignment_service: Annotated[AssignmentService, Depends(get_assignment_service)],
    ocr_client=Depends(get_ocr_client),
) -> GradingService:
    from app.database.grading_repository import SupabaseGradingRepository

    return GradingService(repo, assignment_service, ocr_client, SupabaseGradingRepository())


Grading = Annotated[GradingService, Depends(get_grading_service)]


def _handle_grading_error(exc: Exception) -> NoReturn:
    if isinstance(exc, AIRateLimitedError):
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS, "ai_rate_limited", "AI providers are rate limited. Try again shortly."
        ) from None
    if isinstance(exc, AITimeoutError):
        raise api_error(status.HTTP_504_GATEWAY_TIMEOUT, "ai_timeout", "AI answer check took too long. Try again.") from None
    if isinstance(exc, AIServiceUnavailableError):
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "ai_unavailable", "The AI Engine is unavailable or not configured."
        ) from None
    if isinstance(exc, AIGenerationError):
        logger.error("AI grading failed: %s", exc)
        raise api_error(status.HTTP_502_BAD_GATEWAY, "ai_failed", "The AI Engine could not check the answers.") from None
    if isinstance(exc, GradingRepositoryError):
        logger.error("Grading storage error: %s", exc)
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "storage_unavailable", "Grade storage is unavailable."
        ) from None
    _handle_error(exc)


@router.post(
    "/submissions/{submission_id}/grade",
    response_model=GradingSuggestionResponse,
    summary="AI answer check against the teacher's answer keys",
    description=(
        "Teacher-only. Compares the submission's OCR text with each question's answer key via the AI Engine "
        "and returns suggested marks and feedback per question. Stored as a pending-review suggestion; "
        "never published to the student by this call."
    ),
    responses={
        **ERROR_RESPONSES,
        429: {"model": ErrorResponse, "description": "AI providers rate limited."},
        502: {"model": ErrorResponse, "description": "AI Engine failed."},
    },
)
async def grade_submission(
    submission_id: UUID,
    teacher: TeacherUser,
    token: AccessToken,
    grading: Grading,
) -> GradingSuggestionResponse:
    try:
        return await grading.grade_submission(teacher, submission_id, access_token=token)
    except Exception as exc:
        _handle_grading_error(exc)


@router.get(
    "/submissions/{submission_id}/grading",
    response_model=GradingSuggestionResponse,
    summary="Last stored AI answer check",
    description="Teacher-only. Returns the last stored answer-check suggestion, or 404 if none exists yet.",
    responses=ERROR_RESPONSES,
)
async def get_submission_grading(
    submission_id: UUID,
    teacher: TeacherUser,
    token: AccessToken,
    grading: Grading,
) -> GradingSuggestionResponse:
    try:
        saved = await grading.get_saved_suggestion(teacher, submission_id, access_token=token)
    except Exception as exc:
        _handle_grading_error(exc)
    if saved is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "not_found", "No answer check has been run for this submission yet.")
    return saved


@router.post(
    "/submissions/{submission_id}/grading/publish",
    response_model=PublishedGradeResponse,
    summary="Approve and publish the final grade (teacher only)",
    description=(
        "Owning teacher only. Stores the teacher's final score and feedback as approved and publishes it, "
        "making it visible to the student. The AI suggestion, if any, is kept as evidence and is never "
        "shown to the student. Calling again replaces the published grade."
    ),
    responses=ERROR_RESPONSES,
)
async def publish_submission_grade(
    submission_id: UUID,
    body: GradePublishRequest,
    teacher: TeacherUser,
    token: AccessToken,
    grading: Grading,
) -> PublishedGradeResponse:
    try:
        return await grading.publish_grade(
            teacher, submission_id, body.final_score, body.final_feedback, access_token=token
        )
    except Exception as exc:
        _handle_grading_error(exc)


@router.get(
    "/submissions/{submission_id}/result",
    response_model=PublishedGradeResponse,
    summary="Published grade for a submission",
    description=(
        "The submitting student or the owning teacher. Returns only a published grade (final score and "
        "teacher feedback); 404 if the grade has not been published."
    ),
    responses=ERROR_RESPONSES,
)
async def get_submission_result(
    submission_id: UUID,
    user: AnyUser,
    token: AccessToken,
    grading: Grading,
) -> PublishedGradeResponse:
    try:
        result = await grading.get_published_grade(user, submission_id, access_token=token)
    except Exception as exc:
        _handle_grading_error(exc)
    if result is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "not_found", "No published grade for this submission.")
    return result


@router.delete(
    "/submissions/{submission_id}/ocr-job",
    summary="Cancel OCR processing job",
    description="Cancel active or queued OCR processing job for this submission.",
    responses=ERROR_RESPONSES,
)
async def cancel_submission_ocr_job(
    submission_id: UUID,
    user: AnyUser,
    token: AccessToken,
    service: Service,
) -> dict:
    try:
        return await service.cancel_submission_ocr_job(user, submission_id, access_token=token)
    except Exception as exc:
        _handle_error(exc)
