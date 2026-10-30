"""Rubric-grounded semantic answer evaluator.

Evaluates student answers against teacher-approved rubrics and course evidence,
awarding partial credit for equivalent meaning and alternative approaches while
strictly detecting missing concepts and flagging uncertain submissions for review.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from app.llm.gemini_client import GeminiClient, get_gemini_client
from app.llm import prompts
from app.grading.evidence_retriever import GradingEvidenceRetriever
from app.grading.feedback_generator import FeedbackGenerator
from app.trust.service import TrustService
from app.schemas.common import ReviewReasonCategory, SourceReference
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
            request: GradingRequest containing question, answer, and rubric.
            retrieved_evidence: Optional pre-retrieved text snippets.
            source_references: Optional pre-retrieved SourceReference objects.
            ocr_confidence: Optional OCR extraction score.

        Returns:
            QuestionGrade with criterion breakdowns, citations, and review flags.
        """
        student_text = request.student_answer.strip() if request.student_answer else ""

        # 1. Edge Case: Empty student answer
        if not student_text:
            return self._handle_empty_submission(request)

        # 2. Retrieve course material if not supplied
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

        # 3. Retrieve approved teacher corrections as reference examples if available
        teacher_examples = self.trust_service.get_approved_reference_snippets(
            course_id=request.course_id,
            question_id=request.question_id,
        )

        # 4. Format rubric text for prompt
        rubric_lines = [f"Total Question Marks: {request.question_max_marks}"]
        for c in request.rubric.criteria:
            crit_name = c.description
            exp = f"Expected: {', '.join(c.expected_concepts)}" if c.expected_concepts else ""
            alt = f"Acceptable alternatives: {', '.join(c.acceptable_alternatives)}" if c.acceptable_alternatives else ""
            rubric_lines.append(f"- Criterion [{c.criterion_id}] ({c.max_marks} marks): {crit_name}. {exp}. {alt}")
        formatted_rubric = "\n".join(rubric_lines)

        # 5. Construct grounded prompt
        prompt = prompts.build_grading_prompt(
            question=request.question_text,
            student_answer=student_text,
            max_marks=request.question_max_marks,
            rubric_text=formatted_rubric,
            retrieved_evidence=evidence_snippets,
            teacher_examples=teacher_examples if teacher_examples else None,
        )

        if request.model_answer:
            prompt += f"\n### TEACHER MODEL ANSWER REFERENCE (Guidance only; do not demand exact wording):\n{request.model_answer.text}\n"

        # 6. Invoke Gemini for semantic grading
        llm_response = self.gemini_client.generate_structured(
            prompt=prompt,
            response_schema=_LLMQuestionGradeResponse,
            system_instruction=prompts.SYSTEM_ACADEMIC_EVALUATOR,
        )

        # 7. Reconcile criteria marks with rubric and clamp
        evaluations: List[CriterionEvaluation] = []
        rubric_crit_map = {c.criterion_id: c for c in request.rubric.criteria}

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

        initial_grade = QuestionGrade(
            question_id=request.question_id,
            max_marks=request.question_max_marks,
            awarded_marks=round(clamped_total, 2),
            criterion_evaluations=evaluations,
            overall_explanation=llm_response.overall_explanation,
            strengths=llm_response.strengths,
            areas_for_improvement=llm_response.areas_for_improvement,
            confidence=llm_response.confidence,
            review_required=llm_response.review_required,
            review_reasons=list(llm_response.review_reasons),
        )

        # 8. Run unified Trust & Confidence assessment
        trust_res = self.trust_service.assess_submission(
            submission_id=request.submission_id,
            assignment_id=request.assignment_id,
            student_answer=student_text,
            question_grade=initial_grade,
            rubric=request.rubric,
            source_references=refs,
            has_sufficient_evidence=has_sufficient_evidence,
            ocr_confidence=ocr_confidence,
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

    @staticmethod
    def _handle_empty_submission(request: GradingRequest) -> QuestionGrade:
        """Construct zero-score evaluation for an empty student submission."""
        all_missing: List[str] = []
        evaluations: List[CriterionEvaluation] = []

        for c in request.rubric.criteria:
            all_missing.extend(c.expected_concepts)
            evaluations.append(
                CriterionEvaluation(
                    criterion_id=c.criterion_id,
                    criterion_name=c.description,
                    max_marks=c.max_marks,
                    awarded_marks=0.0,
                    explanation="No response provided by student.",
                    matched_concepts=[],
                    missing_concepts=c.expected_concepts or ["Response required"],
                    confidence=1.0,
                )
            )

        return QuestionGrade(
            question_id=request.question_id,
            max_marks=request.question_max_marks,
            awarded_marks=0.0,
            criterion_evaluations=evaluations,
            overall_explanation="No answer was submitted for this question.",
            strengths=[],
            areas_for_improvement=["Attempt the question by addressing the rubric criteria."],
            confidence=1.0,
            review_required=False,
            review_reasons=[],
        )

