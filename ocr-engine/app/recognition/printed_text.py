"""Printed text recognition service."""

import logging
from typing import Optional, Tuple
import numpy as np

from app.recognition.config import RecognitionConfig, DEFAULT_RECOGNITION_CONFIG
from app.recognition.exceptions import PrintedRecognitionError
from app.recognition.model_manager import ModelManager

logger = logging.getLogger(__name__)


class PrintedTextRecognizer:
    """Extracts printed English typography from cropped text regions."""

    def __init__(self, config: Optional[RecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_RECOGNITION_CONFIG
        self.model_manager = ModelManager.get_instance(self.config)

    def recognize(self, crop: np.ndarray, page_number: int, block_id: str) -> Tuple[str, float]:
        """Recognize printed text from a region crop.

        Args:
            crop: BGR or grayscale numpy image crop.
            page_number: Page number for diagnostics.
            block_id: Block identifier for error context.

        Returns:
            Tuple of (transcribed_text, confidence_score).

        Raises:
            PrintedRecognitionError: If recognition inference fails.
        """
        if crop is None or crop.size == 0:
            return "", 0.0

        try:
            text, conf = self.model_manager.recognize_printed_crop(crop)
            return text, conf
        except Exception as e:
            logger.error("Printed recognition failed for block %s on page %d: %s", block_id, page_number, e)
            raise PrintedRecognitionError(
                f"Printed recognition failed on {block_id}: {e}",
                page_number=page_number,
                region_id=block_id,
            ) from e

