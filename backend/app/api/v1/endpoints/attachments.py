"""Files attached to assignment questions (pictures / PDFs).

  - POST   /assignments/{assignment_id}/questions/{question_number}/attachments  (owning teacher) upload
  - GET    /assignments/{assignment_id}/attachments                               (teacher or enrolled student)
  - DELETE /assignments/{assignment_id}/attachments/{attachment_id}               (owning teacher)

Students see the files under each question; the files' text (extracted with the OCR pipeline after
upload) is given to the AI as that question's material when checking answers.
"""

import logging
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.api.v1.endpoints.assignments import _HANDLED_ERRORS, _raise_http, get_assignment_service
from app.api.v1.endpoints.auth import AUTH_ERROR_RESPONSES
from app.core.dependencies import api_error, get_bearer_token, require_authenticated_user, require_teacher
from app.database.attachment_repository import AttachmentRepositoryError, SupabaseAttachmentRepository
from app.schemas.attachment import AttachmentResponse
from app.schemas.auth import ErrorResponse
from app.services.assignment_service import AssignmentService
from app.services.attachment_service import (
    MAX_FILE_BYTES,
    AttachmentNotFoundError,
    AttachmentService,
    AttachmentValidationError,
)
from app.services.auth_service import CurrentUser
from app.services.ocr_client import get_ocr_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assignments", tags=["assignment attachments"])

TeacherUser = Annotated[CurrentUser, Depends(require_teacher)]
AnyUser = Annotated[CurrentUser, Depends(require_authenticated_user)]
AccessToken = Annotated[str, Depends(get_bearer_token)]


def get_attachment_repository():
    return SupabaseAttachmentRepository()


def get_attachment_service(
    assignments: Annotated[AssignmentService, Depends(get_assignment_service)],
    repository=Depends(get_attachment_repository),
    ocr_client=Depends(get_ocr_client),
) -> AttachmentService:
    return AttachmentService(repository, assignments, ocr_client)


Attachments = Annotated[AttachmentService, Depends(get_attachment_service)]

ERROR_RESPONSES: dict[int | str, dict] = {
    **AUTH_ERROR_RESPONSES,
    404: {"model": ErrorResponse, "description": "Assignment or file not found / not accessible."},
    413: {"model": ErrorResponse, "description": "File larger than 10 MB."},
    422: {"model": ErrorResponse, "description": "Unsupported file, invalid question or too many files."},
    503: {"model": ErrorResponse, "description": "File storage unavailable (is phase3e applied?)."},
}


def _handle(exc: Exception) -> NoReturn:
    if isinstance(exc, AttachmentValidationError):
        code = {"file_too_large": status.HTTP_413_CONTENT_TOO_LARGE, "forbidden": status.HTTP_403_FORBIDDEN}.get(
            exc.code, status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise api_error(code, exc.code, exc.message) from None
    if isinstance(exc, AttachmentNotFoundError):
        raise api_error(status.HTTP_404_NOT_FOUND, "attachment_not_found", "File not found.") from None
    if isinstance(exc, AttachmentRepositoryError):
        logger.error("Attachment storage error: %s", exc)
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "attachments_unavailable",
            "File attachments are not available yet. Ask the administrator to apply phase3e_assignment_attachments.sql.",
        ) from None
    if isinstance(exc, _HANDLED_ERRORS):
        _raise_http(exc)
    raise exc


@router.post(
    "/{assignment_id}/questions/{question_number}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a picture or PDF to a question (teacher)",
    description=(
        "Owning teacher only. PDF, PNG, JPG or WEBP up to 10 MB, at most 5 per question. The file's text is "
        "extracted in the background (OCR for pictures and scans) and used as the question's material when "
        "the AI checks answers."
    ),
    responses=ERROR_RESPONSES,
)
async def upload_attachment(
    assignment_id: UUID,
    question_number: int,
    teacher: TeacherUser,
    token: AccessToken,
    attachments: Attachments,
    background: BackgroundTasks,
    file: UploadFile = File(..., description="PDF or picture"),
) -> AttachmentResponse:
    try:
        data = await file.read(MAX_FILE_BYTES + 1)
        record = await attachments.upload(
            teacher, assignment_id, question_number, file.filename or "attachment", data, access_token=token
        )
    except Exception as exc:
        _handle(exc)
    background.add_task(attachments.extract_text, record, data, access_token=token)
    return AttachmentResponse(
        id=record.id,
        assignment_id=record.assignment_id,
        question_number=record.question_number,
        filename=record.filename,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        extraction_status=record.extraction_status,
        created_at=record.created_at,
    )


@router.get(
    "/{assignment_id}/attachments",
    response_model=list[AttachmentResponse],
    summary="List the files attached to an assignment's questions",
    description="Owning teacher, or a student enrolled in the course of the published assignment. URLs expire after 15 minutes.",
    responses=ERROR_RESPONSES,
)
async def list_attachments(
    assignment_id: UUID, user: AnyUser, token: AccessToken, attachments: Attachments
) -> list[AttachmentResponse]:
    try:
        return await attachments.list_for(user, assignment_id, access_token=token)
    except Exception as exc:
        _handle(exc)


class AttachmentMove(BaseModel):
    question_number: int = Field(ge=1, le=200)


@router.patch(
    "/{assignment_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Move a file to another question (teacher)",
    description="Used when the teacher reorders or removes questions, so files stay with their question.",
    responses=ERROR_RESPONSES,
)
async def move_attachment(
    assignment_id: UUID,
    attachment_id: UUID,
    body: AttachmentMove,
    teacher: TeacherUser,
    token: AccessToken,
    attachments: Attachments,
) -> Response:
    try:
        await attachments.move(teacher, assignment_id, attachment_id, body.question_number, access_token=token)
    except Exception as exc:
        _handle(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{assignment_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a file from a question (teacher)",
    responses=ERROR_RESPONSES,
)
async def delete_attachment(
    assignment_id: UUID, attachment_id: UUID, teacher: TeacherUser, token: AccessToken, attachments: Attachments
) -> Response:
    try:
        await attachments.delete(teacher, assignment_id, attachment_id, access_token=token)
    except Exception as exc:
        _handle(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
