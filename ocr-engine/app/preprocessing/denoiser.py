"""Edge-preserving denoising designed specifically to protect handwritten strokes and mathematical notation."""

import logging
from typing import Optional
import cv2
import numpy as np

from app.preprocessing.config import PreprocessingConfig, DEFAULT_PREPROCESSING_CONFIG

logger = logging.getLogger(__name__)


class Denoiser:
    """Removes scanner noise and artifacts while strictly preserving thin strokes, decimal points, and math symbols."""

    def __init__(self, config: Optional[PreprocessingConfig] = None) -> None:
        self.config = config or DEFAULT_PREPROCESSING_CONFIG

    def denoise(self, image: np.ndarray) -> np.ndarray:
        """Apply gentle edge-preserving bilateral filtering to an image.

        Bilateral filtering replaces pixel values by a weighted average of neighbors,
        where weights depend on spatial proximity AND radiometric difference.
        This suppresses flat scanner grain and background noise while preserving
        high-contrast boundaries (such as ink strokes, punctuation, dots, and symbols).

        Args:
            image: BGR or grayscale numpy image array.

        Returns:
            Denoised image.
        """
        if not self.config.enable_denoising:
            return image

        try:
            d = self.config.bilateral_d
            sc = self.config.bilateral_sigma_color
            ss = self.config.bilateral_sigma_space

            if len(image.shape) == 3:
                return cv2.bilateralFilter(image, d=d, sigmaColor=sc, sigmaSpace=ss)
            else:
                return cv2.bilateralFilter(image, d=d, sigmaColor=sc, sigmaSpace=ss)
        except Exception as e:
            logger.warning("Denoising failed: %s. Returning input image unchanged.", e)
            return image

