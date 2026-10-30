"""Unified Trust and Human Review Orchestrator.

Coordinates prompt injection detection, multi-factor confidence estimation,
human review routing, and teacher-approved reference example management.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.llm.gemini_client import GeminiClient
from app.schemas.assignment import Rubric
from app.schemas.common import SourceReference
from app.schemas.grading import QuestionGrade
from app.schemas.trust import (
    ConfidenceBreakdown,
    HumanReviewItem,
    InjectionDetectionResult,
    ReferenceExample,
    TrustAssessmentResult,
)
from app.trust.confidence import ConfidenceEstimator
from app.trust.injection_detector import PromptInjectionDetector
from app.trust.reference_examples import ReferenceExampleService, ReferenceExampleStore
from app.trust.review_router import HumanReviewRouter

logger = logging.getLogger(__name__)


class TrustService:
    """Central service responsible for submission trust, confidence, and teacher review routing."""

    def __init__(
        self,
        injection_detector: Optional[PromptInjectionDetector] = None,
        confidence_estimator: Optional[ConfidenceEstimator] = None,
        review_router: Optional[HumanReviewRouter] = None,
        reference_example_service: Optional[ReferenceExampleService] = None,
        gemini_client: Optional[GeminiClient] = None,
    ):
        """Initialize TrustService with all subcomponents."""
        self.injection_detector = injection_detector or PromptInjectionDetector(gemini_client=gemini_client)
        self.confidence_estimator = confidence_estimator or ConfidenceEstimator()
        self.review_router = review_router or HumanReviewRouter()
        self.example_service = reference_example_service or ReferenceExampleService()

    def assess_submission(
        self,
        submission_id: str,
        assignment_id: str,
        student_answer: str,
        question_grade: QuestionGrade,
        rubric: Rubric,
        source_references: List[SourceReference],
        has_sufficient_evidence: bool = True,
        ocr_confidence: Optional[float] = None,
        question_context: Optional[str] = None,
    ) -> TrustAssessmentResult:
        """Run complete trust analysis: prompt injection, confidence, and human review routing.

        Args:
            submission_id: Submission identifier.
            assignment_id: Assignment identifier.
            student_answer: Raw student answer text.
            question_grade: Evaluated QuestionGrade.
            rubric: Grading rubric.
            source_references: Citations from course materials.
            has_sufficient_evidence: Whether evidence was found in course materials.
            ocr_confidence: Optional OCR extraction score.
            question_context: Optional question prompt.

        Returns:
            TrustAssessmentResult containing injection result, confidence breakdown,
            and any review items requiring teacher intervention.
        """
        # 1. Prompt Injection Scan
        injection_res = self.injection_detector.detect(
            student_answer=student_answer,
            question_context=question_context,
        )

        # 2. Multi-factor Confidence Estimation
        confidence = self.confidence_estimator.calculate_confidence(
            question_grade=question_grade,
            rubric=rubric,
            source_references=source_references,
            ocr_confidence=ocr_confidence,
            has_sufficient_evidence=has_sufficient_evidence,
        )

        # 3. Human Review Routing
        review_items = self.review_router.determine_reviews(
            submission_id=submission_id,
            assignment_id=assignment_id,
            question_grade=question_grade,
            confidence=confidence,
            injection_result=injection_res,
            source_references=source_references,
            has_sufficient_evidence=has_sufficient_evidence,
            ocr_confidence=ocr_confidence,
        )

        review_required = bool(review_items) or confidence.review_recommended or injection_res.flag_for_review

        return TrustAssessmentResult(
            injection_result=injection_res,
            confidence_breakdown=confidence,
            review_items=review_items,
            review_required=review_required,
        )

    def get_approved_reference_snippets(
        self,
        course_id: str,
        question_id: Optional[str] = None,
        max_examples: int = 3,
    ) -> List[str]:
        """Fetch teacher-approved few-shot reference examples for a course."""
        return self.example_service.get_reference_snippets(
            course_id=course_id,
            question_id=question_id,
            max_examples=max_examples,
        )

    def record_teacher_correction(
        self,
        course_id: str,
        assignment_id: str,
        question_id: str,
        question_text: str,
        student_answer: str,
        teacher_corrected_marks: float,
        max_marks: float,
        teacher_feedback: str,
        teacher_notes: Optional[str] = None,
        auto_approve: bool = False,
        reviewer_id: Optional[str] = None,
    ) -> ReferenceExample:
        """Store a teacher-corrected grading example."""
        return self.example_service.record_correction(
            course_id=course_id,
            assignment_id=assignment_id,
            question_id=question_id,
            question_text=question_text,
            student_answer=student_answer,
            teacher_corrected_marks=teacher_corrected_marks,
            max_marks=max_marks,
            teacher_feedback=teacher_feedback,
            teacher_notes=teacher_notes,
            auto_approve=auto_approve,
            reviewer_id=reviewer_id,
        )

