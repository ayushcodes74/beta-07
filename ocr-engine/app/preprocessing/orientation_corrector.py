"""Page orientation detection and correction service."""

import logging
from typing import Optional, Tuple
import cv2
import numpy as np

from app.preprocessing.config import PreprocessingConfig, DEFAULT_PREPROCESSING_CONFIG

logger = logging.getLogger(__name__)


class OrientationCorrector:
    """Detects and corrects 90, 180, or 270 degree page rotations."""

    def __init__(self, config: Optional[PreprocessingConfig] = None) -> None:
        self.config = config or DEFAULT_PREPROCESSING_CONFIG

    def correct_orientation(
        self,
        image: np.ndarray,
        known_rotation: int = 0,
    ) -> Tuple[np.ndarray, bool, int, Optional[str]]:
        """Correct page orientation if known or reliably detectable.

        Args:
            image: BGR numpy image array.
            known_rotation: Prior rotation angle from PDF metadata (0, 90, 180, 270).

        Returns:
            Tuple of (corrected_image, was_corrected, applied_rotation, warning_message).
        """
        if not self.config.enable_orientation_correction:
            return image, False, 0, None

        # 1. If explicit rotation was provided by Module 1, apply it reliably
        if known_rotation in (90, 180, 270):
            corrected = self.rotate_image(image, known_rotation)
            return corrected, True, known_rotation, None

        # 2. Automated orientation heuristic (projection profile analysis)
        detected_angle, is_confident, warning = self.detect_orientation_heuristic(image)

        if is_confident and detected_angle != 0:
            corrected = self.rotate_image(image, detected_angle)
            return corrected, True, detected_angle, None

        return image, False, 0, warning

    @staticmethod
    def rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
        """Rotate image by 90, 180, or 270 degrees clockwise."""
        normalized_angle = angle % 360
        if normalized_angle == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif normalized_angle == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        elif normalized_angle == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return image

    @staticmethod
    def detect_orientation_heuristic(image: np.ndarray) -> Tuple[int, bool, Optional[str]]:
        """Analyze text line direction using horizontal vs vertical projection variance.

        Note: Per system design, character-level upside-down (0 vs 180) or 90 vs 270
        disambiguation without text-recognition requires OCR models (Module 3).
        When uncertain, we avoid arbitrary rotations and flag for review.

        Returns:
            Tuple of (suggested_angle, is_reliable, warning).
        """
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            # Downsample for fast analysis
            h, w = gray.shape
            scale = 800.0 / max(h, w)
            if scale < 1.0:
                small = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            else:
                small = gray

            # Binarize with Otsu
            _, binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Horizontal and vertical projections
            h_proj = np.sum(binary, axis=1)
            v_proj = np.sum(binary, axis=0)

            var_h = float(np.var(h_proj))
            var_v = float(np.var(v_proj))

            # Horizontal text lines produce strong variance along rows (peaks at lines, troughs between)
            # If vertical projection variance is dramatically larger than horizontal, lines run vertically
            if var_h > 0 and (var_v / var_h) > 2.5:
                # Text appears vertical (page rotated 90 or 270 deg)
                return 0, False, "Page appears sideways (vertical text lines detected). Flagged for review; OCR verification required."

            return 0, True, None
        except Exception as e:
            logger.warning("Orientation heuristic failed: %s", e)
            return 0, False, f"Orientation analysis encountered: {e}"

