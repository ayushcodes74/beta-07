"""Contrast and illumination enhancement service."""

import logging
from typing import Optional
import cv2
import numpy as np

from app.preprocessing.config import PreprocessingConfig, DEFAULT_PREPROCESSING_CONFIG

logger = logging.getLogger(__name__)


class ContrastEnhancer:
    """Corrects uneven page illumination, reduces shadows, and enhances contrast adaptively."""

    def __init__(self, config: Optional[PreprocessingConfig] = None) -> None:
        self.config = config or DEFAULT_PREPROCESSING_CONFIG

    def enhance(self, image: np.ndarray) -> np.ndarray:
        """Enhance contrast and normalize background illumination without harsh binarization.

        Preserves color channels and continuous tones to avoid losing faint handwriting.

        Args:
            image: BGR or grayscale numpy image array.

        Returns:
            Contrast-enhanced image array.
        """
        if not self.config.enable_contrast_enhancement:
            return image

        try:
            if len(image.shape) == 3:
                # Color image: transform to LAB space, enhance L (lightness) channel
                lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
                l_channel, a_channel, b_channel = cv2.split(lab)

                # 1. Background illumination normalization on L-channel
                normalized_l = self._normalize_background(l_channel)

                # 2. CLAHE contrast enhancement
                clahe = cv2.createCLAHE(
                    clipLimit=self.config.clahe_clip_limit,
                    tileGridSize=(self.config.clahe_tile_grid_size, self.config.clahe_tile_grid_size),
                )
                enhanced_l = clahe.apply(normalized_l)

                merged = cv2.merge((enhanced_l, a_channel, b_channel))
                return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
            else:
                # Grayscale image
                normalized = self._normalize_background(image)
                clahe = cv2.createCLAHE(
                    clipLimit=self.config.clahe_clip_limit,
                    tileGridSize=(self.config.clahe_tile_grid_size, self.config.clahe_tile_grid_size),
                )
                return clahe.apply(normalized)

        except Exception as e:
            logger.warning("Contrast enhancement failed: %s. Returning input unchanged.", e)
            return image

    @staticmethod
    def _normalize_background(gray: np.ndarray) -> np.ndarray:
        """Estimate background illumination surface and divide to reduce shadows."""
        try:
            # Estimate background using morphological closing with large rectangular kernel
            kernel_size = 31
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
            background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)

            # Avoid division by zero
            bg_float = background.astype(np.float32) + 1.0
            gray_float = gray.astype(np.float32)

            # Normalized division: paper becomes uniform white (~255)
            normalized = np.clip((gray_float / bg_float) * 255.0, 0, 255).astype(np.uint8)
            return normalized
        except Exception as e:
            logger.warning("Background normalization failed: %s. Proceeding with raw gray.", e)
            return gray

