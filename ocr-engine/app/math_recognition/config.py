"""Configuration settings for Mathematical Recognition & Quality Analysis Module 4."""

from pydantic import BaseModel, Field


class MathRecognitionConfig(BaseModel):
    """Configuration controlling mathematical crop processing, model inference, and quality analysis."""

    # Model & Engine Management
    backend: str = Field(
        default="auto",
        description="Mathematical OCR backend ('auto', 'pix2tex', 'unimernet', 'degraded')",
    )
    device: str = Field(
        default="cpu",
        description="Hardware acceleration device ('cpu', 'cuda', 'auto')",
    )
    model_name: str = Field(
        default="lukas-blecher/LaTeX-OCR",
        description="Pretrained model identifier for mathematical OCR",
    )
    max_target_tokens: int = Field(
        default=128,
        description="Maximum generated tokens for LaTeX formula generation",
        ge=16,
    )
    allow_degraded_fallback: bool = Field(
        default=True,
        description="Gracefully degrade to layout and quality analysis if genuine deep-learning models are unavailable",
    )
    timeout_seconds: float = Field(
        default=10.0,
        description="Maximum execution timeout in seconds per mathematical region crop",
        ge=0.5,
    )

    # Confidence Thresholds
    high_confidence_threshold: float = Field(
        default=0.85,
        description="Confidence at or above which math recognition is considered highly reliable",
        ge=0.0,
        le=1.0,
    )
    medium_confidence_threshold: float = Field(
        default=0.60,
        description="Threshold below which mathematical expression is flagged as low confidence",
        ge=0.0,
        le=1.0,
    )

    # Region Validation Limits
    min_region_width: int = Field(
        default=15,
        description="Minimum pixel width for a valid mathematical expression region",
        ge=5,
    )
    min_region_height: int = Field(
        default=10,
        description="Minimum pixel height for a valid mathematical expression region",
        ge=5,
    )

    # Quality Analysis Thresholds
    blur_threshold: float = Field(
        default=100.0,
        description="Laplacian variance threshold below which region is flagged as blurred",
        ge=10.0,
    )
    faint_contrast_threshold: float = Field(
        default=20.0,
        description="Grayscale standard deviation threshold below which handwriting is flagged as faint",
        ge=5.0,
    )
    boundary_touch_margin: int = Field(
        default=2,
        description="Pixel margin from crop border to detect cropped or truncated equations",
        ge=1,
    )

    # Mathematical Processing & Validation
    enable_sympy_validation: bool = Field(
        default=True,
        description="Enable optional SymPy syntax parsing (without altering or grading student answers)",
    )
    preserve_raw_tokens: bool = Field(
        default=True,
        description="Preserve original raw transcript alongside structured LaTeX",
    )


DEFAULT_MATH_CONFIG = MathRecognitionConfig()

