"""Pydantic schemas for Trust, Confidence, and Human Review."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator

from app.schemas.common import BaseSchema, ReviewReasonCategory, SourceReference
from app.schemas.assignment import Rubric
from app.schemas.grading import QuestionGrade


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class InjectionRiskLevel(str, Enum):
    """Risk severity for prompt injection assessment."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ConfidenceLevel(str, Enum):
    """Categorical confidence level."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewStatusEnum(str, Enum):
    """Workflow state for human review items."""

    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class ReviewSeverity(str, Enum):
    """Severity of flagged review issues."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReferenceExampleApprovalStatus(str, Enum):
    """Lifecycle status for teacher-corrected reference examples."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Trust & Confidence Schemas
# ---------------------------------------------------------------------------

class InjectionDetectionResult(BaseSchema):
    """Result of adversarial prompt injection inspection."""

    is_suspicious: bool = Field(
        default=False,
        description="Whether the submission contains potential adversarial instructions.",
    )
    risk_level: InjectionRiskLevel = Field(
        default=InjectionRiskLevel.LOW,
        description="Assessed risk level.",
    )
    detected_patterns: List[str] = Field(
        default_factory=list,
        description="Specific adversarial pattern signatures identified in the text.",
    )
    explanation: str = Field(
        default="No injection patterns detected.",
        description="Detailed diagnostic justification for the assessment.",
    )
    flag_for_review: bool = Field(
        default=False,
        description="Whether this submission must be reviewed by a human instructor.",
    )


class ConfidenceBreakdown(BaseSchema):
    """Multi-factor breakdown of grading confidence."""

    overall: float = Field(
        ge=0.0,
        le=1.0,
        description="Composite confidence score between 0.0 and 1.0.",
    )
    level: ConfidenceLevel = Field(
        description="Categorical confidence rating (HIGH, MEDIUM, LOW).",
    )
    evidence_quality: float = Field(
        ge=0.0,
        le=1.0,
        description="Quality and relevance score of retrieved course excerpts.",
    )
    evidence_coverage: float = Field(
        ge=0.0,
        le=1.0,
        description="Proportion of rubric criteria with direct evidence support.",
    )
    rubric_clarity: float = Field(
        ge=0.0,
        le=1.0,
        description="Non-ambiguity and completeness of rubric criteria.",
    )
    ocr_quality: float = Field(
        ge=0.0,
        le=1.0,
        description="Extraction confidence of source document or student answer text.",
    )
    evaluation_completeness: float = Field(
        ge=0.0,
        le=1.0,
        description="Completeness and consistency of criteria evaluations.",
    )
    explanation: str = Field(
        description="Clear narrative explaining the confidence calculation.",
    )
    review_recommended: bool = Field(
        default=False,
        description="Whether confidence is low enough to warrant teacher review.",
    )


class HumanReviewItem(BaseSchema):
    """An actionable submission item routed for teacher review."""

    review_id: str = Field(description="Unique review item identifier.")
    submission_id: str = Field(description="Student submission ID.")
    assignment_id: str = Field(description="Assignment ID.")
    question_id: Optional[str] = Field(default=None, description="Optional question ID.")
    category: ReviewReasonCategory = Field(description="Standardized review category.")
    severity: ReviewSeverity = Field(
        default=ReviewSeverity.MEDIUM,
        description="Severity level of the issue.",
    )
    reason: str = Field(description="Short summary of the review trigger.")
    explanation: str = Field(description="In-depth explanation and context for the instructor.")
    evidence_references: List[SourceReference] = Field(
        default_factory=list,
        description="Citations from course material relevant to the review decision.",
    )
    suggested_teacher_action: str = Field(
        description="Actionable recommendation for the instructor.",
    )
    status: ReviewStatusEnum = Field(
        default=ReviewStatusEnum.PENDING,
        description="Current review status.",
    )
    created_at: str = Field(description="ISO timestamp of review routing.")
    reviewed_by: Optional[str] = Field(
        default=None,
        description="Instructor ID who completed the review.",
    )
    teacher_notes: Optional[str] = Field(
        default=None,
        description="Notes entered by the reviewing teacher.",
    )


class ReferenceExample(BaseSchema):
    """A teacher-corrected grading example used as few-shot reference."""

    example_id: str = Field(description="Unique reference example ID.")
    course_id: str = Field(description="Course identifier for strict isolation.")
    assignment_id: str = Field(description="Assignment ID.")
    question_id: str = Field(description="Question ID.")
    question_text: str = Field(description="Question prompt.")
    student_answer: str = Field(description="Redacted or original student answer.")
    teacher_corrected_marks: float = Field(ge=0, description="Marks approved by the teacher.")
    max_marks: float = Field(gt=0, description="Maximum possible question marks.")
    teacher_feedback: str = Field(description="Authoritative teacher feedback.")
    teacher_notes: Optional[str] = Field(
        default=None,
        description="Teacher explanation of why this grade was awarded.",
    )
    rubric: Optional[Rubric] = Field(default=None, description="Rubric used for grading.")
    approval_status: ReferenceExampleApprovalStatus = Field(
        default=ReferenceExampleApprovalStatus.PENDING,
        description="Approval state. MUST be APPROVED to be included in grading prompts.",
    )
    is_active: bool = Field(
        default=True,
        description="Whether this reference example is active.",
    )
    created_at: str = Field(description="Creation ISO timestamp.")
    approved_by: Optional[str] = Field(
        default=None,
        description="Teacher ID who approved this reference example.",
    )


class TrustAssessmentResult(BaseSchema):
    """Unified trust, confidence, and review assessment for a submission."""

    injection_result: InjectionDetectionResult = Field(
        description="Prompt injection assessment.",
    )
    confidence_breakdown: ConfidenceBreakdown = Field(
        description="Multi-factor confidence estimation.",
    )
    review_items: List[HumanReviewItem] = Field(
        default_factory=list,
        description="List of specific issues flagged for instructor review.",
    )
    review_required: bool = Field(
        default=False,
        description="True if any review condition was triggered.",
    )

