"""Pydantic schemas for Module 5 OCR API requests, responses, and unified results."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BoundingBoxSchema(BaseModel):
    """Normalized bounding box coordinates."""

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


class TextBlockSchema(BaseModel):
    """Structured text block extracted from a page."""

    block_id: str = Field(..., description="Unique block identifier")
    sequence: int = Field(..., ge=1, description="Reading order sequence")
    type: str = Field(..., description="Classification: 'printed', 'handwritten', or 'unknown'")
    text: str = Field(default="", description="Transcribed text (empty if degraded)")
    confidence: Optional[float] = Field(default=None, description="Model probability or null")
    quality_score: Optional[float] = Field(default=None, description="Image quality metric (0.0 to 1.0)")
    bounding_box: BoundingBoxSchema = Field(..., description="Coordinates on page")
    warnings: List[str] = Field(default_factory=list, description="Block-level warnings")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic metrics")


class MathBlockSchema(BaseModel):
    """Structured mathematical expression extracted from a page."""

    region_id: str = Field(..., description="Unique mathematical region identifier")
    bounding_box: BoundingBoxSchema = Field(..., description="Coordinates on page")
    recognized_text: str = Field(default="", description="Raw recognized mathematical tokens")
    latex: str = Field(default="", description="Standardized LaTeX representation")
    confidence: Optional[float] = Field(default=None, description="Model probability or null")
    quality_score: Optional[float] = Field(default=None, description="Visual quality metric")
    is_readable: bool = Field(default=True, description="Whether formula is legible")
    is_complete: bool = Field(default=True, description="Whether expression is intact")
    requires_manual_review: bool = Field(default=False, description="Teacher review recommendation")
    symbols: List[Dict[str, Any]] = Field(default_factory=list, description="Detected symbols and ambiguities")
    structures: List[Dict[str, Any]] = Field(default_factory=list, description="Fractions, roots, powers, etc.")
    warnings: List[str] = Field(default_factory=list, description="Region warnings")
    recognition_status: str = Field(default="completed", description="Status ('completed', 'degraded', 'unavailable')")
    engine_used: str = Field(default="none", description="OCR engine used")


class PageResultSchema(BaseModel):
    """Complete aggregated recognition result for a single assignment page."""

    page_id: str = Field(..., description="Page identifier (e.g. 'page-1')")
    page_number: int = Field(..., ge=1, description="1-based page number")
    status: str = Field(default="completed", description="Page status ('completed', 'completed_with_warnings', 'degraded', 'failed')")
    width: int = Field(..., ge=1, description="Page width in pixels")
    height: int = Field(..., ge=1, description="Page height in pixels")
    image_path: Optional[str] = Field(default=None, description="Path to rendered page image")
    enhanced_image_path: Optional[str] = Field(default=None, description="Path to enhanced page image")
    text_blocks: List[TextBlockSchema] = Field(default_factory=list, description="Extracted text blocks")
    math_blocks: List[MathBlockSchema] = Field(default_factory=list, description="Extracted mathematical formulas")
    full_text: str = Field(default="", description="Unified page text in reading order")
    combined_latex: str = Field(default="", description="Aggregated LaTeX expressions")
    warnings: List[str] = Field(default_factory=list, description="Page-level warnings")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Page diagnostics and quality scores")


class ProcessingSummarySchema(BaseModel):
    """Performance and execution metrics summary."""

    total_pages: int = Field(..., ge=0, description="Total pages in submission")
    processed_pages: int = Field(..., ge=0, description="Successfully processed pages")
    failed_pages: int = Field(default=0, ge=0, description="Failed pages")
    total_processing_time_ms: float = Field(..., ge=0.0, description="Total duration in milliseconds")
    stage_durations_ms: Dict[str, float] = Field(default_factory=dict, description="Duration per pipeline stage")


class DocumentMetadataSchema(BaseModel):
    """Extracted PDF document information."""

    title: Optional[str] = Field(default=None)
    author: Optional[str] = Field(default=None)
    subject: Optional[str] = Field(default=None)
    creator: Optional[str] = Field(default=None)
    producer: Optional[str] = Field(default=None)
    creation_date: Optional[str] = Field(default=None)
    modification_date: Optional[str] = Field(default=None)


class OCRDocumentResult(BaseModel):
    """Final unified structured response for an assignment OCR processing job."""

    job_id: str = Field(..., description="Unique job identifier")
    submission_id: str = Field(..., description="Student submission reference")
    status: str = Field(
        default="completed",
        description="Overall status: 'completed', 'completed_with_warnings', 'degraded', 'failed'",
    )
    document_metadata: DocumentMetadataSchema = Field(default_factory=DocumentMetadataSchema)
    processing_summary: ProcessingSummarySchema = Field(
        default_factory=lambda: ProcessingSummarySchema(
            total_pages=0, processed_pages=0, failed_pages=0, total_processing_time_ms=0.0
        )
    )
    pages: List[PageResultSchema] = Field(default_factory=list, description="Ordered page results")
    warnings: List[str] = Field(default_factory=list, description="Job-level warnings")
    errors: List[str] = Field(default_factory=list, description="Job-level errors")


class ProcessJobResponse(BaseModel):
    """Response returned upon submission of a PDF processing request."""

    job_id: str = Field(..., description="Unique identifier for tracking the asynchronous job")
    submission_id: str = Field(..., description="Submission identifier")
    status: str = Field(default="queued", description="Initial job status ('queued' or 'processing')")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    message: str = Field(default="PDF received and queued for processing")


class JobStatusResponse(BaseModel):
    """Current execution status of an OCR job."""

    job_id: str = Field(..., description="Unique job identifier")
    submission_id: str = Field(..., description="Submission identifier")
    status: str = Field(
        ...,
        description="Status: 'queued', 'processing', 'completed', 'completed_with_warnings', 'degraded', 'failed'",
    )
    stage: str = Field(
        ...,
        description="Current stage: 'queued', 'ingestion', 'preprocessing', 'recognition', 'math_recognition', 'aggregation', 'done'",
    )
    progress: int = Field(default=0, ge=0, le=100, description="Estimated progress percentage (0 to 100)")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    warnings: List[str] = Field(default_factory=list, description="Aggregated warnings")


class HealthResponse(BaseModel):
    """Service health and model readiness status."""

    status: str = Field(default="healthy", description="Service health ('healthy', 'degraded', 'unhealthy')")
    service_version: str = Field(default="1.0.0", description="OCR Engine service version")
    service_available: bool = Field(default=True, description="Whether API service is responsive")
    modules: Dict[str, str] = Field(
        default_factory=dict,
        description="Availability status of Modules 1 through 4 ('available', 'degraded', 'unavailable')",
    )
    models: Dict[str, str] = Field(
        default_factory=dict,
        description="Readiness status of deep-learning models ('loaded', 'unavailable', 'failed')",
    )
    active_jobs: int = Field(default=0, description="Number of currently executing background jobs")

