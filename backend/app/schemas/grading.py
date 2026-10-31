"""AI answer-check (grading suggestion) API schemas.

A suggestion is produced by the AI Engine from the submission's OCR text and the teacher's answer
keys. It is review evidence for the teacher, never a final or published grade.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CourseEvidence(BaseModel):
    """A course-material passage retrieved (RAG) and given to the grader for one question."""

    material_id: str
    filename: Optional[str] = None
    page_number: Optional[int] = None
    similarity: Optional[float] = Field(default=None, description="Cosine similarity to the question (0-1)")
    content: str


class QuestionGradeSuggestion(BaseModel):
    number: int = Field(ge=1, description="1-based question position in the assignment")
    question_text: str
    question_type: str
    max_marks: float
    awarded_marks: float
    raw_awarded_marks: Optional[float] = Field(
        default=None, description="AI score before the full-marks-at-coverage scaling policy"
    )
    explanation: str
    strengths: List[str] = Field(default_factory=list)
    areas_for_improvement: List[str] = Field(default_factory=list)
    matched_concepts: List[str] = Field(default_factory=list)
    missing_concepts: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    review_required: bool = False
    review_reasons: List[str] = Field(default_factory=list)
    evidence_status: str = Field(
        default="not_requested",
        description="Course-material evidence: 'available', 'unavailable' (see reason), or 'not_requested'",
    )
    evidence_unavailable_reason: Optional[str] = None
    evidence: List[CourseEvidence] = Field(default_factory=list)
    teacher_corrections_used: int = Field(
        default=0, description="How many earlier teacher corrections of this question the AI was given"
    )


class GradingSuggestionResponse(BaseModel):
    submission_id: UUID
    assignment_id: UUID
    total_awarded_marks: float
    total_max_marks: float
    percentage: float
    overall_feedback: str
    review_required: bool
    review_reasons: List[str] = Field(default_factory=list)
    questions: List[QuestionGradeSuggestion]
    ocr_confidence: Optional[float] = None
    graded_at: datetime
    saved: bool = Field(description="Whether the suggestion was stored as a pending-review grading result")
    rag: Optional[dict] = Field(
        default=None,
        description="Course-material RAG summary: status (available/partial/unavailable), reason, materials indexed, model",
    )
    scoring: Optional[dict] = Field(
        default=None,
        description="Scoring policy applied: full_marks_at (coverage share for full marks) and raw_total",
    )
    status: str = Field(default="pending_review", description="Suggestions always start as pending teacher review")
    teacher_corrections: List["GradingCorrection"] = Field(
        default_factory=list, description="Corrections the teacher recorded on this submission's AI check"
    )


class GradingCorrectionIn(BaseModel):
    """Teacher says where the AI got one question wrong and what the right mark is."""

    question_number: int = Field(ge=1)
    teacher_marks: float = Field(ge=0)
    note: str = Field(min_length=1, max_length=2000, description="Why the AI's grading was wrong")


class GradingCorrectionsRequest(BaseModel):
    """The full set of corrections for a submission (replaces any previously saved ones)."""

    corrections: List[GradingCorrectionIn] = Field(default_factory=list, max_length=50)


class GradingCorrection(BaseModel):
    """A stored teacher correction. Given to the AI when the same question is graded again."""

    question_number: int
    question_text: str
    max_marks: float
    ai_marks: Optional[float] = None
    ai_explanation: str = ""
    teacher_marks: float
    note: str
    teacher_id: Optional[UUID] = None
    created_at: Optional[datetime] = None


class GradePublishRequest(BaseModel):
    """Teacher's final, reviewed grade. Publishing makes it visible to the student."""

    final_score: float = Field(ge=0, description="Teacher-approved score; may differ from the AI suggestion")
    final_feedback: str = Field(default="", max_length=10_000, description="Feedback shown to the student")
    show_solutions: bool = Field(
        default=True,
        description="Show each question's expected solution to the student once the assignment's due date has passed",
    )


class PublishedQuestionResult(BaseModel):
    """Why one question got its mark, as published to the student (snapshot taken at publish time).

    Excludes matched/missing concepts and course evidence. The teacher's expected solution is included
    only when the teacher chose to share it, and is withheld from students until the due date.
    """

    number: int
    question_text: str
    awarded_marks: Optional[float] = Field(default=None, description="None when there is no per-question mark")
    max_marks: float
    explanation: str = ""
    strengths: List[str] = Field(default_factory=list)
    areas_for_improvement: List[str] = Field(default_factory=list)
    teacher_comment: Optional[str] = Field(
        default=None, description="The teacher's note when they changed the AI's mark for this question"
    )
    expected_solution: Optional[str] = Field(
        default=None, description="The teacher's expected answer / correct option (once solutions are released)"
    )


class PublishedGradeResponse(BaseModel):
    """A teacher-approved, published grade. Contains no AI evidence or answer keys."""

    submission_id: UUID
    questions: List[PublishedQuestionResult] = Field(
        default_factory=list, description="Per-question marks, reasons and (when released) expected solutions"
    )
    solutions_available_at: Optional[datetime] = Field(
        default=None,
        description="Set while expected solutions are still withheld from the student: when they will appear",
    )
    final_score: float
    max_score: Optional[float] = None
    final_feedback: str
    status: str
    reviewed_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    late_penalty_percent: Optional[float] = Field(
        default=None, description="Late-submission deduction applied to final_score, if any"
    )
    score_before_late_penalty: Optional[float] = None


class LateDecisionRequest(BaseModel):
    """Teacher's ruling on a submission handed in after the due date."""

    decision: Literal["accepted", "rejected", "pending"] = Field(
        description="accepted = grade it (minus penalty_percent); rejected = not accepted; pending = undo decision"
    )
    penalty_percent: float = Field(
        default=0, ge=0, le=100, description="Accepted only: % deducted from the final score (50 = half marks)"
    )
    note: str = Field(default="", max_length=2000, description="Optional explanation shown to the student")
