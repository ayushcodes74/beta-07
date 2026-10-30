"""Assignment and Syllabus Intelligence Pydantic schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator, model_validator

from app.schemas.common import BaseSchema, SourceReference


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SyllabusCoverageStatus(str, Enum):
    """Classification states for question syllabus coverage."""

    IN_SYLLABUS = "IN_SYLLABUS"
    PARTIALLY_IN_SYLLABUS = "PARTIALLY_IN_SYLLABUS"
    OUT_OF_SYLLABUS = "OUT_OF_SYLLABUS"
    UNCERTAIN = "UNCERTAIN"


class QuestionType(str, Enum):
    """Supported question types for assignments."""

    MCQ = "MCQ"
    SUBJECTIVE = "SUBJECTIVE"
    MIXED = "MIXED"


class DifficultyLevel(str, Enum):
    """Academic difficulty levels."""

    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


# ---------------------------------------------------------------------------
# Syllabus Detection Schemas
# ---------------------------------------------------------------------------

class SyllabusCoverageResult(BaseSchema):
    """Structured response detailing syllabus boundary verification."""

    status: SyllabusCoverageStatus = Field(
        description="Overall coverage classification.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score in the classification (0.0 to 1.0).",
    )
    covered_concepts: List[str] = Field(
        default_factory=list,
        description="Concepts from the question found in the syllabus/course material.",
    )
    uncovered_concepts: List[str] = Field(
        default_factory=list,
        description="Concepts from the question missing from the syllabus/course material.",
    )
    reasoning: str = Field(
        description="Detailed explanation justifying the classification decision.",
    )
    evidence: List[SourceReference] = Field(
        default_factory=list,
        description="Citations from retrieved course documents supporting the classification.",
    )


# ---------------------------------------------------------------------------
# Rubric & Answer Schemas
# ---------------------------------------------------------------------------

class MCQOption(BaseSchema):
    """An individual multiple choice option."""

    id: str = Field(description="Option identifier (e.g. 'A', 'B', 'C', 'D').")
    text: str = Field(description="The text content of the option.")
    is_correct: bool = Field(description="Whether this is the correct answer.")
    explanation: Optional[str] = Field(
        default=None,
        description="Explanation of why this option is correct or incorrect.",
    )


class RubricCriterion(BaseSchema):
    """Individual grading criterion with specific mark allocation."""

    criterion_id: str = Field(description="Unique criterion identifier.")
    description: str = Field(description="Explanation of what the student must demonstrate.")
    max_marks: float = Field(gt=0, description="Marks allocated to this criterion.")
    expected_concepts: List[str] = Field(
        default_factory=list,
        description="Core concepts required to earn full credit.",
    )
    acceptable_alternatives: List[str] = Field(
        default_factory=list,
        description="Acceptable alternative terminology or conceptual approaches.",
    )


class Rubric(BaseSchema):
    """Complete rubric for a subjective question."""

    criteria: List[RubricCriterion] = Field(
        min_length=1,
        description="List of marking criteria.",
    )
    total_marks: float = Field(gt=0, description="Total maximum marks for the question.")
    instructions: Optional[str] = Field(
        default=None,
        description="General instructions for the grader.",
    )

    @model_validator(mode="after")
    def validate_marks_sum(self) -> Rubric:
        """Ensure criteria marks sum to total_marks with floating-point tolerance."""
        criteria_sum = sum(c.max_marks for c in self.criteria)
        if abs(criteria_sum - self.total_marks) > 0.05:
            # Auto-reconcile or raise if drastically different
            raise ValueError(
                f"Sum of criteria marks ({criteria_sum:.2f}) does not match total_marks ({self.total_marks:.2f})"
            )
        return self


class ModelAnswer(BaseSchema):
    """Authoritative model answer grounded in course material."""

    text: str = Field(description="Complete, well-articulated model answer.")
    key_points: List[str] = Field(
        default_factory=list,
        description="Bullet points of mandatory conceptual elements.",
    )
    acceptable_approaches: List[str] = Field(
        default_factory=list,
        description="Valid alternative formulations or methods.",
    )


# ---------------------------------------------------------------------------
# Assignment Draft Schemas
# ---------------------------------------------------------------------------

class QuestionDraft(BaseSchema):
    """Draft question generated for teacher review."""

    question_id: str = Field(description="Unique question identifier.")
    question_type: QuestionType = Field(description="MCQ or SUBJECTIVE.")
    question_text: str = Field(description="The prompt or question given to students.")
    marks: float = Field(gt=0, description="Marks allocated to this question.")
    difficulty: DifficultyLevel = Field(
        default=DifficultyLevel.MEDIUM,
        description="Difficulty level.",
    )
    learning_objective: Optional[str] = Field(
        default=None,
        description="Target educational objective or Bloom's taxonomy level.",
    )
    mcq_options: Optional[List[MCQOption]] = Field(
        default=None,
        description="Options if question_type is MCQ.",
    )
    model_answer: Optional[ModelAnswer] = Field(
        default=None,
        description="Model answer for subjective questions or comprehensive reference.",
    )
    rubric: Optional[Rubric] = Field(
        default=None,
        description="Grading rubric for subjective questions.",
    )
    source_evidence: List[SourceReference] = Field(
        default_factory=list,
        description="Course excerpts grounding this question.",
    )
    has_sufficient_evidence: bool = Field(
        default=True,
        description="Flag indicating whether course evidence adequately supports this question.",
    )
    evidence_notes: Optional[str] = Field(
        default=None,
        description="Notes on evidence coverage or potential gaps.",
    )

    @model_validator(mode="after")
    def validate_type_consistency(self) -> QuestionDraft:
        """Validate MCQ vs SUBJECTIVE required fields."""
        if self.question_type == QuestionType.MCQ:
            if not self.mcq_options or len(self.mcq_options) < 2:
                raise ValueError("MCQ questions must include at least 2 options.")
            correct_count = sum(1 for o in self.mcq_options if o.is_correct)
            if correct_count != 1:
                raise ValueError(f"MCQ questions must have exactly 1 correct option, got {correct_count}.")
        return self


class AssignmentDraft(BaseSchema):
    """Complete draft assignment requiring teacher approval."""

    assignment_id: str = Field(description="Unique assignment identifier.")
    course_id: str = Field(description="Target course ID.")
    topic: str = Field(description="Subject topic covered by the assignment.")
    title: str = Field(description="Human-readable assignment title.")
    instructions: Optional[str] = Field(
        default="Answer all questions carefully.",
        description="Student-facing instructions.",
    )
    total_marks: float = Field(gt=0, description="Total maximum marks for the assignment.")
    questions: List[QuestionDraft] = Field(
        min_length=1,
        description="List of draft questions.",
    )
    status: str = Field(
        default="DRAFT",
        description="Lifecycle status. Must remain DRAFT until teacher approval.",
    )
    created_at: Optional[str] = Field(default=None, description="ISO timestamp.")

    @field_validator("status")
    @classmethod
    def enforce_draft_status(cls, v: str) -> str:
        """Ensure initial generated assignments are strictly drafts."""
        if v.upper() != "DRAFT":
            raise ValueError("All freshly generated assignments must have status='DRAFT'.")
        return "DRAFT"


class AssignmentGenerationRequest(BaseSchema):
    """Teacher request to generate a draft assignment."""

    course_id: str = Field(description="Target course ID.")
    topic: str = Field(description="Target topic or chapter.")
    question_type: QuestionType = Field(
        default=QuestionType.MIXED,
        description="MCQ, SUBJECTIVE, or MIXED.",
    )
    question_count: int = Field(
        default=5,
        ge=1,
        le=30,
        description="Number of questions to generate.",
    )
    difficulty: DifficultyLevel = Field(
        default=DifficultyLevel.MEDIUM,
        description="Target difficulty level.",
    )
    total_marks: float = Field(
        default=20.0,
        gt=0,
        description="Total desired marks for the assignment.",
    )
    teacher_instructions: Optional[str] = Field(
        default=None,
        description="Additional teacher instructions or focus areas.",
    )

