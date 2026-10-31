"""Image processor for mathematical crops preparing arrays for model inference."""

import logging
from pathlib import Path
from typing import Optional, Union
import cv2
import numpy as np
from PIL import Image

from app.math_recognition.config import MathRecognitionConfig, DEFAULT_MATH_CONFIG
from app.math_recognition.exceptions import MathImageError

logger = logging.getLogger(__name__)


class MathImageProcessor:
    """Prepares and validates mathematical image crops for OCR inference without destroying original data."""

    def __init__(self, config: Optional[MathRecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_MATH_CONFIG

    @classmethod
    def load_crop(cls, image_input: Union[str, Path, np.ndarray]) -> np.ndarray:
        """Safely load an image crop from path or return a clean copy of numpy array."""
        if isinstance(image_input, (str, Path)):
            p = Path(image_input).resolve()
            if not p.exists():
                raise MathImageError(f"Mathematical image crop file not found: '{p}'")
            img = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if img is None:
                raise MathImageError(f"Failed to decode mathematical image crop: '{p}'")
            return img

        if isinstance(image_input, np.ndarray):
            if image_input.size == 0:
                raise MathImageError("Mathematical image crop is empty array")
            return image_input.copy()

        raise MathImageError(f"Unsupported image input type: {type(image_input)}")

    @classmethod
    def to_rgb_pil(cls, crop: np.ndarray) -> Image.Image:
        """Convert a BGR or grayscale numpy crop into a PIL RGB Image."""
        if crop is None or crop.size == 0:
            raise MathImageError("Cannot convert empty crop to PIL Image")

        if len(crop.shape) == 2:
            rgb = cv2.cvtColor(crop, cv2.COLOR_GRAY2RGB)
        elif crop.shape[2] == 4:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGRA2RGB)
        elif crop.shape[2] == 3:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        else:
            raise MathImageError(f"Unsupported array shape for crop: {crop.shape}")

        return Image.fromarray(rgb)

    @classmethod
    def pad_crop(cls, crop: np.ndarray, padding: int = 10, fill_val: int = 255) -> np.ndarray:
        """Add white border padding around crop to prevent boundary stroke clipping."""
        if crop is None or crop.size == 0:
            return crop

        return cv2.copyMakeBorder(
            crop,
            top=padding,
            bottom=padding,
            left=padding,
            right=padding,
            borderType=cv2.BORDER_CONSTANT,
            value=(fill_val, fill_val, fill_val) if len(crop.shape) == 3 else fill_val,
        )

    @classmethod
    def is_blank_crop(cls, crop: np.ndarray, min_ink_pixels: int = 10) -> bool:
        """Check whether image crop contains negligible ink pixels."""
        if crop is None or crop.size == 0:
            return True

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return np.count_nonzero(binary) < min_ink_pixels

