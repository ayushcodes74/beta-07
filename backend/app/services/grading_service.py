"""AI answer checking: grade a submission's OCR text against the teacher's answer keys.

Flow (teacher-only):
  1. Load the submission and the owned assignment with its answer keys (404 if not the owner).
  2. Load the completed OCR result for the submission.
  3. Ask the AI Engine (POST /v1/grading/grade-submission) for per-question suggested marks.
  4. Store the suggestion as a ``pending_review`` grading result (best-effort; never overwrites a
     result the teacher already approved or published) and return it.

The suggestion is review evidence. Publishing grades to students is a separate, teacher-driven step
(``publish_grade``): the teacher's final score/feedback is stored as approved, then published.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import logging
import re
from typing import Any, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.database.grading_repository import (
    GradingRepository,
    GradingRepositoryError,
    GradingResultCreate,
    GradingResultRecord,
    GradingStatus,
)
from app.schemas.grading import (
    CourseEvidence,
    GradingSuggestionResponse,
    PublishedGradeResponse,
    QuestionGradeSuggestion,
)
from app.schemas.user import Role
from app.schemas.ocr import JobStatusResponse, OCRDocumentResult
from app.services.ai_generation_service import (
    AIGenerationError,
    AIRateLimitedError,
    AIServiceUnavailableError,
    AITimeoutError,
)
from app.services.assignment_service import AssignmentService
from app.services.auth_service import CurrentUser
from app.services.ocr_client import OCRServiceClient
from app.services.submission_service import (
    SubmissionNotFoundError,
    SubmissionRepository,
    SubmissionValidationError,
)

logger = logging.getLogger(__name__)


class GradingNotReadyError(SubmissionValidationError):
    """OCR has not finished, so there is no text to check yet."""


class GradingService:
    def __init__(
        self,
        submissions: SubmissionRepository,
        assignment_service: AssignmentService,
        ocr_client: OCRServiceClient,
        grading_repo: Optional[GradingRepository] = None,
        *,
        ai_base_url: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.submissions = submissions
        self.assignment_service = assignment_service
        self.ocr_client = ocr_client
        self.grading_repo = grading_repo
        self.ai_base_url = (ai_base_url or settings.AI_SERVICE_URL).rstrip("/")
        self._transport = transport
        self._timeout = httpx.Timeout(settings.AI_READ_TIMEOUT_SECONDS, connect=settings.AI_CONNECT_TIMEOUT_SECONDS)

    # ------------------------------------------------------------------ public API

    async def grade_submission(
        self, teacher: CurrentUser, submission_id: UUID, *, access_token: str
    ) -> GradingSuggestionResponse:
        submission = await asyncio.to_thread(self.submissions.get, submission_id, access_token=access_token)
        if submission is None:
            raise SubmissionNotFoundError("Submission not found")
        # Ownership check AND answer keys in one call (raises AssignmentNotFoundError -> 404).
        assignment = await asyncio.to_thread(
            self.assignment_service.get_for, teacher, submission.assignment_id, access_token=access_token
        )
        questions = list(assignment.content.questions)
        if not questions:
            raise SubmissionValidationError("no_questions", "This assignment has no questions to check answers against.")
        if not submission.ocr_job_id:
            raise SubmissionValidationError("no_ocr_job", "No OCR processing job is associated with this submission.")

        ocr = await self.ocr_client.get_job_result(submission.ocr_job_id)
        if isinstance(ocr, JobStatusResponse) or not isinstance(ocr, OCRDocumentResult):
            raise GradingNotReadyError(
                "ocr_not_ready", "OCR is still processing this submission. Check answers once it has finished."
            )
        student_text, ocr_confidence = _transcript(ocr)

        payload = {
            "submission_id": str(submission.id),
            "assignment_id": str(assignment.id),
            "course_id": str(assignment.course_id) if assignment.course_id else None,
            "student_text": student_text,
            "ocr_confidence": ocr_confidence,
            "questions": [_question_payload(q, n) for n, q in enumerate(questions, start=1)],
        }
        result = await self._call_ai_engine(payload)

        by_id = {q["question_id"]: q for q in result.get("question_results", [])}
        suggestions = []
        for n, q in enumerate(questions, start=1):
            graded = by_id.get(f"q{n}")
            if graded is None:
                continue
            criteria = graded.get("criterion_evaluations") or []
            suggestions.append(
                QuestionGradeSuggestion(
                    number=n,
                    question_text=q.text,
                    question_type=q.type,
                    max_marks=float(graded.get("max_marks", q.marks)),
                    awarded_marks=float(graded.get("awarded_marks", 0.0)),
                    explanation=graded.get("overall_explanation", ""),
                    strengths=graded.get("strengths") or [],
                    areas_for_improvement=graded.get("areas_for_improvement") or [],
                    matched_concepts=_unique(c for crit in criteria for c in crit.get("matched_concepts") or []),
                    missing_concepts=_unique(c for crit in criteria for c in crit.get("missing_concepts") or []),
                    confidence=graded.get("confidence"),
                    review_required=bool(graded.get("review_required")),
                    review_reasons=graded.get("review_reasons") or [],
                    evidence_status=graded.get("evidence_status") or "not_requested",
                    evidence_unavailable_reason=graded.get("evidence_unavailable_reason"),
                    evidence=[
                        CourseEvidence(
                            material_id=str(e.get("document_id", "")),
                            filename=e.get("title"),
                            page_number=e.get("page_number"),
                            similarity=e.get("similarity_score"),
                            content=e.get("snippet", ""),
                        )
                        for e in graded.get("evidence") or []
                    ],
                )
            )

        total_awarded = float(result.get("total_awarded_marks", 0.0))
        total_max = float(result.get("total_max_marks", 0.0))
        percentage = float(result.get("percentage", 0.0))
        overall_feedback = result.get("overall_feedback", "")
        scoring = None
        threshold = settings.GRADING_FULL_MARKS_AT
        if threshold < 1.0 and suggestions:
            raw_total = total_awarded
            total_awarded, percentage, overall_feedback = _apply_full_marks_policy(
                suggestions, threshold, total_max, overall_feedback
            )
            scoring = {"full_marks_at": threshold, "raw_total": round(raw_total, 2)}

        response = GradingSuggestionResponse(
            submission_id=submission.id,
            assignment_id=assignment.id,
            total_awarded_marks=total_awarded,
            total_max_marks=total_max,
            percentage=percentage,
            overall_feedback=overall_feedback,
            review_required=bool(result.get("review_required")),
            review_reasons=result.get("review_reasons") or [],
            questions=suggestions,
            ocr_confidence=ocr_confidence,
            graded_at=datetime.now(UTC),
            saved=False,
            rag=result.get("rag"),
            scoring=scoring,
        )
        response.saved = await asyncio.to_thread(self._save, response, access_token)
        return response

    async def get_saved_suggestion(
        self, teacher: CurrentUser, submission_id: UUID, *, access_token: str
    ) -> Optional[GradingSuggestionResponse]:
        """Return the last stored suggestion for a submission the teacher owns, or None."""
        submission = await asyncio.to_thread(self.submissions.get, submission_id, access_token=access_token)
        if submission is None:
            raise SubmissionNotFoundError("Submission not found")
        await asyncio.to_thread(
            self.assignment_service.require_owned, teacher, submission.assignment_id, access_token=access_token
        )
        if self.grading_repo is None:
            return None
        try:
            record = await asyncio.to_thread(
                self.grading_repo.get_by_submission_id, submission_id, access_token=access_token
            )
        except Exception as exc:  # storage problems shouldn't break the page; teacher can re-run
            logger.warning("Could not load saved grading suggestion: %s", type(exc).__name__)
            return None
        evidence = record.evidence if record else None
        if not isinstance(evidence, dict) or evidence.get("kind") != "ai_answer_check":
            return None
        try:
            saved = GradingSuggestionResponse.model_validate(evidence["suggestion"])
        except Exception:
            return None
        saved.saved = True
        saved.status = record.status.value
        return saved

    async def publish_grade(
        self,
        teacher: CurrentUser,
        submission_id: UUID,
        final_score: float,
        final_feedback: str,
        *,
        access_token: str,
    ) -> PublishedGradeResponse:
        """Teacher approves a final score/feedback and publishes it to the student.

        Works on top of the stored AI suggestion when there is one; otherwise records a teacher-only
        grade (e.g. when the AI Engine is unavailable). Re-publishing replaces the published grade.
        """
        if self.grading_repo is None:
            raise GradingRepositoryError("Grading storage is not configured")
        submission = await asyncio.to_thread(self.submissions.get, submission_id, access_token=access_token)
        if submission is None:
            raise SubmissionNotFoundError("Submission not found")
        assignment = await asyncio.to_thread(
            self.assignment_service.get_for, teacher, submission.assignment_id, access_token=access_token
        )
        max_score = float(assignment.content.total_marks)
        if final_score > max_score:
            raise SubmissionValidationError(
                "score_out_of_range", f"The final score cannot exceed the assignment's total marks ({max_score:g})."
            )
        score = Decimal(str(round(final_score, 2)))
        feedback = final_feedback.strip()

        def _write() -> GradingResultRecord:
            repo = self.grading_repo
            existing = repo.get_by_submission_id(submission_id, access_token=access_token)
            if existing is None:
                repo.insert(
                    GradingResultCreate(
                        submission_id=submission_id,
                        ai_score=score,
                        ai_feedback="",
                        evidence={"kind": "teacher_manual_grade"},
                        flags={},
                        confidence=Decimal("1"),
                        status=GradingStatus.PENDING_REVIEW,
                    ),
                    access_token=access_token,
                )
                flags: dict = {}
            else:
                flags = dict(existing.flags or {})
            flags["max_score"] = max_score
            reviewed = repo.update_review(
                submission_id, score, feedback, teacher.id, GradingStatus.APPROVED,
                access_token=access_token, flags=flags,
            )
            if reviewed is None:
                raise GradingRepositoryError("Grading result could not be updated (check grading_results RLS)")
            published = repo.publish(submission_id, access_token=access_token)
            if published is None:
                raise GradingRepositoryError("Grading result could not be published (check grading_results RLS)")
            # Student-facing lifecycle: the submissions list shows "Published" from this status.
            if self.submissions.update_status(submission_id, "published", access_token=access_token) is None:
                raise GradingRepositoryError("Submission status could not be set to published")
            return published

        record = await asyncio.to_thread(_write)
        return _published_response(record)

    async def get_published_grade(
        self, user: CurrentUser, submission_id: UUID, *, access_token: str
    ) -> Optional[PublishedGradeResponse]:
        """Published grade for the submission's student or the owning teacher; None if not published."""
        if self.grading_repo is None:
            return None
        submission = await asyncio.to_thread(self.submissions.get, submission_id, access_token=access_token)
        if submission is None:
            raise SubmissionNotFoundError("Submission not found")
        if user.role is Role.STUDENT:
            if submission.student_id != user.id:
                raise SubmissionNotFoundError("Submission not found")
            record = await asyncio.to_thread(
                self.grading_repo.get_published_for_student, submission_id, user.id, access_token=access_token
            )
        elif user.role is Role.TEACHER:
            await asyncio.to_thread(
                self.assignment_service.require_owned, user, submission.assignment_id, access_token=access_token
            )
            record = await asyncio.to_thread(
                self.grading_repo.get_by_submission_id, submission_id, access_token=access_token
            )
        else:
            raise SubmissionNotFoundError("Submission not found")
        if record is None or record.status is not GradingStatus.PUBLISHED:
            return None
        return _published_response(record)

    # ------------------------------------------------------------------ helpers

    async def _call_ai_engine(self, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(
                base_url=self.ai_base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post("/v1/grading/grade-submission", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            logger.error("AI Engine unreachable: %s", type(exc).__name__)
            raise AIServiceUnavailableError("AI Engine is unreachable") from exc
        except httpx.TimeoutException as exc:
            raise AITimeoutError("AI Engine timed out") from exc
        except httpx.HTTPError as exc:
            logger.error("AI Engine request failed: %s", type(exc).__name__)
            raise AIServiceUnavailableError("AI Engine request failed") from exc

        if response.status_code == 503:
            raise AIServiceUnavailableError("AI grading is not configured")
        if response.status_code == 429:
            raise AIRateLimitedError("AI provider rate limit reached")
        if response.status_code == 504:
            raise AITimeoutError("AI provider timed out")
        if response.status_code != 200:
            raise AIGenerationError(f"AI Engine returned status {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise AIGenerationError("AI Engine returned invalid JSON") from exc
        if not isinstance(body, dict):
            raise AIGenerationError("AI Engine returned an unexpected payload")
        return body

    def _save(self, response: GradingSuggestionResponse, access_token: str) -> bool:
        if self.grading_repo is None:
            return False
        try:
            existing = self.grading_repo.get_by_submission_id(response.submission_id, access_token=access_token)
            if existing is not None and existing.status is not GradingStatus.PENDING_REVIEW:
                logger.info("Not overwriting %s grading result for submission", existing.status.value)
                return False
            confidences = [q.confidence for q in response.questions if q.confidence is not None]
            self.grading_repo.insert(
                GradingResultCreate(
                    submission_id=response.submission_id,
                    ai_score=Decimal(str(round(response.total_awarded_marks, 2))),
                    ai_feedback=response.overall_feedback or "AI answer check completed.",
                    evidence={"kind": "ai_answer_check", "suggestion": response.model_dump(mode="json")},
                    flags={"review_required": response.review_required, "review_reasons": response.review_reasons},
                    confidence=Decimal(str(round(sum(confidences) / len(confidences), 4))) if confidences else Decimal("0"),
                    status=GradingStatus.PENDING_REVIEW,
                ),
                access_token=access_token,
            )
            return True
        except Exception as exc:  # the suggestion is still returned to the teacher
            logger.warning("Could not store grading suggestion: %s", type(exc).__name__)
            return False


def _published_response(record: GradingResultRecord) -> PublishedGradeResponse:
    max_score = (record.flags or {}).get("max_score")
    return PublishedGradeResponse(
        submission_id=record.submission_id,
        final_score=float(record.final_score),
        max_score=float(max_score) if isinstance(max_score, (int, float)) else None,
        final_feedback=record.final_feedback,
        status=record.status.value,
        reviewed_at=record.reviewed_at,
        published_at=record.published_at,
    )


_SCORE_IN_FEEDBACK = re.compile(r"\(Score:\s*[\d.]+\s*/\s*[\d.]+\s*[—-]\s*[\d.]+%\)")


def _apply_full_marks_policy(
    questions: list[QuestionGradeSuggestion], threshold: float, total_max: float, overall_feedback: str
) -> tuple[float, float, str]:
    """Full marks once a student covers ``threshold`` of a question's key-point marks.

    score = min(max_marks, raw / threshold), per question, identically for every submission. The AI's
    raw score is kept on each question; returns (total, percentage, feedback with the score line updated).
    """
    for q in questions:
        q.raw_awarded_marks = q.awarded_marks
        q.awarded_marks = round(min(q.max_marks, q.awarded_marks / threshold), 2)
    total = round(sum(q.awarded_marks for q in questions), 2)
    percentage = round(total / total_max * 100.0, 2) if total_max > 0 else 0.0
    feedback = _SCORE_IN_FEEDBACK.sub(f"(Score: {total:.1f}/{total_max:.1f} — {percentage:.1f}%)", overall_feedback)
    return total, percentage, feedback


def _transcript(ocr: OCRDocumentResult) -> tuple[str, Optional[float]]:
    pages = sorted(ocr.pages, key=lambda p: p.page_number)
    text = "\n\n".join(
        f"[Page {p.page_number}]\n{p.full_text.strip()}" for p in pages if p.full_text and p.full_text.strip()
    )
    confidences = [b.confidence for p in pages for b in p.text_blocks if b.confidence is not None]
    confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
    return text, confidence


def _question_payload(question: Any, number: int) -> dict:
    payload: dict = {
        "question_id": f"q{number}",
        "type": question.type,
        "text": question.text,
        "marks": float(question.marks),
    }
    if question.type == "mcq":
        payload["options"] = [{"id": o.id, "text": o.text} for o in question.options]
        payload["correct_option_id"] = question.correct_option_id
    else:
        payload["expected_answer"] = question.expected_answer
        payload["instructions"] = question.instructions
    return payload


def _unique(items) -> list:
    seen: dict = {}
    for item in items:
        if isinstance(item, str) and item.strip():
            seen.setdefault(item.strip(), None)
    return list(seen)
