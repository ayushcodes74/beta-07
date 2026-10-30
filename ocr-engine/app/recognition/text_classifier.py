"""Printed versus handwritten text classification service."""

import logging
from typing import Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class TextClassifier:
    """Classifies detected text regions into 'printed', 'handwritten', or 'unknown'."""

    @classmethod
    def classify_region(cls, crop: np.ndarray) -> Tuple[str, float]:
        """Classify a cropped text region.

        Uses structural analysis:
        - Printed typography features regular stroke widths and dominant 0/90 deg edges.
        - Handwriting features irregular baseline trajectories, variable slant, and cursive loops.
        - Unclear or ambiguous regions are classified as 'unknown' rather than guessed.

        Args:
            crop: BGR or grayscale numpy image crop of the text region.

        Returns:
            Tuple of (classification_label, confidence).
            Label is one of: 'printed', 'handwritten', 'unknown'.
        """
        if crop is None or crop.size == 0:
            return "unknown", 0.0

        try:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
            h, w = gray.shape

            # Very small regions cannot be reliably classified
            if w < 10 or h < 8:
                return "unknown", 0.5

            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            ink_count = np.count_nonzero(binary)
            if ink_count < 20:
                return "unknown", 0.5

            # 1. Edge orientation entropy (Sobel gradient angles)
            gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            mag = np.sqrt(gx**2 + gy**2)
            mask = mag > 20.0

            if np.count_nonzero(mask) > 15:
                angles = np.abs(np.arctan2(gy[mask], gx[mask]))  # 0 to pi
                # Check alignment with cardinal horizontal (0, pi) and vertical (pi/2)
                cardinal_thresh = 0.25
                is_horiz = (angles < cardinal_thresh) | (angles > (np.pi - cardinal_thresh))
                is_vert = np.abs(angles - (np.pi / 2)) < cardinal_thresh
                cardinal_fraction = float(np.count_nonzero(is_horiz | is_vert)) / float(len(angles))
            else:
                cardinal_fraction = 0.5

            # 2. Contour regularity
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return "unknown", 0.5

            aspect_ratios = []
            for cnt in contours:
                _, _, cw, ch = cv2.boundingRect(cnt)
                if ch > 0:
                    aspect_ratios.append(cw / float(ch))

            mean_aspect = float(np.mean(aspect_ratios)) if aspect_ratios else 1.0

            # Decision Logic:
            # High cardinal fraction (>= 0.58) indicates rigid machine typography (printed)
            # Low cardinal fraction (<= 0.48) with cursive/slanted strokes indicates handwriting
            if cardinal_fraction >= 0.58:
                conf = min(0.98, float(0.75 + (cardinal_fraction - 0.58) * 1.5))
                return "printed", round(conf, 2)
            elif cardinal_fraction <= 0.48:
                conf = min(0.95, float(0.70 + (0.48 - cardinal_fraction) * 1.5))
                return "handwritten", round(conf, 2)
            else:
                # Ambiguous boundary zone: do not guess, return unknown
                return "unknown", 0.55

        except Exception as e:
            logger.warning("Text classification encountered error: %s. Returning 'unknown'.", e)
            return "unknown", 0.5
