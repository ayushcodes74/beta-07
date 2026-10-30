"""Grayscale conversion and binarization variants service."""

import logging
from typing import Optional
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ThresholdingService:
    """Provides methods for grayscale conversion and thresholding variants."""

    @staticmethod
    def to_grayscale(image: np.ndarray) -> np.ndarray:
        """Convert BGR image to single-channel 8-bit grayscale."""
        if len(image.shape) == 2:
            return image
        if len(image.shape) == 3 and image.shape[2] == 1:
            return image[:, :, 0]
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    @classmethod
    def apply_adaptive_threshold(
        cls,
        image: np.ndarray,
        block_size: int = 21,
        c: int = 10,
    ) -> np.ndarray:
        """Apply Gaussian adaptive thresholding.

        Computes a localized threshold per block to adapt to varying illumination.

        Args:
            image: BGR or grayscale numpy image.
            block_size: Neighborhood size in pixels (must be odd, e.g. 21).
            c: Constant subtracted from the mean.

        Returns:
            Binary image (0 or 255).
        """
        gray = cls.to_grayscale(image)
        # Ensure block_size is odd and >= 3
        b_size = block_size if block_size % 2 == 1 else block_size + 1
        b_size = max(3, b_size)
        return cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            b_size,
            c,
        )

    @classmethod
    def apply_otsu_threshold(cls, image: np.ndarray) -> np.ndarray:
        """Apply global Otsu thresholding."""
        gray = cls.to_grayscale(image)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    @classmethod
    def generate_threshold_variant(
        cls,
        image: np.ndarray,
        method: str = "adaptive",
    ) -> np.ndarray:
        """Generate a binary thresholded variant based on configured algorithm."""
        if method.lower() == "otsu":
            return cls.apply_otsu_threshold(image)
        return cls.apply_adaptive_threshold(image)

