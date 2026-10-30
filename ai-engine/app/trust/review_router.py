"""Human Review Routing service.

Identifies submissions requiring teacher intervention, constructs structured
HumanReviewItems with actionable advice, and manages review lifecycle states.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import List, Optional

from app.schemas.common import ReviewReasonCategory, SourceReference
from app.schemas.grading import QuestionGrade
from app.schemas.trust import (
    ConfidenceBreakdown,
    HumanReviewItem,
    InjectionDetectionResult,
    ReviewSeverity,
    ReviewStatusEnum,
)

logger = logging.getLogger(__name__)


# Valid state transitions for review items
_ALLOWED_TRANSITIONS = {
    ReviewStatusEnum.PENDING: {ReviewStatusEnum.IN_REVIEW, ReviewStatusEnum.APPROVED, ReviewStatusEnum.REJECTED, ReviewStatusEnum.NEEDS_CLARIFICATION},
    ReviewStatusEnum.IN_REVIEW: {ReviewStatusEnum.APPROVED, ReviewStatusEnum.REJECTED, ReviewStatusEnum.NEEDS_CLARIFICATION},
    ReviewStatusEnum.NEEDS_CLARIFICATION: {ReviewStatusEnum.IN_REVIEW, ReviewStatusEnum.APPROVED, ReviewStatusEnum.REJECTED},
    ReviewStatusEnum.APPROVED: {ReviewStatusEnum.IN_REVIEW},  # Allow reopening if contested
    ReviewStatusEnum.REJECTED: {ReviewStatusEnum.IN_REVIEW},
}


class HumanReviewRouter:
    """Routes flagged submissions to human instructors and manages review item lifecycles."""

    def __init__(self, confidence_threshold: float = 0.70):
        self.confidence_threshold = confidence_threshold

    def determine_reviews(
        self,
        submission_id: str,
        assignment_id: str,
        question_grade: QuestionGrade,
        confidence: ConfidenceBreakdown,
        injection_result: InjectionDetectionResult,
        source_references: List[SourceReference],
        has_sufficient_evidence: bool = True,
        ocr_confidence: Optional[float] = None,
    ) -> List[HumanReviewItem]:
        """Examine evaluation signals and generate review items for any triggered rules.

        Args:
            submission_id: Student submission identifier.
            assignment_id: Assignment identifier.
            question_grade: The evaluation result for the question.
            confidence: Multi-factor confidence breakdown.
            injection_result: Prompt injection scan result.
            source_references: Supporting course references.
            has_sufficient_evidence: Course material grounding flag.
            ocr_confidence: Optional OCR quality score.

        Returns:
            List of HumanReviewItem instances (empty if no review needed).
        """
        items: List[HumanReviewItem] = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        q_id = question_grade.question_id

        # 1. Prompt Injection Trigger
        if injection_result.is_suspicious and injection_result.flag_for_review:
            items.append(
                HumanReviewItem(
                    review_id=f"rev_inj_{uuid.uuid4().hex[:8]}",
                    submission_id=submission_id,
                    assignment_id=assignment_id,
                    question_id=q_id,
                    category=ReviewReasonCategory.PROMPT_INJECTION_DETECTED,
                    severity=ReviewSeverity.CRITICAL if injection_result.risk_level.value in ("CRITICAL", "HIGH") else ReviewSeverity.HIGH,
                    reason="Adversarial instructions or jailbreak attempt detected in student submission.",
                    explanation=injection_result.explanation,
                    evidence_references=source_references,
                    suggested_teacher_action="Inspect the raw submission text. Evaluate student understanding while ignoring embedded prompt injection commands.",
                    status=ReviewStatusEnum.PENDING,
                    created_at=now,
                )
            )

        # 2. Insufficient Course Evidence Trigger
        if not has_sufficient_evidence:
            items.append(
                HumanReviewItem(
                    review_id=f"rev_evi_{uuid.uuid4().hex[:8]}",
                    submission_id=submission_id,
                    assignment_id=assignment_id,
                    question_id=q_id,
                    category=ReviewReasonCategory.INSUFFICIENT_EVIDENCE,
                    severity=ReviewSeverity.HIGH,
                    reason="Insufficient course evidence: Course materials lack evidence to authoritatively verify question claims.",
                    explanation="No matching course documents found in vector store meeting similarity thresholds.",
                    evidence_references=source_references,
                    suggested_teacher_action="Verify if the student answer is correct using external subject expertise and check course material coverage.",
                    status=ReviewStatusEnum.PENDING,
                    created_at=now,
                )
            )

        # 3. Low Confidence Trigger
        if confidence.overall < self.confidence_threshold and has_sufficient_evidence:
            items.append(
                HumanReviewItem(
                    review_id=f"rev_cnf_{uuid.uuid4().hex[:8]}",
                    submission_id=submission_id,
                    assignment_id=assignment_id,
                    question_id=q_id,
                    category=ReviewReasonCategory.LOW_CONFIDENCE,
                    severity=ReviewSeverity.MEDIUM,
                    reason=f"Overall evaluation confidence ({confidence.overall:.2f}) is below threshold ({self.confidence_threshold:.2f}).",
                    explanation=confidence.explanation,
                    evidence_references=source_references,
                    suggested_teacher_action="Review criterion score allocations and adjust partial marks if the student demonstrated valid alternative approaches.",
                    status=ReviewStatusEnum.PENDING,
                    created_at=now,
                )
            )

        # 4. Low OCR Extraction Quality Trigger
        if ocr_confidence is not None and ocr_confidence < 0.65:
            items.append(
                HumanReviewItem(
                    review_id=f"rev_ocr_{uuid.uuid4().hex[:8]}",
                    submission_id=submission_id,
                    assignment_id=assignment_id,
                    question_id=q_id,
                    category=ReviewReasonCategory.LOW_OCR_CONFIDENCE,
                    severity=ReviewSeverity.HIGH,
                    reason=f"Low OCR text extraction confidence ({ocr_confidence:.2f}).",
                    explanation="Extracted text may be fragmented, degraded, or missing key mathematical expressions.",
                    evidence_references=source_references,
                    suggested_teacher_action="Inspect the original student scan/image to confirm what the student originally wrote.",
                    status=ReviewStatusEnum.PENDING,
                    created_at=now,
                )
            )

        # 5. Evaluator Specific Review Flags
        if question_grade.review_required:
            for r in question_grade.review_reasons:
                if not any(it.reason == r for it in items):
                    items.append(
                        HumanReviewItem(
                            review_id=f"rev_eva_{uuid.uuid4().hex[:8]}",
                            submission_id=submission_id,
                            assignment_id=assignment_id,
                            question_id=q_id,
                            category=ReviewReasonCategory.UNUSUAL_APPROACH,
                            severity=ReviewSeverity.MEDIUM,
                            reason=r,
                            explanation="Evaluator marked this response as requiring teacher confirmation.",
                            evidence_references=source_references,
                            suggested_teacher_action="Confirm mark allocation based on teacher judgment.",
                            status=ReviewStatusEnum.PENDING,
                            created_at=now,
                        )
                    )

        return items

    @staticmethod
    def transition_review_status(
        item: HumanReviewItem,
        new_status: ReviewStatusEnum,
        reviewer_id: str,
        teacher_notes: Optional[str] = None,
    ) -> HumanReviewItem:
        """Validate and apply a status transition to a review item.

        Args:
            item: The HumanReviewItem to update.
            new_status: Desired ReviewStatusEnum.
            reviewer_id: Teacher or admin making the transition.
            teacher_notes: Optional notes explaining the review decision.

        Raises:
            ValueError: If the state transition is invalid.
        """
        current_status = item.status
        allowed = _ALLOWED_TRANSITIONS.get(current_status, set())

        if new_status not in allowed:
            raise ValueError(
                f"Invalid review status transition from '{current_status.value}' to '{new_status.value}'. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

        item.status = new_status
        item.reviewed_by = reviewer_id
        if teacher_notes is not None:
            item.teacher_notes = teacher_notes

        return item
