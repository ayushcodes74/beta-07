"""Pydantic schemas for OCR engine integration and AI grading handoff."""

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Normalized bounding box coordinates on a page."""

    x1: int = Field(..., ge=0)
    y1: int = Field(..., ge=0)
    x2: int = Field(..., ge=0)
    y2: int = Field(..., ge=0)

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


class TextBlock(BaseModel):
    """Structured text block extracted from an assignment page."""

    block_id: str
    sequence: int = Field(..., ge=1)
    type: str  # 'printed', 'handwritten', or 'unknown'
    text: str = ""
    confidence: Optional[float] = None
    quality_score: Optional[float] = None
    bounding_box: BoundingBox
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MathBlock(BaseModel):
    """Structured mathematical expression extracted from an assignment page."""

    region_id: str
    bounding_box: BoundingBox
    recognized_text: str = ""
    latex: str = ""
    confidence: Optional[float] = None
    quality_score: Optional[float] = None
    is_readable: bool = True
    is_complete: bool = True
    requires_manual_review: bool = False
    symbols: List[Dict[str, Any]] = Field(default_factory=list)
    structures: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recognition_status: str = "completed"
    engine_used: str = "none"


class PageResult(BaseModel):
    """Aggregated OCR recognition result for a single page."""

    page_id: str
    page_number: int = Field(..., ge=1)
    status: str = "completed"
    width: int = Field(..., ge=1)
    height: int = Field(..., ge=1)
    image_path: Optional[str] = None
    enhanced_image_path: Optional[str] = None
    text_blocks: List[TextBlock] = Field(default_factory=list)
    math_blocks: List[MathBlock] = Field(default_factory=list)
    full_text: str = ""
    combined_latex: str = ""
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProcessingSummary(BaseModel):
    """Execution metrics and stage timings from OCR engine."""

    total_pages: int = Field(..., ge=0)
    processed_pages: int = Field(..., ge=0)
    failed_pages: int = Field(default=0, ge=0)
    total_processing_time_ms: float = Field(..., ge=0.0)
    stage_durations_ms: Dict[str, float] = Field(default_factory=dict)


class DocumentMetadata(BaseModel):
    """PDF metadata extracted during ingestion."""

    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None


class OCRDocumentResult(BaseModel):
    """Final unified structured document result from the OCR microservice."""

    job_id: str
    submission_id: str
    status: str = "completed"  # 'completed', 'completed_with_warnings', 'degraded', 'failed'
    document_metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    processing_summary: ProcessingSummary = Field(
        default_factory=lambda: ProcessingSummary(
            total_pages=0, processed_pages=0, failed_pages=0, total_processing_time_ms=0.0
        )
    )
    pages: List[PageResult] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class ProcessJobResponse(BaseModel):
    """Response returned upon submitting a PDF to the OCR engine."""

    job_id: str
    submission_id: Optional[str] = None
    status: str = "queued"
    created_at: str
    message: str = "PDF submission accepted and scheduled for processing."


class JobStatusResponse(BaseModel):
    """Status query response from OCR engine."""

    job_id: str
    submission_id: Optional[str] = None
    status: str  # 'queued', 'processing', 'completed', 'completed_with_warnings', 'degraded', 'failed', 'cancelled'
    stage: str  # 'queued', 'ingestion', 'preprocessing', 'recognition', 'math_recognition', 'aggregation', 'done'
    progress: int = Field(default=0, ge=0, le=100)
    created_at: str
    updated_at: str
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """OCR service health and readiness."""

    status: str
    service_version: str = "1.0.0"
    service_available: bool = True
    modules: Dict[str, str] = Field(default_factory=dict)
    models: Dict[str, str] = Field(default_factory=dict)
    active_jobs: int = 0


# --------------------------------------------------------------------------
# Backend Submission OCR & AI Grading Schemas
# --------------------------------------------------------------------------


class SubmissionOCRStatusResponse(BaseModel):
    """Backend status response exposed to students/teachers for an assignment submission."""

    submission_id: UUID
    assignment_id: UUID
    student_id: UUID
    status: str  # e.g., 'submitted', 'ocr_queued', 'ocr_processing', 'ocr_completed', 'ocr_degraded', 'ocr_failed'
    ocr_job_id: Optional[str] = None
    ocr_stage: Optional[str] = None
    ocr_progress: int = 0
    warnings: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
    submitted_at: Optional[str] = Field(default=None, description="When the work was (last) handed in")
    late_status: Optional[Literal["pending", "accepted", "rejected"]] = Field(
        default=None, description="Set only for submissions handed in after the due date"
    )
    late_penalty_percent: Optional[float] = Field(
        default=None, description="Accepted late work: % deducted from the final score when published"
    )
    late_decision_note: Optional[str] = None
    late_decided_at: Optional[str] = None


class AIGradingPageContent(BaseModel):
    """Structured page-level content prepared for AI grading."""

    page_number: int
    text_content: str
    latex_formulas: List[str] = Field(default_factory=list)
    text_blocks_count: int = 0
    math_blocks_count: int = 0
    page_status: str
    requires_manual_review: bool = False
    warnings: List[str] = Field(default_factory=list)


class AIGradingPayload(BaseModel):
    """Clean backend boundary payload prepared for AI grading handoff (Phase 4)."""

    submission_id: UUID
    assignment_id: UUID
    student_id: UUID
    ocr_job_id: str
    overall_status: str  # 'completed', 'completed_with_warnings', 'degraded'
    page_count: int
    full_text: str
    all_formulas_latex: List[str] = Field(default_factory=list)
    pages: List[AIGradingPageContent] = Field(default_factory=list)
    requires_manual_teacher_review: bool = False
    system_warnings: List[str] = Field(default_factory=list)
    ocr_metadata: Dict[str, Any] = Field(default_factory=dict)
