"""Pydantic schemas for Mathematical Recognition & Quality Analysis Module 4."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class BoundingBox(BaseModel):
    """Bounding box coordinates with origin (0, 0) at the top-left corner."""

    x1: int = Field(..., ge=0, description="Left coordinate in pixels")
    y1: int = Field(..., ge=0, description="Top coordinate in pixels")
    x2: int = Field(..., ge=0, description="Right coordinate in pixels")
    y2: int = Field(..., ge=0, description="Bottom coordinate in pixels")

    @field_validator("x2")
    @classmethod
    def validate_x2(cls, v: int, info) -> int:
        data = info.data
        if "x1" in data and v < data["x1"]:
            raise ValueError(f"x2 ({v}) must be greater than or equal to x1 ({data['x1']})")
        return v

    @field_validator("y2")
    @classmethod
    def validate_y2(cls, v: int, info) -> int:
        data = info.data
        if "y1" in data and v < data["y1"]:
            raise ValueError(f"y2 ({v}) must be greater than or equal to y1 ({data['y1']})")
        return v

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return self.width * self.height


class SymbolDetection(BaseModel):
    """Represents a recognized mathematical symbol and its ambiguity analysis."""

    symbol: str = Field(..., description="Recognized symbol (e.g. '\\pi', '+', 'x', '\\int')")
    category: str = Field(
        ...,
        description="Category: 'operator', 'greek', 'calculus', 'structure', 'variable', 'number', 'delimiter'",
    )
    bounding_box: Optional[BoundingBox] = Field(default=None, description="Bounding box if localized")
    is_ambiguous: bool = Field(default=False, description="Whether symbol is visually confusable (e.g. 0 vs O)")
    suggested_alternatives: List[str] = Field(
        default_factory=list, description="Alternative interpretations if ambiguous"
    )


class StructureDetection(BaseModel):
    """Represents a structural mathematical component (fraction, power, root, matrix)."""

    structure_type: str = Field(
        ...,
        description="Type: 'fraction', 'superscript', 'subscript', 'radical', 'integral', 'summation', 'matrix', 'limit'",
    )
    latex_representation: str = Field(..., description="LaTeX representation of this component")
    components: Dict[str, Any] = Field(
        default_factory=dict, description="Component parts (e.g. numerator, denominator, exponent)"
    )
    bounding_box: Optional[BoundingBox] = Field(default=None, description="Bounding box if localized")


class MathQualityAssessment(BaseModel):
    """Structured quality assessment of a mathematical expression image crop."""

    quality_score: float = Field(..., ge=0.0, le=1.0, description="Overall image quality score (0.0 to 1.0)")
    is_readable: bool = Field(..., description="Whether symbols are clear enough to read accurately")
    is_complete: bool = Field(..., description="Whether expression appears intact rather than cropped or cut off")
    requires_manual_review: bool = Field(..., description="Whether teacher verification is recommended")
    is_faint: bool = Field(default=False, description="Detected low-contrast or faint pencil writing")
    is_blurred: bool = Field(default=False, description="Detected out-of-focus or motion blur")
    is_low_resolution: bool = Field(default=False, description="Extremely small pixel dimensions")
    is_cropped: bool = Field(default=False, description="Ink touches crop borders indicating truncation")
    has_overlapping_strokes: bool = Field(default=False, description="Dense entangled strokes detected")
    warnings: List[str] = Field(default_factory=list, description="Quality warnings")
    uncertain_regions: List[BoundingBox] = Field(default_factory=list, description="Unclear sub-regions")


class MathRegionResult(BaseModel):
    """Structured extraction and quality result for a single mathematical expression region."""

    region_id: str = Field(..., description="Unique mathematical region identifier")
    page_id: str = Field(..., description="Associated page identifier or page number string")
    bounding_box: BoundingBox = Field(..., description="Coordinates of the mathematical region on the page")
    recognized_text: str = Field(default="", description="Original raw recognized mathematical text")
    latex: str = Field(default="", description="Structured LaTeX mathematical formula")
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Model-provided probability or None if uncalibrated"
    )
    quality_score: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Visual image quality score from quality analyzer"
    )
    is_readable: bool = Field(default=True, description="Whether mathematical region is legible")
    is_complete: bool = Field(default=True, description="Whether formula is complete")
    requires_manual_review: bool = Field(default=False, description="Flag for teacher manual inspection")
    symbols: List[SymbolDetection] = Field(default_factory=list, description="Detected mathematical symbols")
    structures: List[StructureDetection] = Field(default_factory=list, description="Detected mathematical structures")
    warnings: List[str] = Field(default_factory=list, description="Diagnostics and ambiguity warnings")
    recognition_status: str = Field(
        default="completed",
        description="Status: 'completed', 'low_confidence', 'unreadable', 'failed', 'unavailable'",
    )
    engine_used: str = Field(default="none", description="Engine used ('pix2tex', 'unimernet', 'fallback', 'none')")
    model_version: Optional[str] = Field(default=None, description="Model version or checkpoint name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional diagnostics")


class PageMathRecognitionResult(BaseModel):
    """Aggregated mathematical recognition result across an entire assignment page."""

    submission_id: str = Field(..., description="Submission identifier")
    page_number: int = Field(..., ge=1, description="1-based page number")
    status: str = Field(default="completed", description="Overall page status ('completed', 'degraded', 'failed')")
    math_regions: List[MathRegionResult] = Field(default_factory=list, description="Extracted mathematical regions")
    combined_latex: str = Field(default="", description="Aggregated LaTeX expressions in reading order")
    warnings: List[str] = Field(default_factory=list, description="Page-level diagnostics")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic metrics")

