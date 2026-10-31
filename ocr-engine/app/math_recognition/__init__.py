"""Module 4: Mathematical Recognition & Quality Analysis for TrustGrade OCR Engine."""

from app.math_recognition.config import (
    DEFAULT_MATH_CONFIG,
    MathRecognitionConfig,
)
from app.math_recognition.exceptions import (
    LaTeXConversionError,
    MathImageError,
    MathInferenceError,
    MathModelLoadingError,
    MathPipelineError,
    MathRecognitionError,
    MathRegionValidationError,
)
from app.math_recognition.image_processor import MathImageProcessor
from app.math_recognition.latex_converter import LaTeXConverter
from app.math_recognition.math_ocr import MathOCREngine
from app.math_recognition.model_manager import MathModelManager
from app.math_recognition.quality_analyzer import MathQualityAnalyzer
from app.math_recognition.recognition_pipeline import (
    MathRecognitionPipeline,
    process_math_batch,
    process_math_page,
    process_math_region,
)
from app.math_recognition.region_validator import MathRegionValidator
from app.math_recognition.schemas import (
    BoundingBox,
    MathQualityAssessment,
    MathRegionResult,
    PageMathRecognitionResult,
    StructureDetection,
    SymbolDetection,
)
from app.math_recognition.structure_analyzer import MathStructureAnalyzer
from app.math_recognition.symbol_analyzer import MathSymbolAnalyzer

__all__ = [
    # Main Pipeline & Convenience Functions
    "MathRecognitionPipeline",
    "process_math_region",
    "process_math_page",
    "process_math_batch",
    # Configuration
    "MathRecognitionConfig",
    "DEFAULT_MATH_CONFIG",
    # Schemas
    "BoundingBox",
    "SymbolDetection",
    "StructureDetection",
    "MathQualityAssessment",
    "MathRegionResult",
    "PageMathRecognitionResult",
    # Services
    "MathModelManager",
    "MathOCREngine",
    "MathQualityAnalyzer",
    "MathSymbolAnalyzer",
    "MathStructureAnalyzer",
    "LaTeXConverter",
    "MathRegionValidator",
    "MathImageProcessor",
    # Exceptions
    "MathRecognitionError",
    "MathImageError",
    "MathRegionValidationError",
    "MathModelLoadingError",
    "MathInferenceError",
    "LaTeXConversionError",
    "MathPipelineError",
]

