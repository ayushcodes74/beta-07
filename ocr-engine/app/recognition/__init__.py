"""Module 3: Text & Handwriting Recognition for TrustGrade OCR Engine."""

from app.recognition.config import (
    DEFAULT_RECOGNITION_CONFIG,
    RecognitionConfig,
)
from app.recognition.exceptions import (
    HandwritingRecognitionError,
    ModelLoadingError,
    PrintedRecognitionError,
    RecognitionError,
    RecognitionPipelineError,
    TextDetectionError,
)
from app.recognition.model_manager import ModelManager
from app.recognition.reading_order import ReadingOrderReconstructor
from app.recognition.recognition_pipeline import recognize_page, recognize_pages
from app.recognition.schemas import (
    BoundingBox,
    PageRecognitionResult,
    TextBlock,
)
from app.recognition.text_classifier import TextClassifier
from app.recognition.text_detector import TextDetector
from app.recognition.text_normalizer import TextNormalizer

__all__ = [
    "recognize_page",
    "recognize_pages",
    "RecognitionConfig",
    "DEFAULT_RECOGNITION_CONFIG",
    "PageRecognitionResult",
    "TextBlock",
    "BoundingBox",
    "ModelManager",
    "TextDetector",
    "TextClassifier",
    "ReadingOrderReconstructor",
    "TextNormalizer",
    "RecognitionError",
    "TextDetectionError",
    "PrintedRecognitionError",
    "HandwritingRecognitionError",
    "ModelLoadingError",
    "RecognitionPipelineError",
]

