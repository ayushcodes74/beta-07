"""Mathematical OCR inference engine coordinating model execution."""

import logging
from typing import Any, Dict, Optional, Tuple
import numpy as np

from app.math_recognition.config import MathRecognitionConfig, DEFAULT_MATH_CONFIG
from app.math_recognition.exceptions import MathInferenceError
from app.math_recognition.image_processor import MathImageProcessor
from app.math_recognition.model_manager import MathModelManager

logger = logging.getLogger(__name__)


class MathOCREngine:
    """Executes mathematical OCR inference on region crops using the loaded model or fallback."""

    def __init__(self, config: Optional[MathRecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_MATH_CONFIG
        self.model_manager = MathModelManager.get_instance(self.config)

    def recognize_crop(
        self,
        crop: np.ndarray,
        region_id: str,
        page_id: str,
    ) -> Tuple[str, str, Optional[float], Dict[str, Any]]:
        """Run mathematical recognition on an image crop.

        Args:
            crop: BGR or grayscale numpy image crop.
            region_id: Unique mathematical region identifier.
            page_id: Page identifier.

        Returns:
            Tuple of (recognized_text, latex_expression, confidence, metadata).

        Raises:
            MathInferenceError: If model inference crashes unexpectedly.
        """
        # Blank or empty crop check
        if MathImageProcessor.is_blank_crop(crop):
            return "", "", None, {
                "engine_used": "none",
                "is_fallback": True,
                "recognition_mode": "blank_region",
                "recognition_available": False,
                "recognition_status": "unreadable",
            }

        try:
            # 1. Prepare crop: add border padding to avoid boundary clipping
            padded = MathImageProcessor.pad_crop(crop, padding=8)
            pil_img = MathImageProcessor.to_rgb_pil(padded)

            # 2. Delegate to ModelManager
            latex_expr, conf, meta = self.model_manager.recognize_math_crop(pil_img)

            # Raw recognized text is identical to LaTeX output for dedicated LaTeX-OCR models
            recognized_text = latex_expr

            # Determine recognition status
            if meta.get("is_fallback"):
                meta["recognition_status"] = "unavailable"
            elif conf is not None and conf < self.config.medium_confidence_threshold:
                meta["recognition_status"] = "low_confidence"
            elif not latex_expr.strip():
                meta["recognition_status"] = "unreadable"
            else:
                meta["recognition_status"] = "completed"

            return recognized_text, latex_expr, conf, meta

        except Exception as e:
            if isinstance(e, MathInferenceError):
                raise
            logger.error("Mathematical OCR failed on region %s (page %s): %s", region_id, page_id, e)
            raise MathInferenceError(
                f"Math OCR inference failed on {region_id}: {e}",
                region_id=region_id,
            ) from e

