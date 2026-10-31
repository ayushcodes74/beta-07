"""Response schemas for teacher-facing submission integrity analysis."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.ocr import BoundingBox


class OCRRegionReference(BaseModel):
    page_number: int = Field(ge=1)
    region_id: str | None = None
    bounding_box: BoundingBox | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    original_text: str = ""


class OCRQualitySummary(BaseModel):
    mean_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    low_confidence_regions: list[OCRRegionReference] = Field(default_factory=list)
    unreadable_pages: list[int] = Field(default_factory=list)
    missing_pages: list[int] = Field(default_factory=list)


class HandwritingAnalysisStatus(BaseModel):
    status: Literal["unavailable"] = "unavailable"
    calibrated_score: None = None
    model_name: None = None
    model_version: None = None
    reason: str = (
        "No validated writer-verification model or labeled validation set is configured."
    )


class IntegrityEvidence(BaseModel):
    submission_id: UUID
    answer_id: str = Field(description="OCR page/region locator; not a persisted answer row.")
    source_submission_id: UUID
    source_answer_id: str = Field(description="OCR page/region locator in the authorized source.")
    source_type: Literal["same_assignment_submission"] = "same_assignment_submission"
    source_reference: str
    current_passage: str
    source_passage: str
    exact_match_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Normalized token-sequence similarity for this passage, not a probability or misconduct score.",
    )
    semantic_similarity_score: float | None = None
    current_regions: list[OCRRegionReference] = Field(default_factory=list)
    source_regions: list[OCRRegionReference] = Field(default_factory=list)
    method: Literal["normalized_token_sequence"] = "normalized_token_sequence"
    ocr_uncertain: bool
    context_note: str | None = None
    detected_at: datetime


class IntegrityReport(BaseModel):
    submission_id: UUID
    review_status: Literal["processing", "needs_teacher_review", "no_matches"]
    comparison_scope: Literal["same_assignment"] = "same_assignment"
    comparisons_completed: int = Field(ge=0)
    comparisons_skipped: int = Field(ge=0)
    comparison_complete: bool
    exact_matching: Literal["normalized_token_sequence"] = "normalized_token_sequence"
    semantic_similarity: Literal["unavailable"] = "unavailable"
    handwriting_analysis: HandwritingAnalysisStatus = Field(default_factory=HandwritingAnalysisStatus)
    ocr_quality: OCRQualitySummary
    evidence: list[IntegrityEvidence] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
