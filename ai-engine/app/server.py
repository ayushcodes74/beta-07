"""HTTP wrapper exposing AI Engine services to the TrustGrade backend.

The backend cannot import this package directly (both projects use the top-level
package name ``app``), so the AI Engine runs as a small internal service, the same
way the OCR Engine does. Bind it to localhost only; it has no authentication of its
own and relies on the backend to authenticate and authorize teachers.

Run from the ai-engine directory:
    uvicorn app.server:app --host 127.0.0.1 --port 8002
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import Field

from app.assignment.generator import AssignmentGenerator
from app.config import get_settings
from app.llm.gemini_client import (
    LLMAPIError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.schemas.assignment import AssignmentDraft, AssignmentGenerationRequest

logger = logging.getLogger("ai_engine.server")

app = FastAPI(
    title="TrustGrade AI Engine",
    description="Internal service: assignment generation for the TrustGrade backend.",
    version="1.0.0",
)


class GenerateAssignmentRequest(AssignmentGenerationRequest):
    """Generation request, optionally with course material text to ground questions in."""

    course_materials: Optional[str] = Field(
        default=None,
        max_length=200_000,
        description="Optional course text. Without it, questions are generated from the topic alone.",
    )


_generator: Optional[AssignmentGenerator] = None


def get_generator() -> AssignmentGenerator:
    """Lazily create the generator so the service starts even before Gemini is configured."""
    global _generator
    if _generator is None:
        _generator = AssignmentGenerator()
    return _generator


@app.get("/health")
def health() -> dict:
    configured = bool((get_settings().gemini_api_key or "").strip())
    return {
        "status": "ok" if configured else "degraded",
        "gemini_configured": configured,
        "model": get_settings().gemini_model,
    }


@app.post("/v1/assignments/generate", response_model=AssignmentDraft)
def generate_assignment(request: GenerateAssignmentRequest) -> AssignmentDraft:
    # Sync handler: FastAPI runs it in a worker thread, so slow Gemini calls don't block the loop.
    generation_request = AssignmentGenerationRequest.model_validate(
        request.model_dump(exclude={"course_materials"})
    )
    try:
        return get_generator().generate_assignment(generation_request, course_materials=request.course_materials)
    except LLMConfigError as exc:
        logger.error("Gemini is not configured: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI generation is not configured.") from None
    except LLMRateLimitError:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "AI provider rate limit reached.") from None
    except LLMTimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "AI provider timed out.") from None
    except LLMResponseValidationError:
        logger.warning("Gemini returned output that failed schema validation")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI provider returned an unusable response.") from None
    except (LLMAPIError, LLMError) as exc:
        logger.error("Gemini request failed: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI provider request failed.") from None
