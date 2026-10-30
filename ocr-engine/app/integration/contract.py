"""Integration contract defining the HTTP payload interfaces between TrustGrade Backend and OCR Engine."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.api.schemas import (
    OCRDocumentResult,
    PageResultSchema,
    TextBlockSchema,
    MathBlockSchema,
)


class BackendOCRRequest(BaseModel):
    """Specification of the request payload sent by the backend to process a student submission."""

    submission_id: str = Field(..., description="Unique submission ID from assignments table")
    assignment_id: Optional[str] = Field(default=None, description="Assignment reference")
    student_id: Optional[str] = Field(default=None, description="Student user reference")


class BackendOCRJobResponse(BaseModel):
    """Specification of the response received by the backend upon queuing a submission."""

    job_id: str = Field(..., description="Job identifier for status polling")
    submission_id: str = Field(..., description="Submission reference")
    status: str = Field(..., description="Initial status ('queued' or 'processing')")
    message: str = Field(default="PDF received and queued for processing")


class BackendGradingPayload(BaseModel):
    """Normalized payload ready to be forwarded by the backend to the AI grading engine."""

    submission_id: str = Field(..., description="Submission ID")
    overall_status: str = Field(..., description="OCR status ('completed', 'degraded', etc.)")
    extracted_full_text: str = Field(..., description="Combined page-wise student answer text")
    extracted_formulas_latex: List[str] = Field(default_factory=list, description="All extracted LaTeX formulas")
    page_count: int = Field(..., ge=1)
    requires_manual_teacher_review: bool = Field(default=False)
    quality_warnings: List[str] = Field(default_factory=list)

