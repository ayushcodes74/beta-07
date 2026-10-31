"""Handwriting recognition service."""

import logging
from typing import Any, Dict, Optional, Tuple
import numpy as np

from app.recognition.config import RecognitionConfig, DEFAULT_RECOGNITION_CONFIG
from app.recognition.exceptions import HandwritingRecognitionError
from app.recognition.model_manager import ModelManager

logger = logging.getLogger(__name__)


class HandwritingRecognizer:
    """Extracts handwritten student answers from cropped regions using TrOCR or degraded fallback."""

    def __init__(self, config: Optional[RecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_RECOGNITION_CONFIG
        self.model_manager = ModelManager.get_instance(self.config)

    def recognize(
        self, crop: np.ndarray, page_number: int, block_id: str
    ) -> Tuple[str, Optional[float], Optional[float], Dict[str, Any]]:
        """Recognize handwritten student text from a region crop.

        Args:
            crop: BGR or grayscale numpy image crop.
            page_number: Page number for diagnostics.
            block_id: Block identifier for error context.

        Returns:
            Tuple of (transcribed_text, confidence_score, quality_score, metadata).

        Raises:
            HandwritingRecognitionError: If recognition inference encounters an unrecoverable failure.
        """
        if crop is None or crop.size == 0:
            return "", None, 0.0, {
                "engine_used": "none",
                "is_fallback": True,
                "recognition_mode": "empty_crop",
                "recognition_available": False,
            }

        try:
            return self.model_manager.recognize_handwriting_crop(crop)
        except Exception as e:
            if isinstance(e, HandwritingRecognitionError):
                raise
            logger.error("Handwriting recognition failed for block %s on page %d: %s", block_id, page_number, e)
            raise HandwritingRecognitionError(
                f"Handwriting recognition failed on {block_id}: {e}",
                page_number=page_number,
                region_id=block_id,
            ) from e
