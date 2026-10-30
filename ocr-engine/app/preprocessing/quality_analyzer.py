"""Quality assessment service for scanned assignment images."""

from typing import List, Optional, Tuple
import cv2
import numpy as np

from app.preprocessing.config import PreprocessingConfig, DEFAULT_PREPROCESSING_CONFIG
from app.preprocessing.schemas import ImageQualityMetrics


class QualityAnalyzer:
    """Analyzes image dimensions, blur, contrast, brightness, and blank page status."""

    def __init__(self, config: Optional[PreprocessingConfig] = None) -> None:
        self.config = config or DEFAULT_PREPROCESSING_CONFIG

    def analyze_quality(
        self,
        image: np.ndarray,
        estimated_skew: float = 0.0,
        corrected_skew: float = 0.0,
        orientation_corrected: bool = False,
        extra_warnings: Optional[List[str]] = None,
    ) -> ImageQualityMetrics:
        """Compute diagnostic quality metrics for an image.

        Args:
            image: BGR or grayscale numpy image.
            estimated_skew: Estimated skew angle.
            corrected_skew: Applied skew angle.
            orientation_corrected: Whether 90/180/270 orientation correction was applied.
            extra_warnings: Additional warnings accumulated from pipeline stages.

        Returns:
            ImageQualityMetrics instance.
        """
        h, w = image.shape[:2]
        warnings: List[str] = list(extra_warnings or [])
        needs_review = False

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

        # 1. Resolution Check
        is_low_res = False
        if w < self.config.min_ocr_width or h < self.config.min_ocr_height:
            is_low_res = True
            warnings.append(
                f"Low resolution image ({w}x{h} px). Recommended minimum is "
                f"{self.config.min_ocr_width}x{self.config.min_ocr_height} px for OCR."
            )

        # 2. Brightness & Contrast
        mean_intensity = float(np.mean(gray))
        std_intensity = float(np.std(gray))

        # 3. Blank Page Detection
        is_blank = False
        if std_intensity < self.config.blank_std_threshold:
            is_blank = True
            needs_review = True
            warnings.append("Page appears blank or contains almost no written content.")

        # 4. Blur Estimation (Laplacian variance)
        blur_val = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if blur_val < self.config.blur_threshold and not is_blank:
            needs_review = True
            warnings.append(
                f"Image may be blurry (Laplacian variance: {blur_val:.1f} < {self.config.blur_threshold})."
            )

        # 5. Extreme brightness warnings
        if mean_intensity < 40.0:
            needs_review = True
            warnings.append(f"Image is excessively dark (mean brightness: {mean_intensity:.1f}/255).")

        # 6. Flag review if any critical warning is present
        if any("review" in w.lower() for w in warnings):
            needs_review = True

        return ImageQualityMetrics(
            width=w,
            height=h,
            estimated_skew_angle=round(estimated_skew, 2),
            corrected_skew_angle=round(corrected_skew, 2),
            orientation_corrected=orientation_corrected,
            is_low_resolution=is_low_res,
            needs_review=needs_review,
            warnings=warnings,
            blur_score=round(blur_val, 2),
            brightness_score=round(mean_intensity, 2),
            contrast_score=round(std_intensity, 2),
            is_blank=is_blank,
        )

