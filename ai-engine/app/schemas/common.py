"""Common reusable Pydantic schemas for the AI Engine."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """Base schema with standard configurations."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        validate_assignment=True,
    )


class SourceReference(BaseSchema):
    """Source reference for evidence extracted from course materials."""

    document_id: str = Field(description="Unique identifier of the course document.")
    title: Optional[str] = Field(default=None, description="Title or file name of the document.")
    page_number: Optional[int] = Field(default=None, description="Page number where the evidence appears.")
    section: Optional[str] = Field(default=None, description="Section heading or chapter.")
    snippet: str = Field(description="Exact or relevant excerpt from the course material.")
    similarity_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Vector similarity score from retrieval.",
    )


class ConfidenceScore(BaseSchema):
    """Multi-factor confidence estimation details."""

    overall: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence score between 0.0 and 1.0.",
    )
    retrieval_quality: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Quality and relevance of retrieved documents.",
    )
    evidence_coverage: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Coverage of required concepts by the retrieved evidence.",
    )
    semantic_clarity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Semantic clarity and lack of ambiguity in the student answer.",
    )
    rubric_alignment: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Clarity and non-ambiguity of rubric criteria.",
    )
    reasoning: str = Field(
        default="",
        description="Detailed explanation justifying the calculated confidence.",
    )


class ReviewReasonCategory(str, Enum):
    """Standard categories for flagging human review."""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNUSUAL_APPROACH = "UNUSUAL_APPROACH"
    UNSUPPORTED_CORRECT_ANSWER = "UNSUPPORTED_CORRECT_ANSWER"
    AMBIGUOUS_RUBRIC = "AMBIGUOUS_RUBRIC"
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    UNCERTAIN_SYLLABUS = "UNCERTAIN_SYLLABUS"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class ReviewStatus(BaseSchema):
    """Human review decision status and breakdown."""

    needs_review: bool = Field(
        default=False,
        description="Flag indicating if teacher review is required.",
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Detailed reasons triggering the review flag.",
    )
    flagged_categories: List[ReviewReasonCategory] = Field(
        default_factory=list,
        description="Specific categories that triggered the review requirement.",
    )


class ErrorDetail(BaseSchema):
    """Standardized error structure."""

    code: str = Field(description="Error classification code.")
    message: str = Field(description="Human-readable error description.")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional diagnostic details or metadata.",
    )

