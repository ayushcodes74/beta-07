"""AI-assisted assignment drafting.

Returns suggested questions for the teacher's editor. Nothing is persisted here;
the teacher reviews/edits the draft and saves it through POST /assignments.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.api.v1.endpoints.auth import AUTH_ERROR_RESPONSES
from app.core.dependencies import api_error, require_teacher
from app.schemas.ai_generation import (
    AssignmentGenerationRequest,
    ExtractedCourseMaterial,
    GeneratedAssignmentDraft,
)
from app.schemas.auth import ErrorResponse
from app.services.course_material_service import (
    MAX_FILE_BYTES,
    MaterialExtractionError,
    extract_course_material,
)
from app.services.ai_generation_service import (
    AIGenerationError,
    AIGenerationService,
    AIRateLimitedError,
    AIServiceUnavailableError,
    AITimeoutError,
    get_ai_generation_service,
)
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.post(
    "/generate-ai",
    response_model=GeneratedAssignmentDraft,
    summary="Draft assignment questions with AI (teachers only; not saved)",
    responses={
        **AUTH_ERROR_RESPONSES,
        403: {"model": ErrorResponse, "description": "Only teachers can generate assignments."},
        429: {"model": ErrorResponse, "description": "AI provider rate limit reached; retry later."},
        502: {"model": ErrorResponse, "description": "AI provider returned an unusable response."},
        503: {"model": ErrorResponse, "description": "AI generation is unavailable or not configured."},
        504: {"model": ErrorResponse, "description": "AI generation timed out."},
    },
)
async def generate_assignment_draft(
    body: AssignmentGenerationRequest,
    _teacher: Annotated[CurrentUser, Depends(require_teacher)],
    service: Annotated[AIGenerationService, Depends(get_ai_generation_service)],
) -> GeneratedAssignmentDraft:
    try:
        return await service.generate(body)
    except AIServiceUnavailableError:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "ai_unavailable", "AI generation is currently unavailable."
        ) from None
    except AIRateLimitedError:
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS, "ai_rate_limited", "AI generation is busy. Try again in a minute."
        ) from None
    except AITimeoutError:
        raise api_error(
            status.HTTP_504_GATEWAY_TIMEOUT, "ai_timeout", "AI generation took too long. Try fewer questions."
        ) from None
    except AIGenerationError:
        raise api_error(
            status.HTTP_502_BAD_GATEWAY, "ai_generation_failed", "AI generation failed. Try again."
        ) from None


@router.post(
    "/materials/extract",
    response_model=ExtractedCourseMaterial,
    summary="Extract text from course material attached while creating an assignment (teachers only; not saved)",
    description=(
        "Accepts a PDF, DOCX, PPTX or TXT file and returns its text, which the editor then sends as "
        "`course_material` to POST /assignments/generate-ai. The file and text are not stored."
    ),
    responses={
        **AUTH_ERROR_RESPONSES,
        403: {"model": ErrorResponse, "description": "Only teachers can attach course material."},
        413: {"model": ErrorResponse, "description": "File larger than 25 MB."},
        415: {"model": ErrorResponse, "description": "Unsupported file type."},
        422: {"model": ErrorResponse, "description": "File unreadable, encrypted, or has no text."},
    },
)
async def extract_material(
    _teacher: Annotated[CurrentUser, Depends(require_teacher)],
    file: UploadFile = File(..., description="Course material: PDF, DOCX, PPTX or TXT (max 25 MB)"),
) -> ExtractedCourseMaterial:
    data = await file.read(MAX_FILE_BYTES + 1)  # bounded read: never buffer more than the limit
    try:
        # PDF/XML parsing is CPU-bound; keep it off the event loop.
        result = await run_in_threadpool(extract_course_material, file.filename or "material", data)
    except MaterialExtractionError as exc:
        status_code = {
            "file_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "unsupported_type": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        }.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        raise api_error(status_code, exc.code, exc.message) from None
    return ExtractedCourseMaterial(
        filename=result.filename,
        text=result.text,
        characters=result.characters,
        truncated=result.truncated,
        pages=result.pages,
    )
