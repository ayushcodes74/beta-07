"""Validation service for mathematical region bounding boxes and dimensions."""

import logging
from typing import Optional, Tuple
import numpy as np

from app.math_recognition.config import MathRecognitionConfig, DEFAULT_MATH_CONFIG
from app.math_recognition.exceptions import MathRegionValidationError
from app.math_recognition.schemas import BoundingBox

logger = logging.getLogger(__name__)


class MathRegionValidator:
    """Validates mathematical bounding boxes and ensures coordinate integrity."""

    def __init__(self, config: Optional[MathRecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_MATH_CONFIG

    def validate_region(
        self,
        box: BoundingBox,
        page_width: Optional[int] = None,
        page_height: Optional[int] = None,
        crop: Optional[np.ndarray] = None,
        region_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validate bounding box coordinates and corresponding crop dimensions.

        Args:
            box: BoundingBox instance.
            page_width: Optional page width in pixels for boundary checking.
            page_height: Optional page height in pixels for boundary checking.
            crop: Optional crop image array to compare dimensions.
            region_id: Optional region ID for diagnostic messages.

        Returns:
            Tuple of (is_valid, error_message).
        """
        # 1. Coordinate Ordering Checks
        if box.x2 <= box.x1:
            return False, f"Invalid width: x2 ({box.x2}) must be strictly greater than x1 ({box.x1})"
        if box.y2 <= box.y1:
            return False, f"Invalid height: y2 ({box.y2}) must be strictly greater than y1 ({box.y1})"

        # 2. Minimum Dimension Limits
        if box.width < self.config.min_region_width:
            return False, f"Region width {box.width}px is below minimum threshold ({self.config.min_region_width}px)"
        if box.height < self.config.min_region_height:
            return False, f"Region height {box.height}px is below minimum threshold ({self.config.min_region_height}px)"

        # 3. Page Boundary Limits
        if page_width is not None and box.x2 > page_width:
            return False, f"Bounding box x2 ({box.x2}) extends beyond page width ({page_width})"
        if page_height is not None and box.y2 > page_height:
            return False, f"Bounding box y2 ({box.y2}) extends beyond page height ({page_height})"

        # 4. Crop Alignment Checks
        if crop is not None:
            if crop.size == 0:
                return False, "Provided crop image array is empty (0 pixels)"
            ch, cw = crop.shape[:2]
            # Allow minor padding tolerance (+- 2 pixels)
            if abs(cw - box.width) > 4 or abs(ch - box.height) > 4:
                logger.warning(
                    "Crop dimensions (%dx%d) diverge from bounding box (%dx%d) for region %s",
                    cw,
                    ch,
                    box.width,
                    box.height,
                    region_id or "unknown",
                )

        return True, None

    def assert_valid_region(
        self,
        box: BoundingBox,
        page_width: Optional[int] = None,
        page_height: Optional[int] = None,
        crop: Optional[np.ndarray] = None,
        region_id: Optional[str] = None,
    ) -> None:
        """Validate region and raise MathRegionValidationError if invalid."""
        is_valid, msg = self.validate_region(box, page_width, page_height, crop, region_id)
        if not is_valid:
            raise MathRegionValidationError(
                msg or "Invalid mathematical bounding box",
                region_id=region_id,
            )

