"""Pydantic schemas for Image Preprocessing input and output models."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ImageQualityMetrics(BaseModel):
    """Quality and diagnostic metrics extracted during image analysis."""

    width: int = Field(..., ge=1, description="Image width in pixels")
    height: int = Field(..., ge=1, description="Image height in pixels")
    estimated_skew_angle: float = Field(default=0.0, description="Estimated skew angle in degrees")
    corrected_skew_angle: float = Field(default=0.0, description="Actual skew correction angle applied in degrees")
    orientation_corrected: bool = Field(default=False, description="Whether 90/180/270 degree orientation correction was applied")
    is_low_resolution: bool = Field(default=False, description="Flag indicating if image resolution is sub-optimal for OCR")
    needs_review: bool = Field(default=False, description="Flag indicating that human review is recommended")
    warnings: List[str] = Field(default_factory=list, description="Diagnostic warnings encountered during preprocessing")
    blur_score: Optional[float] = Field(default=None, description="Laplacian variance blur estimator score")
    brightness_score: Optional[float] = Field(default=None, description="Mean grayscale intensity (0-255)")
    contrast_score: Optional[float] = Field(default=None, description="Standard deviation of grayscale intensity")
    is_blank: Optional[bool] = Field(default=None, description="Whether page was detected as blank or nearly blank")


class VariantsRecord(BaseModel):
    """Paths to optional image variants generated for downstream OCR models."""

    grayscale: Optional[str] = Field(default=None, description="Relative path to grayscale variant image")
    thresholded: Optional[str] = Field(default=None, description="Relative path to thresholded binary variant image")


class PreprocessingResult(BaseModel):
    """Standardized result model for a preprocessed page."""

    submission_id: str = Field(..., description="Unique assignment submission identifier")
    page_number: int = Field(..., ge=1, description="1-based page number")
    status: str = Field(default="completed", description="Preprocessing execution status (completed, failed, review)")
    original_image_path: str = Field(..., description="Path to original input image from Module 1")
    enhanced_image_path: str = Field(..., description="Path to default enhanced image for Module 3")
    variants: VariantsRecord = Field(default_factory=VariantsRecord, description="Available image variants")
    image_quality: ImageQualityMetrics = Field(..., description="Quality analysis and correction metrics")

