"""Configuration settings for Text & Handwriting Recognition Module 3."""

from pydantic import BaseModel, Field


class RecognitionConfig(BaseModel):
    """Configuration controlling text detection, classification, and OCR inference."""

    # Confidence Thresholds
    high_confidence_threshold: float = Field(
        default=0.85,
        description="Confidence at or above which recognition is considered highly reliable",
        ge=0.0,
        le=1.0,
    )
    medium_confidence_threshold: float = Field(
        default=0.60,
        description="Threshold below which text is flagged as low confidence",
        ge=0.0,
        le=1.0,
    )

    # Text Region Detection Parameters
    min_region_width: int = Field(
        default=15,
        description="Minimum width in pixels for a valid text region",
        ge=5,
    )
    min_region_height: int = Field(
        default=10,
        description="Minimum height in pixels for a valid text region",
        ge=5,
    )
    dilation_kernel_width: int = Field(
        default=18,
        description="Horizontal dilation kernel width to connect adjacent words into lines",
    )
    dilation_kernel_height: int = Field(
        default=4,
        description="Vertical dilation kernel height to avoid merging across text lines",
    )

    # Reading Order Reconstruction
    multi_column_detection: bool = Field(
        default=True,
        description="Whether to detect and segment multi-column layouts into reading order",
    )
    column_gap_threshold: int = Field(
        default=60,
        description="Horizontal gap in pixels required to separate columns",
    )
    vertical_band_tolerance: int = Field(
        default=16,
        description="Vertical overlap tolerance in pixels when sorting text blocks horizontally",
    )

    # Safe Normalization
    collapse_whitespace: bool = Field(
        default=True,
        description="Normalize multiple consecutive spaces/tabs into a single space",
    )
    preserve_newlines: bool = Field(
        default=True,
        description="Preserve paragraph breaks between distinct text blocks",
    )

    # Model & Engine Management
    backend: str = Field(
        default="auto",
        description="OCR execution engine ('auto', 'trocr', 'paddleocr', 'degraded')",
    )
    device: str = Field(
        default="cpu",
        description="Hardware acceleration device ('cpu', 'cuda', 'auto')",
    )
    handwriting_model_name: str = Field(
        default="microsoft/trocr-small-handwritten",
        description="Model identifier for handwriting recognition",
    )
    printed_model_name: str = Field(
        default="paddleocr-en",
        description="Model identifier for printed text recognition",
    )
    max_target_tokens: int = Field(
        default=64,
        description="Maximum generated tokens for autoregressive sequence models",
        ge=1,
    )
    allow_degraded_fallback: bool = Field(
        default=True,
        description="Gracefully degrade to layout-only mode if genuine models cannot be loaded",
    )
    preserve_math_regions: bool = Field(
        default=True,
        description="Identify and preserve mathematical regions for Module 4",
    )


DEFAULT_RECOGNITION_CONFIG = RecognitionConfig()

