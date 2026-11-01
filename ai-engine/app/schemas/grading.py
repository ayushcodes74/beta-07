"""Pydantic schemas for AI Grading and Feedback."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator, model_validator

from app.schemas.common import BaseSchema, SourceReference, ReviewReasonCategory
from app.schemas.assignment import ModelAnswer, QuestionType, Rubric


class GradingStatus(str, Enum):
    """Execution status for submission grading."""

    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class GradingRequest(BaseSchema):
    """Payload representing a single student question submission to be graded."""

    course_id: str = Field(description="Target course identifier.")
    assignment_id: str = Field(description="Target assignment identifier.")
    submission_id: str = Field(description="Unique submission identifier.")
    question_id: str = Field(description="Target question identifier.")
    question_text: str = Field(description="The question prompt given to the student.")
    question_max_marks: float = Field(gt=0, description="Maximum possible marks for this question.")
    student_answer: str = Field(default="", description="The raw student response provided by OCR or text input.")
    rubric: Optional[Rubric] = Field(
        default=None,
        description="Teacher-approved grading criteria rubric (optional).",
    )
    model_answer: Optional[ModelAnswer] = Field(
        default=None,
        description="Teacher-approved model answer for conceptual guidance.",
    )
    expected_answer: Optional[str] = Field(
        default=None,
        description="Plain-text teacher-provided expected answer for subjective questions.",
    )
    instructions: Optional[str] = Field(
        default=None,
        description="Teacher-provided grading instructions.",
    )
    question_type: Optional[QuestionType] = Field(
        default=QuestionType.SUBJECTIVE,
        description="Question type: MCQ or SUBJECTIVE.",
    )
    selected_option_id: Optional[str] = Field(
        default=None,
        description="For MCQ: ID of the option selected by student (e.g. 'A', 'B').",
    )
    correct_option_id: Optional[str] = Field(
        default=None,
        description="For MCQ: ID of the correct option specified by the teacher.",
    )
    ocr_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional OCR text extraction confidence score (0.0 to 1.0).",
    )
    context: Optional[str] = Field(
        default=None,
        description="Optional additional course or question context.",
    )
    teacher_corrections: List[str] = Field(
        default_factory=list,
        description="Teacher corrections of earlier AI grading of this question; the grader must follow them.",
    )
    reference_images: List["ReferenceImage"] = Field(
        default_factory=list,
        max_length=4,
        description="Pictures the teacher attached to this question (graph, diagram, ...); shown to the grader.",
    )


class ReferenceImage(BaseSchema):
    """A picture attached to a question, passed to a multimodal grader."""

    mime_type: str = Field(pattern=r"^image/(png|jpeg|webp)$")
    data_base64: str = Field(max_length=6_000_000, description="Base64 image bytes (about 4 MB max)")


GradingRequest.model_rebuild()


class CriterionEvaluation(BaseSchema):
    """Evaluation breakdown for a single rubric criterion."""

    criterion_id: str = Field(description="Rubric criterion identifier.")
    criterion_name: Optional[str] = Field(
        default=None,
        description="Short label or title for the criterion.",
    )
    max_marks: float = Field(ge=0, description="Maximum marks for this criterion.")
    awarded_marks: float = Field(ge=0, description="Marks awarded to student.")
    explanation: str = Field(description="Reasoning explaining the marks awarded or deducted.")
    matched_concepts: List[str] = Field(
        default_factory=list,
        description="Concepts correctly demonstrated by the student.",
    )
    missing_concepts: List[str] = Field(
        default_factory=list,
        description="Expected concepts omitted or misunderstood.",
    )
    evidence_references: List[SourceReference] = Field(
        default_factory=list,
        description="Citations from course materials supporting the grading decision.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score in this criterion evaluation.",
    )

    @model_validator(mode="after")
    def validate_marks(self) -> CriterionEvaluation:
        if self.awarded_marks > self.max_marks + 1e-4:
            raise ValueError(
                f"awarded_marks ({self.awarded_marks}) cannot exceed max_marks ({self.max_marks}) "
                f"for criterion '{self.criterion_id}'."
            )
        return self


class MethodApproach(str, Enum):
    """How the student's method relates to what the course taught for this question."""

    TAUGHT = "taught"  # the method in the answer key / course material
    ALTERNATIVE_VALID = "alternative_valid"  # a different method, and its working is correct
    ALTERNATIVE_INVALID = "alternative_invalid"  # a different method, but the working is wrong
    UNCLEAR = "unclear"  # cannot tell (too little working, unreadable, off-topic)


