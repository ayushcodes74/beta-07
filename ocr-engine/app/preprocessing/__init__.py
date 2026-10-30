"""Module 2: Image Preprocessing & Enhancement for TrustGrade OCR Engine."""

from app.preprocessing.config import (
    DEFAULT_PREPROCESSING_CONFIG,
    PreprocessingConfig,
)
from app.preprocessing.exceptions import (
    ImageLoadError,
    ImageProcessingError,
    ImageSaveError,
    InvalidImageError,
    PreprocessingError,
    UnsupportedImageFormatError,
)
from app.preprocessing.pipeline import preprocess_page, preprocess_pages
from app.preprocessing.schemas import (
    ImageQualityMetrics,
    PreprocessingResult,
    VariantsRecord,
)

__all__ = [
    "preprocess_page",
    "preprocess_pages",
    "PreprocessingConfig",
    "DEFAULT_PREPROCESSING_CONFIG",
    "PreprocessingResult",
    "ImageQualityMetrics",
    "VariantsRecord",
    "PreprocessingError",
    "InvalidImageError",
    "UnsupportedImageFormatError",
    "ImageLoadError",
    "ImageProcessingError",
    "ImageSaveError",
]

