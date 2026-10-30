"""Pydantic schemas for Text & Handwriting Recognition Module 3."""

from typing import List, Optional
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


class TextBlock(BaseModel):
    """Represents a recognized text segment or paragraph block."""

    block_id: str = Field(..., description="Unique block identifier (e.g. page-1-block-1)")
    sequence: int = Field(..., ge=1, description="1-based natural reading order sequence")
    type: str = Field(..., description="Classification: 'printed', 'handwritten', or 'unknown'")
    text: str = Field(..., description="Safely normalized transcribed text")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Recognition confidence score (0.0 to 1.0)")
    bounding_box: BoundingBox = Field(..., description="Pixel coordinates of the text region")
    warnings: List[str] = Field(default_factory=list, description="Quality, uncertainty, or mathematical warnings")


class PageRecognitionResult(BaseModel):
    """Structured text extraction result for a single assignment page."""

    submission_id: str = Field(..., description="Unique assignment submission identifier")
    page_number: int = Field(..., ge=1, description="1-based page number")
    status: str = Field(default="completed", description="Recognition status (completed, failed, review)")
    text_blocks: List[TextBlock] = Field(default_factory=list, description="Ordered text blocks")
    full_text: str = Field(default="", description="Aggregated full page text in reading order")
    warnings: List[str] = Field(default_factory=list, description="Page-level warnings or review notifications")
    metadata: Optional[dict] = Field(default=None, description="Optional diagnostic metrics (model info, timing)")

