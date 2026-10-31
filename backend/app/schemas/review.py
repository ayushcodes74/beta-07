"""Teacher review queue and student review-request API schemas.

The review queue groups every submission that needs a teacher's manual attention:
  - ``ocr``:              OCR failed / degraded / cancelled, finished with warnings, or low confidence
  - ``low_trust``:        an AI grade suggestion with low confidence or a review-required flag
  - ``student_requests``: open re-evaluation requests from students unhappy with a published grade
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ReviewRequestStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReviewRequestCreate(BaseModel):
    """Student: why the published grade should be looked at again."""

    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Please explain your request in at least 10 characters.")
        return value


class ReviewRequestResolve(BaseModel):
    """Teacher: close a student's request, optionally with a reply the student can read."""

    status: Literal["resolved", "dismissed"]
    teacher_response: Optional[str] = Field(default=None, max_length=2000)


class ReviewRequestResponse(BaseModel):
    id: UUID
    submission_id: UUID
    student_id: UUID
    reason: str
    status: ReviewRequestStatus
    teacher_response: Optional[str] = None
    resolved_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


ReviewCategory = Literal["ocr", "low_trust", "student_request"]


class ReviewQueueItem(BaseModel):
    category: ReviewCategory
    submission_id: UUID
    assignment_id: UUID
    student_id: UUID
    submission_status: str
    submitted_at: str
    reasons: List[str] = Field(default_factory=list)
    ocr_confidence: Optional[float] = Field(default=None, description="Mean OCR text-block confidence (0-1)")
    trust_score: Optional[float] = Field(default=None, description="AI answer-check confidence (0-1)")
    ai_score: Optional[float] = None
    final_score: Optional[float] = None
    max_score: Optional[float] = None
    grading_status: Optional[str] = None
    review_request: Optional[ReviewRequestResponse] = None


class ReviewQueueThresholds(BaseModel):
    ocr_confidence: float
    trust_score: float


class ReviewQueueResponse(BaseModel):
    ocr: List[ReviewQueueItem] = Field(default_factory=list)
    low_trust: List[ReviewQueueItem] = Field(default_factory=list)
    student_requests: List[ReviewQueueItem] = Field(default_factory=list)
    thresholds: ReviewQueueThresholds
    notes: List[str] = Field(
        default_factory=list,
        description="Data that could not be checked (e.g. OCR engine unreachable), so the queue may be incomplete.",
    )
