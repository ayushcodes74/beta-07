"""Client for the AI Engine's assignment generator and mapping into editor-ready drafts."""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.ai_generation import (
    AssignmentGenerationRequest,
    GeneratedAssignmentDraft,
    GeneratedQuestion,
)

logger = logging.getLogger(__name__)

# The AI Engine requires a course id, but nothing is retrieved by it yet (no course
# material storage), so a fixed label avoids sending real identifiers for no benefit.
_UNSCOPED_COURSE = "unscoped"

_FORMATS = {"mixed": "MIXED", "subjective": "SUBJECTIVE", "mcq": "MCQ"}
_DIFFICULTIES = {"easy": "EASY", "medium": "MEDIUM", "hard": "HARD", "mixed": "MEDIUM"}


class AIGenerationError(Exception):
    """AI generation failed in a way the caller cannot fix by changing the request."""


class AIServiceUnavailableError(AIGenerationError):
    """AI Engine is not running, not configured, or unreachable."""


class AIRateLimitedError(AIGenerationError):
    """The AI provider rate-limited the request."""


class AITimeoutError(AIGenerationError):
    """The AI Engine or provider took too long."""


class AIGenerationService:
    def __init__(self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = (base_url or settings.AI_SERVICE_URL).rstrip("/")
        self.timeout = httpx.Timeout(settings.AI_READ_TIMEOUT_SECONDS, connect=settings.AI_CONNECT_TIMEOUT_SECONDS)
        self._transport = transport

    async def generate(self, request: AssignmentGenerationRequest) -> GeneratedAssignmentDraft:
        payload = _engine_payload(request)
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout, transport=self._transport
            ) as client:
                response = await client.post("/v1/assignments/generate", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            logger.error("AI Engine unreachable: %s", type(exc).__name__)
            raise AIServiceUnavailableError("AI Engine is unreachable") from exc
        except httpx.TimeoutException as exc:
            raise AITimeoutError("AI Engine timed out") from exc
        except httpx.HTTPError as exc:
            logger.error("AI Engine request failed: %s", type(exc).__name__)
            raise AIServiceUnavailableError("AI Engine request failed") from exc

        if response.status_code == 503:
            raise AIServiceUnavailableError("AI generation is not configured")
        if response.status_code == 429:
            raise AIRateLimitedError("AI provider rate limit reached")
        if response.status_code == 504:
            raise AITimeoutError("AI provider timed out")
        if response.status_code != 200:
            logger.error("AI Engine returned status %d", response.status_code)
            raise AIGenerationError(f"AI Engine returned status {response.status_code}")

        try:
            return map_engine_draft(response.json(), request.total_marks)
        except (ValueError, KeyError, TypeError) as exc:
            logger.error("AI Engine response could not be mapped: %s", type(exc).__name__)
            raise AIGenerationError("AI Engine returned an unexpected response") from exc


def get_ai_generation_service() -> AIGenerationService:
    return AIGenerationService()


# --------------------------------------------------------------------------
# Request / response mapping
# --------------------------------------------------------------------------


def _engine_payload(request: AssignmentGenerationRequest) -> dict[str, Any]:
    notes = [request.instructions] if request.instructions else []
    if request.difficulty == "mixed":
        notes.append("Vary the difficulty across the questions (a mix of easy, medium and hard).")
    return {
        "course_id": _UNSCOPED_COURSE,
        "topic": request.topic,
        "question_type": _FORMATS[request.question_format],
        "question_count": request.question_count,
        "difficulty": _DIFFICULTIES[request.difficulty],
        "total_marks": float(request.total_marks),
        "teacher_instructions": "\n".join(notes) or None,
    }


def whole_marks(weights: list[float], total: int) -> list[int]:
    """Split ``total`` into whole marks proportional to ``weights``: each >= 1, summing exactly to total."""
    if not weights:
        return []
    if total < len(weights):
        raise ValueError("total marks must cover at least one mark per question")
    safe = [w if w > 0 else 1.0 for w in weights]
    spare = total - len(safe)  # everyone gets 1, the rest is shared proportionally
    scale = sum(safe)
    shares = [spare * w / scale for w in safe]
    marks = [1 + math.floor(s) for s in shares]
    leftover = total - sum(marks)
    by_remainder = sorted(range(len(safe)), key=lambda i: shares[i] - math.floor(shares[i]), reverse=True)
    for i in by_remainder[:leftover]:
        marks[i] += 1
    return marks


def _subjective_guidance(question: dict[str, Any]) -> str:
    parts: list[str] = []
    answer = question.get("model_answer") or {}
    if answer.get("text"):
        parts.append(answer["text"].strip())
    if answer.get("key_points"):
        parts.append("Key points:\n" + "\n".join(f"- {point}" for point in answer["key_points"]))
    rubric = question.get("rubric") or {}
    if rubric.get("criteria"):
        parts.append(
            "Rubric:\n"
            + "\n".join(f"- {c['description']} ({c['max_marks']:g} marks)" for c in rubric["criteria"])
        )
    return "\n\n".join(parts)


def _mcq_fields(question: dict[str, Any]) -> tuple[list[str], int, str]:
    options = question.get("mcq_options") or []
    texts = [str(option["text"]).strip() for option in options]
    correct = next((i for i, option in enumerate(options) if option.get("is_correct")), None)
    if len(texts) < 2 or correct is None:
        raise ValueError("MCQ question without at least two options and a correct answer")
    explanation = (options[correct].get("explanation") or "").strip()
    guidance = f"Correct answer: {texts[correct]}" + (f"\n{explanation}" if explanation else "")
    return texts, correct, guidance


def map_engine_draft(draft: dict[str, Any], total_marks: int) -> GeneratedAssignmentDraft:
    """Convert the AI Engine's AssignmentDraft JSON into editor-ready questions."""
    usable: list[dict[str, Any]] = []
    for question in draft["questions"]:
        text = str(question.get("question_text") or "").strip()
        if not text:
            continue
        if question.get("question_type") == "MCQ":
            try:
                options, correct, guidance = _mcq_fields(question)
            except (ValueError, KeyError):
                logger.warning("Dropping malformed generated MCQ question")
                continue
            usable.append({"type": "mcq", "text": text, "expected_answer": guidance,
                           "options": options, "correct_option_index": correct,
                           "weight": float(question.get("marks") or 1)})
        else:
            usable.append({"type": "subjective", "text": text, "expected_answer": _subjective_guidance(question),
                           "weight": float(question.get("marks") or 1)})

    if not usable:
        raise ValueError("AI Engine returned no usable questions")

    weights = [q.pop("weight") for q in usable]
    if total_marks < len(usable):  # the model over-produced: keep the first `total_marks` at 1 mark each
        usable, marks = usable[:total_marks], [1] * total_marks
    else:
        marks = whole_marks(weights, total_marks)

    return GeneratedAssignmentDraft(
        title=str(draft.get("title") or "").strip() or "AI-drafted assignment",
        instructions=(draft.get("instructions") or None),
        questions=[GeneratedQuestion(marks=m, **q) for q, m in zip(usable, marks)],
        grounded_in_course_materials=False,
    )
