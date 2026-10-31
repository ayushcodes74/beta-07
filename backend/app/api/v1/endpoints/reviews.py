"""Teacher review queue and student review (re-evaluation) requests.

Endpoints:
  - GET   /reviews/queue                               (teacher) OCR / low-trust / student-request queues
  - GET   /review-requests                             (student: own; teacher: own assignments)
  - POST  /submissions/{submission_id}/review-requests (student) flag a published grade for review
  - PATCH /review-requests/{request_id}                (teacher) resolve or dismiss with a reply
"""

import logging
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.endpoints.submissions import ERROR_RESPONSES, _handle_error, get_submission_service
from app.core.dependencies import api_error, get_bearer_token, require_authenticated_user, require_student, require_teacher
from app.database.grading_repository import GradingRepositoryError, SupabaseGradingRepository
from app.database.review_request_repository import ReviewRequestRepositoryError, SupabaseReviewRequestRepository
from app.schemas.auth import ErrorResponse
from app.schemas.review import (
    ReviewQueueResponse,
    ReviewRequestCreate,
    ReviewRequestResolve,
    ReviewRequestResponse,
)
from app.services.auth_service import CurrentUser
from app.services.ocr_client import get_ocr_client
from app.services.review_service import ReviewConflictError, ReviewService
from app.services.submission_service import SubmissionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reviews"])

StudentUser = Annotated[CurrentUser, Depends(require_student)]
TeacherUser = Annotated[CurrentUser, Depends(require_teacher)]
AnyUser = Annotated[CurrentUser, Depends(require_authenticated_user)]
AccessToken = Annotated[str, Depends(get_bearer_token)]


def get_review_service(
    submissions: Annotated[SubmissionService, Depends(get_submission_service)],
    ocr_client=Depends(get_ocr_client),
) -> ReviewService:
    return ReviewService(submissions, SupabaseGradingRepository(), SupabaseReviewRequestRepository(), ocr_client)


Reviews = Annotated[ReviewService, Depends(get_review_service)]

REVIEW_ERROR_RESPONSES: dict[int | str, dict] = {
    **ERROR_RESPONSES,
    409: {"model": ErrorResponse, "description": "Review request already open or already closed."},
}


def _handle_review_error(exc: Exception) -> NoReturn:
    if isinstance(exc, ReviewConflictError):
        raise api_error(status.HTTP_409_CONFLICT, exc.code, exc.message) from None
    if isinstance(exc, (ReviewRequestRepositoryError, GradingRepositoryError)):
        logger.error("Review storage error: %s", exc)
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "storage_unavailable", "Review storage is unavailable."
        ) from None
    _handle_error(exc)


@router.get(
    "/reviews/queue",
    response_model=ReviewQueueResponse,
    summary="Teacher review queue",
    description=(
        "Owning teacher only. Submissions needing manual review, grouped as: OCR review (failed, degraded, "
        "warnings, or low OCR confidence), low trust score (unpublished AI grades with low confidence or a "
        "review flag), and open student review requests."
    ),
    responses=REVIEW_ERROR_RESPONSES,
)
async def get_review_queue(teacher: TeacherUser, token: AccessToken, reviews: Reviews) -> ReviewQueueResponse:
    try:
        return await reviews.build_queue(teacher, access_token=token)
    except Exception as exc:
        _handle_review_error(exc)


@router.get(
    "/review-requests",
    response_model=list[ReviewRequestResponse],
    summary="List review requests",
    description="Students receive their own requests; teachers receive requests on their own assignments.",
    responses=REVIEW_ERROR_RESPONSES,
)
async def list_review_requests(user: AnyUser, token: AccessToken, reviews: Reviews) -> list[ReviewRequestResponse]:
    try:
        return await reviews.list_requests(user, access_token=token)
    except Exception as exc:
        _handle_review_error(exc)


@router.post(
    "/submissions/{submission_id}/review-requests",
    response_model=ReviewRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a review of a published grade (student)",
    description="The submitting student flags a published grade for teacher review with a reason.",
    responses=REVIEW_ERROR_RESPONSES,
)
async def create_review_request(
    submission_id: UUID,
    body: ReviewRequestCreate,
    student: StudentUser,
    token: AccessToken,
    reviews: Reviews,
) -> ReviewRequestResponse:
    try:
        return await reviews.create_request(student, submission_id, body.reason, access_token=token)
    except Exception as exc:
        _handle_review_error(exc)


@router.patch(
    "/review-requests/{request_id}",
    response_model=ReviewRequestResponse,
    summary="Resolve or dismiss a student review request (teacher)",
    description=(
        "Owning teacher only. Closes an open request as resolved or dismissed, with an optional reply the "
        "student can read. To change the grade, re-publish it from the grading review page."
    ),
    responses=REVIEW_ERROR_RESPONSES,
)
async def resolve_review_request(
    request_id: UUID,
    body: ReviewRequestResolve,
    teacher: TeacherUser,
    token: AccessToken,
    reviews: Reviews,
) -> ReviewRequestResponse:
    try:
        return await reviews.resolve_request(
            teacher, request_id, body.status, body.teacher_response, access_token=token
        )
    except Exception as exc:
        _handle_review_error(exc)
