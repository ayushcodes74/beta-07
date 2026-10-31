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
    GradingCorrection,
    GradingCorrectionIn,
    GradingSuggestionResponse,
    PublishedGradeResponse,
    PublishedQuestionResult,
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
        # Teacher corrections from earlier checks of this assignment: the AI must follow them.
        corrections = await asyncio.to_thread(self._corrections_by_question, assignment, access_token)

        payload = {
            "submission_id": str(submission.id),
            "assignment_id": str(assignment.id),
            "course_id": str(assignment.course_id) if assignment.course_id else None,
            "student_text": student_text,
            "ocr_confidence": ocr_confidence,
            "questions": [
                _question_payload(q, n, corrections.get(n, [])) for n, q in enumerate(questions, start=1)
            ],
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
                    teacher_corrections_used=len(corrections.get(n, [])),
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
        saved.teacher_corrections = _stored_corrections(record.flags)
        return saved

    async def save_corrections(
        self,
        teacher: CurrentUser,
        submission_id: UUID,
        corrections: list[GradingCorrectionIn],
        *,
        access_token: str,
    ) -> list[GradingCorrection]:
        """Record where the AI graded this submission wrong (replaces earlier corrections for it).

        Corrections are stored with the submission's grading result and given to the AI Engine as
        binding guidance whenever the same question of this assignment is checked again. Nothing is
        retrained; removing a correction stops it being used.
        """
        if self.grading_repo is None:
            raise GradingRepositoryError("Grading storage is not configured")
        submission = await asyncio.to_thread(self.submissions.get, submission_id, access_token=access_token)
        if submission is None:
            raise SubmissionNotFoundError("Submission not found")
        assignment = await asyncio.to_thread(
            self.assignment_service.get_for, teacher, submission.assignment_id, access_token=access_token
        )
        questions = list(assignment.content.questions)
        if len({c.question_number for c in corrections}) != len(corrections):
            raise SubmissionValidationError("duplicate_correction", "Each question can have only one correction.")
        for c in corrections:
            if c.question_number > len(questions):
                raise SubmissionValidationError(
                    "invalid_question", f"Question {c.question_number} does not exist in this assignment."
                )
            max_marks = float(questions[c.question_number - 1].marks)
            if c.teacher_marks > max_marks:
                raise SubmissionValidationError(
                    "score_out_of_range", f"Question {c.question_number} is worth at most {max_marks:g} marks."
                )

        def _write() -> list[GradingCorrection]:
            record = self.grading_repo.get_by_submission_id(submission_id, access_token=access_token)
            if record is None:
                raise SubmissionValidationError(
                    "no_answer_check", "Run the AI answer check first, then correct where it went wrong."
                )
            suggestion = _suggestion_questions(record.evidence)
            previous = {c.question_number: c for c in _stored_corrections(record.flags)}
            now = datetime.now(UTC)
            stored: list[GradingCorrection] = []
            for c in sorted(corrections, key=lambda c: c.question_number):
                question = questions[c.question_number - 1]
                ai = suggestion.get(c.question_number, {})
                old = previous.get(c.question_number)
                unchanged = old is not None and old.teacher_marks == c.teacher_marks and old.note == c.note.strip()
                stored.append(
                    GradingCorrection(
                        question_number=c.question_number,
                        question_text=question.text,
                        max_marks=float(question.marks),
                        ai_marks=ai.get("awarded_marks"),
                        ai_explanation=str(ai.get("explanation") or "")[:1000],
                        teacher_marks=c.teacher_marks,
                        note=c.note.strip(),
                        teacher_id=teacher.id,
                        created_at=old.created_at if unchanged else now,
                    )
                )
            flags = dict(record.flags or {})
            flags[_CORRECTIONS_KEY] = [c.model_dump(mode="json") for c in stored]
            if self.grading_repo.update_flags(submission_id, flags, access_token=access_token) is None:
                raise GradingRepositoryError("Corrections could not be saved (check grading_results RLS)")
            return stored

        return await asyncio.to_thread(_write)

    async def publish_grade(
        self,
        teacher: CurrentUser,
        submission_id: UUID,
        final_score: float,
        final_feedback: str,
        *,
        access_token: str,
        show_solutions: bool = True,
    ) -> PublishedGradeResponse:
        """Teacher approves a final score/feedback and publishes it to the student.

        Works on top of the stored AI suggestion when there is one; otherwise records a teacher-only
        grade (e.g. when the AI Engine is unavailable). Re-publishing replaces the published grade.

        Late submissions need the teacher's decision first. For accepted late work, ``final_score`` is
        the teacher's mark before the late deduction; the stored/published score has it applied.
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
        if submission.late_status == "pending":
            raise SubmissionValidationError(
                "late_decision_required",
                "This submission was handed in late. Accept or reject it on the Late submissions page before "
                "publishing a grade.",
            )
        if submission.late_status == "rejected":
            raise SubmissionValidationError(
                "late_submission_rejected",
                "This late submission was rejected, so no grade can be published. Change the decision on the "
                "Late submissions page to grade it.",
            )
        raw_score = round(final_score, 2)
        penalty = submission.late_penalty_percent if submission.late_status == "accepted" else None
        penalty = penalty if penalty else None  # 0% deduction = no penalty
        score = Decimal(str(late_adjusted_score(raw_score, penalty)))
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
            if penalty is not None:
                flags["late_penalty_percent"] = penalty
                flags["score_before_late_penalty"] = raw_score
            else:
                flags.pop("late_penalty_percent", None)
                flags.pop("score_before_late_penalty", None)
            # Freeze what the student sees per question: later re-checks/corrections need a re-publish.
            breakdown = _student_breakdown(
                existing.evidence if existing else None, flags, assignment.content.questions, show_solutions
            )
            if show_solutions:
                # Students see solutions only after the due date (classmates may not have submitted yet).
                flags[_SOLUTIONS_FROM_KEY] = assignment.content.due_at.isoformat()
            else:
                flags.pop(_SOLUTIONS_FROM_KEY, None)
            if breakdown:
                flags[_BREAKDOWN_KEY] = [q.model_dump(mode="json") for q in breakdown]
            else:
                flags.pop(_BREAKDOWN_KEY, None)
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

    async def list_published_grades(self, user: CurrentUser, *, access_token: str) -> list[PublishedGradeResponse]:
        """Every published grade the caller may see, in a few queries (instead of one request each).

        Students: their own submissions. Teachers: submissions to their own assignments.
        """
        if self.grading_repo is None:
            return []

        def _load() -> list[PublishedGradeResponse]:
            if user.role is Role.STUDENT:
                records = [
                    r for r in self.submissions.list_by_student(user.id, access_token=access_token)
                    if r.student_id == user.id
                ]
            elif user.role is Role.TEACHER:
                owned = set(self.assignment_service.owned_ids(user, access_token=access_token))
                list_many = getattr(self.submissions, "list_by_assignments", None)
                if list_many is not None:
                    fetched = list_many(sorted(owned), access_token=access_token) if owned else []
                else:
                    fetched = [s for a in owned for s in self.submissions.list_by_assignment(a, access_token=access_token)]
                records = [r for r in fetched if r.assignment_id in owned]
            else:
                return []
            ids = [r.id for r in records if r.status == "published"]
            if not ids:
                return []
            list_grades = getattr(self.grading_repo, "list_by_submission_ids", None)
            if list_grades is not None:
                grades = [
                    g for start in range(0, len(ids), 100)
                    for g in list_grades(ids[start : start + 100], access_token=access_token)
                ]
            else:
                grades = [g for i in ids if (g := self.grading_repo.get_by_submission_id(i, access_token=access_token))]
            allowed = set(ids)
            return [
                _published_response(g, for_student=user.role is Role.STUDENT)
                for g in grades
                if g.submission_id in allowed and g.status is GradingStatus.PUBLISHED
            ]

        return await asyncio.to_thread(_load)

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
        return _published_response(record, for_student=user.role is Role.STUDENT)

    # ------------------------------------------------------------------ helpers

    def _corrections_by_question(self, assignment: Any, access_token: str) -> dict[int, list[dict]]:
        """Teacher corrections recorded on any submission of this assignment, per question number.

        Only corrections whose question text still matches the current question are used (so editing
        or reordering questions never applies a stale correction). Newest first, capped per question.
        Best-effort: if storage is unavailable the answer check runs without them.
        """
        list_by_assignment = getattr(self.grading_repo, "list_by_assignment", None)
        if list_by_assignment is None:
            return {}
        try:
            records = list_by_assignment(assignment.id, access_token=access_token)
        except Exception as exc:
            logger.warning("Could not load teacher corrections: %s", type(exc).__name__)
            return {}
        questions = list(assignment.content.questions)
        found: dict[int, list[GradingCorrection]] = {}
        for record in records:
            for c in _stored_corrections(record.flags):
                n = c.question_number
                if 1 <= n <= len(questions) and c.question_text.strip() == questions[n - 1].text.strip():
                    found.setdefault(n, []).append(c)
        epoch = datetime.min.replace(tzinfo=UTC)
        return {
            n: [
                {
                    "ai_marks": c.ai_marks,
                    "ai_explanation": c.ai_explanation,
                    "teacher_marks": c.teacher_marks,
                    "max_marks": c.max_marks,
                    "note": c.note,
                }
                for c in sorted(items, key=lambda c: c.created_at or epoch, reverse=True)[:_MAX_CORRECTIONS_PER_QUESTION]
            ]
            for n, items in found.items()
        }

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
            flags: dict = {"review_required": response.review_required, "review_reasons": response.review_reasons}
            if existing is not None and (existing.flags or {}).get(_CORRECTIONS_KEY):
                flags[_CORRECTIONS_KEY] = existing.flags[_CORRECTIONS_KEY]  # re-checks keep teacher corrections
            self.grading_repo.insert(
                GradingResultCreate(
                    submission_id=response.submission_id,
                    ai_score=Decimal(str(round(response.total_awarded_marks, 2))),
                    ai_feedback=response.overall_feedback or "AI answer check completed.",
                    evidence={"kind": "ai_answer_check", "suggestion": response.model_dump(mode="json")},
                    flags=flags,
                    confidence=Decimal(str(round(sum(confidences) / len(confidences), 4))) if confidences else Decimal("0"),
                    status=GradingStatus.PENDING_REVIEW,
                ),
                access_token=access_token,
            )
            return True
        except Exception as exc:  # the suggestion is still returned to the teacher
            logger.warning("Could not store grading suggestion: %s", type(exc).__name__)
            return False


def late_adjusted_score(score: float, penalty_percent: Optional[float]) -> float:
    """Apply a late deduction: 8 marks with a 50% penalty -> 4 marks."""
    if not penalty_percent:
        return round(score, 2)
    return round(score * (1 - penalty_percent / 100.0), 2)


def _number(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _published_response(
    record: GradingResultRecord, *, for_student: bool = False, now: Optional[datetime] = None
) -> PublishedGradeResponse:
    flags = record.flags or {}
    max_score = flags.get("max_score")
    questions = _stored_breakdown(flags)
    solutions_at = _solutions_release(flags)
    withheld_until = None
    if for_student and solutions_at is not None and (now or datetime.now(UTC)) < solutions_at:
        withheld_until = solutions_at if any(q.expected_solution for q in questions) else None
        questions = [q.model_copy(update={"expected_solution": None}) for q in questions]
    return PublishedGradeResponse(
        solutions_available_at=withheld_until,
        submission_id=record.submission_id,
        final_score=float(record.final_score),
        max_score=float(max_score) if isinstance(max_score, (int, float)) else None,
        final_feedback=record.final_feedback,
        status=record.status.value,
        reviewed_at=record.reviewed_at,
        published_at=record.published_at,
        late_penalty_percent=_number(flags.get("late_penalty_percent")),
        score_before_late_penalty=_number(flags.get("score_before_late_penalty")),
        questions=questions,
    )


_BREAKDOWN_KEY = "student_breakdown"
_SOLUTIONS_FROM_KEY = "solutions_visible_from"


def _solutions_release(flags: dict) -> Optional[datetime]:
    raw = flags.get(_SOLUTIONS_FROM_KEY)
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _expected_solution(question: Any) -> Optional[str]:
    """The teacher's answer key for one question, as a student-readable solution."""
    if question.type == "mcq":
        correct = next((o for o in question.options if o.id == question.correct_option_id), None)
        return f"{question.correct_option_id}) {correct.text}" if correct else None
    answer = (question.expected_answer or "").strip()
    return answer or None


def _student_breakdown(
    evidence: Any, flags: dict, questions: Any, show_solutions: bool
) -> list[PublishedQuestionResult]:
    """Per-question marks, reasons and expected solutions for the student.

    Marks and reasons come from the AI check plus teacher corrections: a question the teacher corrected
    shows the teacher's mark and note instead of the AI's reasoning, which argued for a different mark.
    Without an AI check (teacher-only grade) questions have no per-question mark, only the solution.
    """
    suggestion = _suggestion_questions(evidence)
    if not suggestion and not show_solutions:
        return []
    corrections = {c.question_number: c for c in _stored_corrections(flags)}
    results: list[PublishedQuestionResult] = []
    for number, question in enumerate(questions, start=1):
        q = suggestion.get(number, {})
        correction = corrections.get(number)
        solution = _expected_solution(question) if show_solutions else None
        try:
            if correction is not None:
                result = PublishedQuestionResult(
                    number=number,
                    question_text=question.text,
                    awarded_marks=correction.teacher_marks,
                    max_marks=float(question.marks),
                    teacher_comment=correction.note,
                    expected_solution=solution,
                )
            elif q:
                result = PublishedQuestionResult(
                    number=number,
                    question_text=question.text,
                    awarded_marks=float(q.get("awarded_marks") or 0.0),
                    max_marks=float(question.marks),
                    explanation=str(q.get("explanation") or ""),
                    strengths=[str(s) for s in q.get("strengths") or []],
                    areas_for_improvement=[str(s) for s in q.get("areas_for_improvement") or []],
                    expected_solution=solution,
                )
            else:
                result = PublishedQuestionResult(
                    number=number, question_text=question.text, max_marks=float(question.marks),
                    expected_solution=solution,
                )
        except (TypeError, ValueError):
            continue
        results.append(result)
    return results


def _stored_breakdown(flags: dict) -> list[PublishedQuestionResult]:
    raw = flags.get(_BREAKDOWN_KEY)
    results: list[PublishedQuestionResult] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            results.append(PublishedQuestionResult.model_validate(item))
        except Exception:
            continue
    return results


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


_CORRECTIONS_KEY = "teacher_corrections"
_MAX_CORRECTIONS_PER_QUESTION = 5


def _stored_corrections(flags: Any) -> list[GradingCorrection]:
    raw = flags.get(_CORRECTIONS_KEY) if isinstance(flags, dict) else None
    corrections: list[GradingCorrection] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            corrections.append(GradingCorrection.model_validate(item))
        except Exception:
            continue
    return corrections


def _suggestion_questions(evidence: Any) -> dict[int, dict]:
    """Per-question AI marks/explanation from a stored answer check, keyed by question number."""
    if not isinstance(evidence, dict) or evidence.get("kind") != "ai_answer_check":
        return {}
    questions = (evidence.get("suggestion") or {}).get("questions") or []
    return {q["number"]: q for q in questions if isinstance(q, dict) and isinstance(q.get("number"), int)}


def _question_payload(question: Any, number: int, corrections: Optional[list[dict]] = None) -> dict:
    payload: dict = {
        "question_id": f"q{number}",
        "type": question.type,
        "text": question.text,
        "marks": float(question.marks),
    }
    if corrections:
        payload["teacher_corrections"] = corrections
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
