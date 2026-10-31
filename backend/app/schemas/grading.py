"""AI answer-check (grading suggestion) API schemas.

A suggestion is produced by the AI Engine from the submission's OCR text and the teacher's answer
keys. It is review evidence for the teacher, never a final or published grade.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
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


class GradePublishRequest(BaseModel):
    """Teacher's final, reviewed grade. Publishing makes it visible to the student."""

    final_score: float = Field(ge=0, description="Teacher-approved score; may differ from the AI suggestion")
    final_feedback: str = Field(default="", max_length=10_000, description="Feedback shown to the student")


class PublishedGradeResponse(BaseModel):
    """A teacher-approved, published grade. Contains no AI evidence or answer keys."""

    submission_id: UUID
    final_score: float
    max_score: Optional[float] = None
    final_feedback: str
    status: str
    reviewed_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
