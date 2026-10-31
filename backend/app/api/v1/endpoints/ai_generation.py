"""AI-assisted assignment drafting.

Returns suggested questions for the teacher's editor. Nothing is persisted here;
the teacher reviews/edits the draft and saves it through POST /assignments.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.endpoints.auth import AUTH_ERROR_RESPONSES
from app.core.dependencies import api_error, require_teacher
from app.schemas.ai_generation import AssignmentGenerationRequest, GeneratedAssignmentDraft
from app.schemas.auth import ErrorResponse
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
