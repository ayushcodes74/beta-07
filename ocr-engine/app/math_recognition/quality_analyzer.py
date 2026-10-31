"""Quality analysis service evaluating physical image properties of mathematical regions."""

import logging
from typing import List, Optional, Tuple
import cv2
import numpy as np

from app.math_recognition.config import MathRecognitionConfig, DEFAULT_MATH_CONFIG
from app.math_recognition.schemas import BoundingBox, MathQualityAssessment

logger = logging.getLogger(__name__)


class MathQualityAnalyzer:
    """Analyzes mathematical crop readability, focus, stroke contrast, and boundary completeness."""

    def __init__(self, config: Optional[MathRecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_MATH_CONFIG

    def analyze_crop(
        self,
        crop: np.ndarray,
        box: Optional[BoundingBox] = None,
    ) -> MathQualityAssessment:
        """Perform comprehensive physical image quality analysis on a mathematical crop.

        This evaluates strictly visual image quality and is completely distinct from
        mathematical model recognition confidence.

        Args:
            crop: BGR or grayscale numpy image array.
            box: Optional BoundingBox on the parent page.

        Returns:
            MathQualityAssessment with structured quality metrics and review flags.
        """
        if crop is None or crop.size == 0:
            return MathQualityAssessment(
                quality_score=0.0,
                is_readable=False,
                is_complete=False,
                requires_manual_review=True,
                is_faint=False,
                is_blurred=False,
                is_low_resolution=True,
                is_cropped=False,
                has_overlapping_strokes=False,
                warnings=["Empty or zero-pixel mathematical crop."],
                uncertain_regions=[],
            )

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        h, w = gray.shape
        warnings: List[str] = []
        uncertain_regions: List[BoundingBox] = []

        # 1. Stroke Binarization & Ink Pixel Statistics
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        total_pixels = h * w
        ink_pixels = np.count_nonzero(binary)

        if ink_pixels < 10:
            return MathQualityAssessment(
                quality_score=0.10,
                is_readable=False,
                is_complete=False,
                requires_manual_review=True,
                is_faint=True,
                is_blurred=False,
                is_low_resolution=False,
                is_cropped=False,
                has_overlapping_strokes=False,
                warnings=["Unreadable crop: insufficient ink pixels detected."],
                uncertain_regions=[],
            )

        # 2. Contrast & Faint Handwriting Detection
        std_val = float(np.std(gray))
        is_faint = std_val < self.config.faint_contrast_threshold
        if is_faint:
            warnings.append(
                f"Faint mathematical writing detected (contrast std={std_val:.1f} < {self.config.faint_contrast_threshold:.1f})."
            )

        # 3. Blur & Sharpness Analysis (Laplacian Variance)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_blurred = laplacian_var < self.config.blur_threshold
        if is_blurred:
            warnings.append(
                f"Blurred or out-of-focus mathematical region (sharpness={laplacian_var:.1f} < {self.config.blur_threshold:.1f})."
            )

        # 4. Low Resolution Analysis
        is_low_res = (w < 35) or (h < 20)
        if is_low_res:
            warnings.append(
                f"Low resolution ({w}x{h}px); sub-symbol discrimination (subscripts/powers) may be compromised."
            )

        # 5. Boundary Cropping / Truncation Check
        # Check if ink touches outer perimeter pixels of the crop
        m = self.config.boundary_touch_margin
        top_ink = np.count_nonzero(binary[0:m, :])
        bottom_ink = np.count_nonzero(binary[h - m : h, :])
        left_ink = np.count_nonzero(binary[:, 0:m])
        right_ink = np.count_nonzero(binary[:, w - m : w])

        is_cropped = False
        if top_ink > 3 or bottom_ink > 3 or left_ink > 3 or right_ink > 3:
            is_cropped = True
            warnings.append(
                "Mathematical expression touches crop boundaries; strokes or symbols may be truncated."
            )

        # 6. Overlapping Strokes & Entanglement Analysis
        has_overlapping = False
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
        if num_labels > 1:
            for i in range(1, num_labels):
                cw = stats[i, cv2.CC_STAT_WIDTH]
                ch = stats[i, cv2.CC_STAT_HEIGHT]
                c_area = stats[i, cv2.CC_STAT_AREA]
                # High density component that is large in both dimensions
                if c_area > 400 and (c_area / float(cw * ch)) > 0.70:
                    has_overlapping = True
                    # Localize uncertain sub-region
                    rx1, ry1 = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
                    uncertain_regions.append(
                        BoundingBox(x1=rx1, y1=ry1, x2=rx1 + cw, y2=ry1 + ch)
                    )
                    break

        if has_overlapping:
            warnings.append("Dense overlapping or entangled strokes detected in mathematical region.")

        # 7. Overall Quality Score Computation
        # Base quality from contrast std (normalized to [0.2, 0.95])
        contrast_factor = min(1.0, max(0.1, std_val / 50.0))
        # Sharpness factor
        sharpness_factor = min(1.0, max(0.1, laplacian_var / 300.0))
        # Resolution factor
        res_factor = min(1.0, max(0.2, min(w / 120.0, h / 40.0)))

        raw_score = 0.40 * contrast_factor + 0.35 * sharpness_factor + 0.25 * res_factor

        # Penalties
        if is_faint:
            raw_score *= 0.75
        if is_blurred:
            raw_score *= 0.75
        if is_cropped:
            raw_score *= 0.80
        if has_overlapping:
            raw_score *= 0.85

        final_quality = round(float(np.clip(raw_score, 0.10, 0.98)), 2)

        # Readability & Review Flags
        is_readable = final_quality >= 0.45 and not is_blurred and not is_faint
        is_complete = not is_cropped
        requires_manual_review = (
            (not is_readable)
            or (not is_complete)
            or is_low_res
            or (final_quality < self.config.medium_confidence_threshold)
        )

        return MathQualityAssessment(
            quality_score=final_quality,
            is_readable=is_readable,
            is_complete=is_complete,
            requires_manual_review=requires_manual_review,
            is_faint=is_faint,
            is_blurred=is_blurred,
            is_low_resolution=is_low_res,
            is_cropped=is_cropped,
            has_overlapping_strokes=has_overlapping,
            warnings=warnings,
            uncertain_regions=uncertain_regions,
        )