class MethodAssessment(BaseSchema):
    """Whether the student solved the question with a method the course did not teach.

    A valid untaught method is graded on correctness like any other answer; this record lets the
    teacher see it, check web sources for the method, and decide on a bonus for that question.
    """

    approach: MethodApproach = Field(default=MethodApproach.TAUGHT)
    method_name: str = Field(default="", description="Short name of the student's method, e.g. 'integration by parts'.")
    taught_method: str = Field(default="", description="The method the answer key / course material expects.")
    explanation: str = Field(default="", description="Why the student's method is (in)valid, step by step.")


class QuestionGrade(BaseSchema):
    """Grading result for an individual question."""

    question_id: str = Field(description="Question identifier.")
    max_marks: float = Field(gt=0, description="Maximum marks possible.")
    awarded_marks: float = Field(ge=0, description="Total marks awarded across all criteria.")
    criterion_evaluations: List[CriterionEvaluation] = Field(
        min_length=1,
        description="Detailed evaluations per rubric criterion.",
    )
    overall_explanation: str = Field(description="Summary explanation of the grading.")
    strengths: List[str] = Field(
        default_factory=list,
        description="Key strengths demonstrated in the student answer.",
    )
    areas_for_improvement: List[str] = Field(
        default_factory=list,
        description="Specific suggestions for improvement.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Calculated confidence in the grading accuracy.",
    )
    review_required: bool = Field(
        default=False,
        description="Whether teacher review is flagged.",
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Reasons why human review is required.",
    )
    evidence_status: str = Field(
        default="not_requested",
        description="Course-material RAG evidence: 'available', 'unavailable', or 'not_requested'.",
    )
    evidence_unavailable_reason: Optional[str] = Field(
        default=None,
        description="Why no course evidence was used (no materials indexed, nothing relevant, embeddings missing).",
    )
    evidence: List[SourceReference] = Field(
        default_factory=list,
        description="Course passages retrieved for this question, with similarity scores, passed to the grader.",
    )
    method_assessment: Optional[MethodAssessment] = Field(
        default=None,
        description="Set for subjective questions the LLM graded: taught method or a (valid) alternative one.",
    )

    @model_validator(mode="after")
    def validate_totals(self) -> QuestionGrade:
        # Clamp awarded marks strictly between 0 and max_marks
        clamped = max(0.0, min(self.awarded_marks, self.max_marks))
        # Criteria sum reconciliation with floating point tolerance
        crit_sum = sum(c.awarded_marks for c in self.criterion_evaluations)
        if abs(crit_sum - clamped) > 0.05:
            clamped = round(crit_sum, 2)
        object.__setattr__(self, "awarded_marks", clamped)
        return self


class GradingResult(BaseSchema):
    """Complete grading outcome for a submission across one or more questions."""

    submission_id: str = Field(description="Submission identifier.")
    assignment_id: str = Field(description="Assignment identifier.")
    total_awarded_marks: float = Field(ge=0, description="Sum of awarded marks.")
    total_max_marks: float = Field(gt=0, description="Sum of maximum possible marks.")
    percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Percentage score achieved.")
    question_results: List[QuestionGrade] = Field(
        min_length=1,
        description="Results per evaluated question.",
    )
    overall_feedback: str = Field(description="Constructive student feedback summary.")
    review_required: bool = Field(
        default=False,
        description="True if any question or overall score warrants teacher review.",
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Explanations triggering review flags.",
    )
    grading_status: GradingStatus = Field(
        default=GradingStatus.COMPLETED,
        description="Current workflow status.",
    )
    rag: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Course-material RAG summary: status, course_id, indexed materials, embedding model.",
    )

    @model_validator(mode="after")
    def compute_percentage(self) -> GradingResult:
        pct = 0.0
        if self.total_max_marks > 0:
            pct = round((self.total_awarded_marks / self.total_max_marks) * 100.0, 2)
        object.__setattr__(self, "percentage", pct)
        if self.review_required and self.grading_status == GradingStatus.COMPLETED:
            object.__setattr__(self, "grading_status", GradingStatus.NEEDS_REVIEW)
        return self
