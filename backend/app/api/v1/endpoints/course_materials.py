"""Course materials for RAG grading (teacher, course owner only).

  - POST   /courses/{course_id}/materials               upload + index notes (PDF/DOCX/PPTX/TXT; scans via OCR)
  - GET    /courses/{course_id}/materials               list indexed materials
  - DELETE /courses/{course_id}/materials/{material_id} remove a material from the index

Indexed passages are used as course evidence when the AI checks answers. Students cannot call
these endpoints, and answer keys are never stored here.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.v1.endpoints.auth import AUTH_ERROR_RESPONSES
from app.api.v1.endpoints.courses import get_course_service
from app.core.dependencies import api_error, get_bearer_token, require_teacher
from app.schemas.auth import ErrorResponse
from app.services.ai_generation_service import AIGenerationError, AIServiceUnavailableError, AITimeoutError
from app.services.auth_service import CurrentUser
from app.services.course_material_index_service import CourseMaterialIndexService, MaterialNotFoundError
from app.services.course_material_service import MAX_FILE_BYTES, MaterialExtractionError
from app.services.course_service import CourseNotFoundError, CourseRepositoryError, CourseService
from app.services.ocr_client import (
    OCRJobFailedError,
    OCRServiceUnavailableError,
    OCRTimeoutError,
    get_ocr_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["course materials"])

TeacherUser = Annotated[CurrentUser, Depends(require_teacher)]
AccessToken = Annotated[str, Depends(get_bearer_token)]


def get_material_index_service(ocr_client=Depends(get_ocr_client)) -> CourseMaterialIndexService:
    return CourseMaterialIndexService(ocr_client)


MaterialIndex = Annotated[CourseMaterialIndexService, Depends(get_material_index_service)]
Courses = Annotated[CourseService, Depends(get_course_service)]

ERROR_RESPONSES: dict[int | str, dict] = {
    **AUTH_ERROR_RESPONSES,
    403: {"model": ErrorResponse, "description": "Only teachers can manage course materials."},
    404: {"model": ErrorResponse, "description": "Course or material not found or not owned by you."},
    413: {"model": ErrorResponse, "description": "File larger than 25 MB."},
    415: {"model": ErrorResponse, "description": "Unsupported file type."},
    422: {"model": ErrorResponse, "description": "File unreadable, encrypted, or has no text."},
    503: {"model": ErrorResponse, "description": "AI Engine, embeddings, or OCR unavailable."},
    504: {"model": ErrorResponse, "description": "Indexing or OCR timed out."},
}


async def _require_owned_course(courses: CourseService, teacher: CurrentUser, course_id: UUID, token: str) -> None:
    try:
        await run_in_threadpool(courses.get_for, teacher, course_id, access_token=token)
    except CourseNotFoundError:
        raise api_error(status.HTTP_404_NOT_FOUND, "course_not_found", "Course not found.") from None
    except CourseRepositoryError:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "course_service_unavailable", "Course service is temporarily unavailable."
        ) from None


def _handle(exc: Exception) -> NoReturn:
    if isinstance(exc, MaterialExtractionError):
        code = {
            "file_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "unsupported_type": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        }.get(exc.code, status.HTTP_422_UNPROCESSABLE_CONTENT)
        raise api_error(code, exc.code, exc.message) from None
    if isinstance(exc, MaterialNotFoundError):
        raise api_error(status.HTTP_404_NOT_FOUND, "material_not_found", "Material not found in this course.") from None
    if isinstance(exc, (AITimeoutError, OCRTimeoutError)):
        raise api_error(status.HTTP_504_GATEWAY_TIMEOUT, "timeout", "Indexing took too long. Try a smaller file.") from None
    if isinstance(exc, OCRJobFailedError):
        raise api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "ocr_failed", "OCR could not read this PDF.") from None
    if isinstance(exc, (AIServiceUnavailableError, OCRServiceUnavailableError)):
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "rag_unavailable", f"Course material indexing is unavailable: {exc}"
        ) from None
    if isinstance(exc, AIGenerationError):
        logger.error("Course material indexing failed: %s", exc)
        raise api_error(status.HTTP_502_BAD_GATEWAY, "indexing_failed", "The AI Engine could not index this file.") from None
    logger.exception("Unexpected course material error: %s", exc)
    raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "An internal error occurred.") from None


@router.post(
    "/{course_id}/materials",
    summary="Upload course notes for RAG grading",
    description=(
        "Teacher (course owner) uploads notes/slides (PDF, DOCX, PPTX, TXT; scanned PDFs are OCR'd). The text is "
        "chunked, embedded and indexed for this course only. Uploading identical content again adds nothing."
    ),
    responses=ERROR_RESPONSES,
)
async def upload_course_material(
    course_id: UUID,
    teacher: TeacherUser,
    token: AccessToken,
    courses: Courses,
    index: MaterialIndex,
    file: UploadFile = File(..., description="Course material: PDF, DOCX, PPTX or TXT (max 25 MB)"),
) -> dict[str, Any]:
    await _require_owned_course(courses, teacher, course_id, token)
    data = await file.read(MAX_FILE_BYTES + 1)
    try:
        return await index.upload(str(course_id), file.filename or "material", data)
    except Exception as exc:
        _handle(exc)


@router.get(
    "/{course_id}/materials",
    summary="List indexed course materials",
    responses=ERROR_RESPONSES,
)
async def list_course_materials(
    course_id: UUID, teacher: TeacherUser, token: AccessToken, courses: Courses, index: MaterialIndex
) -> dict[str, Any]:
    await _require_owned_course(courses, teacher, course_id, token)
    try:
        return await index.list(str(course_id))
    except Exception as exc:
        _handle(exc)


@router.delete(
    "/{course_id}/materials/{material_id}",
    summary="Remove a course material from the RAG index",
    responses=ERROR_RESPONSES,
)
async def delete_course_material(
    course_id: UUID,
    material_id: str,
    teacher: TeacherUser,
    token: AccessToken,
    courses: Courses,
    index: MaterialIndex,
) -> dict[str, Any]:
    await _require_owned_course(courses, teacher, course_id, token)
    try:
        return await index.delete(str(course_id), material_id)
    except Exception as exc:
        _handle(exc)
