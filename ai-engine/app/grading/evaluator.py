"""Rubric-grounded semantic answer evaluator.

Evaluates student answers against teacher-approved rubrics and course evidence,
awarding partial credit for equivalent meaning and alternative approaches while
strictly detecting missing concepts, handling OCR extraction uncertainty,
supporting deterministic MCQ grading, and flagging uncertain submissions for review.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from app.llm.gemini_client import GeminiClient, get_gemini_client
from app.llm import prompts
from app.grading.evidence_retriever import GradingEvidenceRetriever
from app.grading.feedback_generator import FeedbackGenerator
from app.trust.service import TrustService
from app.schemas.common import ReviewReasonCategory, SourceReference
from app.schemas.assignment import QuestionType, Rubric, RubricCriterion
from app.schemas.grading import (
    CriterionEvaluation,
    GradingRequest,
    GradingResult,
    GradingStatus,
    QuestionGrade,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intermediate Evaluation Schemas for LLM
# ---------------------------------------------------------------------------

class _LLMCriterionEvaluation(BaseModel):
    criterion_id: str
    criterion_name: Optional[str] = None
    awarded_marks: float
    max_marks: float
    explanation: str
    matched_concepts: List[str] = Field(default_factory=list)
    missing_concepts: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class _LLMQuestionGradeResponse(BaseModel):
    awarded_marks: float
    criterion_evaluations: List[_LLMCriterionEvaluation] = Field(min_length=1)
    overall_explanation: str
    strengths: List[str] = Field(default_factory=list)
    areas_for_improvement: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    review_required: bool = False
    review_reasons: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Evaluator Service
# ---------------------------------------------------------------------------

class AnswerEvaluator:
    """Service that semantically scores student answers against rubrics and course evidence."""

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        evidence_retriever: Optional[GradingEvidenceRetriever] = None,
        trust_service: Optional[TrustService] = None,
    ):
        """Initialize AnswerEvaluator.

        Args:
            gemini_client: Gemini API client instance.
            evidence_retriever: Evidence retrieval helper for course grounding.
            trust_service: Trust, confidence, and human review orchestrator.
        """
        self.gemini_client = gemini_client or get_gemini_client()
        self.evidence_retriever = evidence_retriever or GradingEvidenceRetriever()
        self.trust_service = trust_service or TrustService(gemini_client=self.gemini_client)

    def evaluate_question(
        self,
        request: GradingRequest,
        retrieved_evidence: Optional[List[str]] = None,
        source_references: Optional[List[SourceReference]] = None,
        ocr_confidence: Optional[float] = None,
    ) -> QuestionGrade:
        """Evaluate a single question response against its rubric and course material.

        Args:
            request: GradingRequest containing question, answer, and optional rubric/guidance.
            retrieved_evidence: Optional pre-retrieved text snippets.
            source_references: Optional pre-retrieved SourceReference objects.
            ocr_confidence: Optional OCR extraction score override.

        Returns:
            QuestionGrade with criterion breakdowns, citations, and review flags.
        """
        effective_ocr_confidence = ocr_confidence if ocr_confidence is not None else request.ocr_confidence

        # 1. Deterministic MCQ check (Fix 3: bypass LLM completely)
        if request.question_type == QuestionType.MCQ or request.correct_option_id is not None:
            return self._evaluate_mcq_deterministic(request)

        student_text = request.student_answer.strip() if request.student_answer else ""

        # 2. Edge Case: Empty student answer (Fix 1: check OCR extraction failure vs genuine blank)
        if not student_text:
            return self._handle_empty_submission(request, effective_ocr_confidence)

        # 3. Retrieve course material if not supplied
        evidence_snippets = retrieved_evidence or []
        refs = source_references or []
        has_sufficient_evidence = True

        if not evidence_snippets:
            ev_result = self.evidence_retriever.retrieve_evidence_for_grading(
                course_id=request.course_id,
                question_text=request.question_text,
                student_answer=student_text,
            )
            evidence_snippets = ev_result.evidence_snippets
            refs = ev_result.source_references
            has_sufficient_evidence = ev_result.has_sufficient_evidence

        # 4. Resolve grading guidance & rubric (Fix 2: optional rubric support)
        rubric, guidance_review_flag, guidance_review_reason = self._resolve_grading_guidance(request)

        # 5. Retrieve approved teacher corrections as reference examples if available
        teacher_examples = self.trust_service.get_approved_reference_snippets(
            course_id=request.course_id,
            question_id=request.question_id,
        )

        # 6. Format rubric text for prompt
        rubric_lines = [f"Total Question Marks: {request.question_max_marks}"]
        for c in rubric.criteria:
            crit_name = c.description
            exp = f"Expected: {', '.join(c.expected_concepts)}" if c.expected_concepts else ""
            alt = f"Acceptable alternatives: {', '.join(c.acceptable_alternatives)}" if c.acceptable_alternatives else ""
            rubric_lines.append(f"- Criterion [{c.criterion_id}] ({c.max_marks} marks): {crit_name}. {exp}. {alt}")
        formatted_rubric = "\n".join(rubric_lines)

        # 7. Construct grounded prompt
        prompt = prompts.build_grading_prompt(
            question=request.question_text,
            student_answer=student_text,
            max_marks=request.question_max_marks,
            rubric_text=formatted_rubric,
            retrieved_evidence=evidence_snippets,
            teacher_examples=teacher_examples if teacher_examples else None,
        )

        expected_model_text = request.expected_answer or (request.model_answer.text if request.model_answer else None)
        if expected_model_text:
            prompt += f"\n### TEACHER EXPECTED / MODEL ANSWER REFERENCE (Guidance only; do not demand exact wording):\n{expected_model_text}\n"

        if request.instructions:
            prompt += f"\n### TEACHER SPECIFIC INSTRUCTIONS:\n{request.instructions}\n"

        # 8. Invoke Gemini for semantic grading
        llm_response = self.gemini_client.generate_structured(
            prompt=prompt,
            response_schema=_LLMQuestionGradeResponse,
            system_instruction=prompts.SYSTEM_ACADEMIC_EVALUATOR,
        )

        # 9. Reconcile criteria marks with rubric and clamp
        evaluations: List[CriterionEvaluation] = []
        rubric_crit_map = {c.criterion_id: c for c in rubric.criteria}

        for llm_c in llm_response.criterion_evaluations:
            rubric_c = rubric_crit_map.get(llm_c.criterion_id)
            c_max = rubric_c.max_marks if rubric_c else llm_c.max_marks
            c_awarded = max(0.0, min(llm_c.awarded_marks, c_max))

            evaluations.append(
                CriterionEvaluation(
                    criterion_id=llm_c.criterion_id,
                    criterion_name=rubric_c.description if rubric_c else llm_c.criterion_name,
                    max_marks=c_max,
                    awarded_marks=round(c_awarded, 2),
                    explanation=llm_c.explanation,
                    matched_concepts=llm_c.matched_concepts,
                    missing_concepts=llm_c.missing_concepts,
                    evidence_references=refs,
                    confidence=llm_c.confidence,
                )
            )

        total_awarded = sum(c.awarded_marks for c in evaluations)
        clamped_total = max(0.0, min(total_awarded, request.question_max_marks))

        review_reasons_list = list(llm_response.review_reasons)
        review_required_flag = llm_response.review_required

        if guidance_review_flag and guidance_review_reason:
            review_required_flag = True
            if guidance_review_reason not in review_reasons_list:
                review_reasons_list.append(guidance_review_reason)

        initial_grade = QuestionGrade(
            question_id=request.question_id,
            max_marks=request.question_max_marks,
            awarded_marks=round(clamped_total, 2),
            criterion_evaluations=evaluations,
            overall_explanation=llm_response.overall_explanation,
            strengths=llm_response.strengths,
            areas_for_improvement=llm_response.areas_for_improvement,
            confidence=llm_response.confidence,
            review_required=review_required_flag,
            review_reasons=review_reasons_list,
        )

        # 10. Run unified Trust & Confidence assessment
        trust_res = self.trust_service.assess_submission(
            submission_id=request.submission_id,
            assignment_id=request.assignment_id,
            student_answer=student_text,
            question_grade=initial_grade,
            rubric=rubric,
            source_references=refs,
            has_sufficient_evidence=has_sufficient_evidence,
            ocr_confidence=effective_ocr_confidence,
            question_context=request.question_text,
        )

        # Merge review requirements and reasons
        all_reasons = list(initial_grade.review_reasons)
        for rev_item in trust_res.review_items:
            if rev_item.reason not in all_reasons:
                all_reasons.append(rev_item.reason)

        final_review_required = initial_grade.review_required or trust_res.review_required

        object.__setattr__(initial_grade, "confidence", trust_res.confidence_breakdown.overall)
        object.__setattr__(initial_grade, "review_required", final_review_required)
        object.__setattr__(initial_grade, "review_reasons", all_reasons)

        return initial_grade

    async def async_evaluate_question(
        self,
        request: GradingRequest,
        retrieved_evidence: Optional[List[str]] = None,
        source_references: Optional[List[SourceReference]] = None,
        ocr_confidence: Optional[float] = None,
    ) -> QuestionGrade:
        """Asynchronously evaluate a single question using asyncio.to_thread.

        Prevents blocking the FastAPI async event loop during LLM evaluation.
        """
        return await asyncio.to_thread(
            self.evaluate_question,
            request,
            retrieved_evidence=retrieved_evidence,
            source_references=source_references,
            ocr_confidence=ocr_confidence,
        )

    def grade_submission(
        self,
        submission_id: str,
        assignment_id: str,
        requests: List[GradingRequest],
    ) -> GradingResult:
        """Grade a multi-question submission and assemble assignment-level results.

        Args:
            submission_id: Submission identifier.
            assignment_id: Assignment identifier.
            requests: List of GradingRequest items for each question.

        Returns:
            Complete GradingResult with score, feedback, and review routing.
        """
        if not requests:
            raise ValueError("requests list cannot be empty for grading submission.")

        question_grades: List[QuestionGrade] = []
        all_review_reasons: List[str] = []
        any_review_needed = False

        for req in requests:
            q_grade = self.evaluate_question(req)
            question_grades.append(q_grade)
            if q_grade.review_required:
                any_review_needed = True
                all_review_reasons.extend(
                    [f"Q[{q_grade.question_id}]: {r}" for r in q_grade.review_reasons]
                )

        total_awarded = sum(q.awarded_marks for q in question_grades)
        total_max = sum(q.max_marks for q in question_grades)
        overall_feedback = FeedbackGenerator.generate_overall_feedback(question_grades)

        status = GradingStatus.NEEDS_REVIEW if any_review_needed else GradingStatus.COMPLETED

        return GradingResult(
            submission_id=submission_id,
            assignment_id=assignment_id,
            total_awarded_marks=round(total_awarded, 2),
            total_max_marks=round(total_max, 2),
            question_results=question_grades,
            overall_feedback=overall_feedback,
            review_required=any_review_needed,
            review_reasons=all_review_reasons,
            grading_status=status,
        )

    async def async_grade_submission(
        self,
        submission_id: str,
        assignment_id: str,
        requests: List[GradingRequest],
    ) -> GradingResult:
        """Asynchronously grade a multi-question submission using asyncio.to_thread."""
        return await asyncio.to_thread(
            self.grade_submission,
            submission_id,
            assignment_id,
            requests,
        )

    @staticmethod
    def _evaluate_mcq_deterministic(request: GradingRequest) -> QuestionGrade:
        """Deterministic evaluation for Multiple Choice Questions without LLM invocation.

        Evaluates student choice strictly against the teacher's correct_option_id.
        Never reveals the correct answer key in student-facing explanation.
        """
        selected = (request.selected_option_id or request.student_answer or "").strip()
        correct = (request.correct_option_id or "").strip()

        # Handle missing teacher answer key
        if not correct:
            evaluations = [
                CriterionEvaluation(
                    criterion_id="mcq_selection",
                    criterion_name="Multiple Choice Selection",
                    max_marks=request.question_max_marks,
                    awarded_marks=0.0,
                    explanation="Grading key is missing for this MCQ question.",
                    matched_concepts=[],
                    missing_concepts=[],
                    confidence=0.5,
                )
            ]
            return QuestionGrade(
                question_id=request.question_id,
                max_marks=request.question_max_marks,
                awarded_marks=0.0,
                criterion_evaluations=evaluations,
                overall_explanation="MCQ question lacks a correct option key from instructor.",
                strengths=[],
                areas_for_improvement=["Contact instructor regarding question configuration."],
                confidence=0.5,
                review_required=True,
                review_reasons=["MCQ evaluation lacks teacher correct_option_id."],
            )

        # Handle missing student selection
        if not selected:
            evaluations = [
                CriterionEvaluation(
                    criterion_id="mcq_selection",
                    criterion_name="Multiple Choice Selection",
                    max_marks=request.question_max_marks,
                    awarded_marks=0.0,
                    explanation="No option selected by student.",
                    matched_concepts=[],
                    missing_concepts=["Selection required"],
                    confidence=1.0,
                )
            ]
            return QuestionGrade(
                question_id=request.question_id,
                max_marks=request.question_max_marks,
                awarded_marks=0.0,
                criterion_evaluations=evaluations,
                overall_explanation="No option was selected for this multiple-choice question.",
                strengths=[],
                areas_for_improvement=["Select an option for all multiple-choice questions."],
                confidence=1.0,
                review_required=False,
                review_reasons=[],
            )

        # Deterministic case-insensitive comparison
        is_correct = selected.upper() == correct.upper()
        awarded = request.question_max_marks if is_correct else 0.0

        if is_correct:
            explanation = f"Selected option '{selected}' is correct."
            overall_explanation = f"Correct answer selected for Question {request.question_id}."
            strengths = ["Selected correct option."]
            improvements = []
            matched = [selected]
            missing = []
        else:
            explanation = f"Selected option '{selected}' is incorrect."
            overall_explanation = f"Incorrect option selected for Question {request.question_id}."
            strengths = []
            improvements = ["Review course concepts related to this question."]
            matched = []
            missing = ["Correct option"]

        evaluations = [
            CriterionEvaluation(
                criterion_id="mcq_selection",
                criterion_name="Multiple Choice Selection",
                max_marks=request.question_max_marks,
                awarded_marks=awarded,
                explanation=explanation,
                matched_concepts=matched,
                missing_concepts=missing,
                confidence=1.0,
            )
        ]

        return QuestionGrade(
            question_id=request.question_id,
            max_marks=request.question_max_marks,
            awarded_marks=awarded,
            criterion_evaluations=evaluations,
            overall_explanation=overall_explanation,
            strengths=strengths,
            areas_for_improvement=improvements,
            confidence=1.0,
            review_required=False,
            review_reasons=[],
        )

    @staticmethod
    def _resolve_grading_guidance(request: GradingRequest) -> Tuple[Rubric, bool, Optional[str]]:
        """Resolve rubric and determine if lack of guidance requires teacher review.

        Returns:
            Tuple of (resolved_rubric, review_required_flag, review_reason).
        """
        # Case 1: Formal Rubric provided
        if request.rubric and request.rubric.criteria:
            return request.rubric, False, None

        # Case 2: Expected Answer provided (without full rubric)
        expected_text = request.expected_answer or (request.model_answer.text if request.model_answer else "")
        expected_concepts = request.model_answer.key_points if (request.model_answer and request.model_answer.key_points) else []

        if expected_text:
            rubric = Rubric(
                criteria=[
                    RubricCriterion(
                        criterion_id="holistic_eval",
                        description="Holistic evaluation based on teacher expected answer",
                        max_marks=request.question_max_marks,
                        expected_concepts=expected_concepts,
                    )
                ],
                total_marks=request.question_max_marks,
                instructions=request.instructions,
            )
            return rubric, False, None

        # Case 3: Only instructions or context provided
        if request.instructions or request.context:
            rubric = Rubric(
                criteria=[
                    RubricCriterion(
                        criterion_id="instruction_eval",
                        description=request.instructions or "Evaluation based on question context",
                        max_marks=request.question_max_marks,
                        expected_concepts=[],
                    )
                ],
                total_marks=request.question_max_marks,
                instructions=request.instructions,
            )
            return (
                rubric,
                True,
                "Graded based on teacher instructions without an official rubric or expected answer. Teacher review recommended.",
            )

        # Case 4: No guidance provided at all
        rubric = Rubric(
            criteria=[
                RubricCriterion(
                    criterion_id="general_eval",
                    description="General conceptual evaluation",
                    max_marks=request.question_max_marks,
                    expected_concepts=[],
                )
            ],
            total_marks=request.question_max_marks,
        )
        return (
            rubric,
            True,
            "No rubric, expected answer, or grading instructions provided. Teacher review required.",
        )

    @staticmethod
    def _handle_empty_submission(
        request: GradingRequest,
        ocr_confidence: Optional[float] = None,
    ) -> QuestionGrade:
        """Construct evaluation for an empty student submission.

        Distinguishes:
        Case A: Genuine blank submission (OCR not involved or high OCR confidence confirming blank).
        Case B: OCR extraction failure (empty text with low OCR confidence < 0.70).
        """
        evaluations: List[CriterionEvaluation] = []

        # Determine criteria to report
        if request.rubric and request.rubric.criteria:
            criteria_list = request.rubric.criteria
        else:
            criteria_list = [
                RubricCriterion(
                    criterion_id="default_eval",
                    description=request.instructions or "Submission response required",
                    max_marks=request.question_max_marks,
                    expected_concepts=["Response required"],
                )
            ]

        # Check for Case B: OCR extraction failure
        is_ocr_failure = ocr_confidence is not None and ocr_confidence < 0.70

        if is_ocr_failure:
            explanation = "No text could be extracted from submission. Potential OCR extraction failure on handwritten answer."
            overall_explanation = (
                f"OCR text extraction was degraded or empty (confidence: {ocr_confidence:.2f}). "
                "The submission could not be verified as intentionally blank. Teacher inspection required."
            )
            grade_confidence = max(0.10, min(0.50, round(float(ocr_confidence), 2)))
            review_required = True
            review_reasons = [
                f"Potential OCR extraction failure: empty text extracted with low OCR confidence ({ocr_confidence:.2f}). Teacher manual inspection required."
            ]
        else:
            # Case A: Genuine blank submission
            explanation = "No response provided by student."
            overall_explanation = "No answer was submitted for this question."
            grade_confidence = 1.0
            review_required = False
            review_reasons = []

        for c in criteria_list:
            evaluations.append(
                CriterionEvaluation(
                    criterion_id=c.criterion_id,
                    criterion_name=c.description,
                    max_marks=c.max_marks,
                    awarded_marks=0.0,
                    explanation=explanation,
                    matched_concepts=[],
                    missing_concepts=c.expected_concepts or ["Response required"],
                    confidence=grade_confidence,
                )
            )

        return QuestionGrade(
            question_id=request.question_id,
            max_marks=request.question_max_marks,
            awarded_marks=0.0,
            criterion_evaluations=evaluations,
            overall_explanation=overall_explanation,
            strengths=[],
            areas_for_improvement=["Attempt the question by providing a legible response."],
            confidence=grade_confidence,
            review_required=review_required,
            review_reasons=review_reasons,
        )
