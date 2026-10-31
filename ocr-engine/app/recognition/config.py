"""Configuration settings for Text & Handwriting Recognition Module 3."""

import os

from pydantic import BaseModel, Field

from app.env import load_env_file

load_env_file()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


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
        default="ocrspace",
        description=(
            "OCR execution engine. 'ocrspace' (default): OCR.space cloud OCR (OCREngine 3, strong handwriting) "
            "per page, falling back to local PaddleOCR when no API key is set or the API fails. 'paddleocr': "
            "local PaddleOCR detects and recognizes every text line on the full page. 'auto': legacy hybrid "
            "(OpenCV regions, TrOCR for handwriting, PaddleOCR for printed crops). 'trocr': legacy OpenCV "
            "regions with TrOCR only. 'degraded': no models."
        ),
    )

    # Vision-LLM page reader (Gemini): math -> LaTeX, tables, diagrams/graphs, any language/script.
    # Runs before the OCR engines above whenever a key is configured; any failure falls back to them.
    vision_enabled: bool = Field(
        default_factory=lambda: _env_bool("OCR_VISION_ENABLED", True),
        description="Use the vision LLM as the primary page reader when an API key is available (env OCR_VISION_ENABLED)",
    )
    vision_api_key: str = Field(
        default_factory=lambda: os.getenv("OCR_VISION_API_KEY") or os.getenv("GEMINI_API_KEY", ""),
        description="Gemini API key (env OCR_VISION_API_KEY, falling back to GEMINI_API_KEY). Empty disables it.",
        repr=False,
    )
    vision_model: str = Field(
        default_factory=lambda: os.getenv("OCR_VISION_MODEL", "gemini-2.5-flash"),
        description="Gemini model used to read pages (env OCR_VISION_MODEL)",
    )
    vision_fallback_models: list = Field(
        default_factory=lambda: [
            m.strip()
            for m in (os.getenv("OCR_VISION_FALLBACK_MODELS") or os.getenv("GEMINI_FALLBACK_MODELS", "")).split(",")
            if m.strip()
        ],
        description=(
            "Models tried in order when the primary is rate-limited/over quota/unavailable "
            "(env OCR_VISION_FALLBACK_MODELS, comma-separated; falls back to GEMINI_FALLBACK_MODELS)"
        ),
    )
    vision_endpoint: str = Field(
        default_factory=lambda: os.getenv("OCR_VISION_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta"),
        description="Gemini API base URL",
    )
    vision_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("OCR_VISION_TIMEOUT_SECONDS", "120")),
        description="Per-page request timeout for the vision model",
        gt=0,
    )
    vision_max_image_side: int = Field(
        default=2048,
        description="Page images are downscaled so their longest side is at most this many pixels",
        ge=512,
    )

    # OCR.space cloud OCR (https://ocr.space/ocrapi)
    ocr_space_api_key: str = Field(
        default_factory=lambda: os.getenv("OCR_SPACE_API_KEY", ""),
        description="OCR.space API key (env OCR_SPACE_API_KEY, e.g. in ocr-engine/.env). Empty disables OCR.space.",
        repr=False,
    )
    ocr_space_endpoint: str = Field(
        default_factory=lambda: os.getenv("OCR_SPACE_ENDPOINT", "https://api.ocr.space/parse/image"),
        description="OCR.space parse endpoint (PRO plans use a different host)",
    )
    ocr_space_engine: int = Field(
        default_factory=lambda: int(os.getenv("OCR_SPACE_ENGINE", "3")),
        description="OCR.space OCREngine: 3 = handwriting/tables (1000/month free), 2 = fast general purpose",
        ge=1,
        le=3,
    )
    ocr_space_language: str = Field(
        default_factory=lambda: os.getenv("OCR_SPACE_LANGUAGE", "auto"),
        description=(
            "OCR.space language. 'auto' (default) auto-detects mixed languages/scripts on Engines 2 and 3 "
            "(Engine 3: 200+ languages). 3-letter codes (e.g. 'hin', 'ara', 'chs') are only a fallback hint."
        ),
    )
    ocr_space_timeout_seconds: float = Field(
        default=120.0,
        description="Per-page request timeout (Engine 3 with overlay can take tens of seconds)",
        gt=0,
    )
    ocr_space_max_upload_bytes: int = Field(
        default_factory=lambda: int(os.getenv("OCR_SPACE_MAX_UPLOAD_BYTES", "1000000")),
        description="Page images are JPEG-compressed under this size (free plan limit is 1 MB)",
        gt=10_000,
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
        description="Model identifier reported for PaddleOCR 2.x installs (3.x reports the det/rec model names)",
    )

    # PaddleOCR (3.x) settings
    paddle_det_model_name: str = Field(
        default="PP-OCRv6_small_det",
        description="PaddleOCR text detection model (PP-OCRv6_tiny/small/medium_det trade speed for recall)",
    )
    paddle_rec_model_name: str = Field(
        default="PP-OCRv6_small_rec",
        description="PaddleOCR text recognition model (PP-OCRv6_tiny/small/medium_rec)",
    )
    paddle_enable_mkldnn: bool = Field(
        default=False,
        description=(
            "Enable oneDNN/MKLDNN CPU acceleration. Off by default: PaddlePaddle 3.x crashes in oneDNN on "
            "Windows CPU ('ConvertPirAttribute2RuntimeAttribute not support')."
        ),
    )
    paddle_use_textline_orientation: bool = Field(
        default=False,
        description="Run PaddleOCR's per-line 0/180 orientation classifier (pages are already deskewed by Module 2)",
    )
    paddle_min_score: float = Field(
        default=0.30,
        description="Discard PaddleOCR lines whose recognition score is below this (pure noise)",
        ge=0.0,
        le=1.0,
    )
    line_merge_gap_factor: float = Field(
        default=4.0,
        description=(
            "PaddleOCR fragments on the same visual line are merged into one block unless the horizontal gap "
            "exceeds this multiple of the line height (keeps side-by-side columns separate)"
        ),
        gt=0.0,
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

