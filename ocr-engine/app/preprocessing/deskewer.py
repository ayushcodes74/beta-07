"""Skew detection and alignment correction service."""

import logging
from typing import Optional, Tuple
import cv2
import numpy as np

from app.preprocessing.config import PreprocessingConfig, DEFAULT_PREPROCESSING_CONFIG

logger = logging.getLogger(__name__)


class Deskewer:
    """Estimates dominant text tilt and performs deskewing on scanned assignment images."""

    def __init__(self, config: Optional[PreprocessingConfig] = None) -> None:
        self.config = config or DEFAULT_PREPROCESSING_CONFIG

    def deskew(self, image: np.ndarray) -> Tuple[np.ndarray, float, float, Optional[str]]:
        """Estimate skew angle and apply correction to align text horizontally.

        Args:
            image: BGR numpy image array.

        Returns:
            Tuple of (deskewed_image, estimated_angle, corrected_angle, warning_message).
        """
        if not self.config.enable_deskew:
            return image, 0.0, 0.0, None

        estimated_angle, warning = self.estimate_skew_angle(image)

        # Check bounds
        if abs(estimated_angle) > self.config.max_deskew_angle:
            warn = (
                f"Estimated skew angle ({estimated_angle:.1f}°) exceeds maximum allowable "
                f"limit of {self.config.max_deskew_angle}°. Deskewing skipped to prevent distortion."
            )
            return image, round(estimated_angle, 2), 0.0, warn

        # If angle is minimal, skip rotation to avoid unnecessary resampling blur
        if abs(estimated_angle) < self.config.deskew_min_angle:
            return image, round(estimated_angle, 2), 0.0, None

        # Apply rotation correction
        corrected_image = self.rotate_image_bound(image, -estimated_angle)
        return corrected_image, round(estimated_angle, 2), round(estimated_angle, 2), warning

    def estimate_skew_angle(self, image: np.ndarray) -> Tuple[float, Optional[str]]:
        """Estimate the dominant text orientation angle.

        Uses a robust hybrid approach:
        1. Primary: Probabilistic Hough transform on edge contours to find text line directions.
           This is robust against shadows, gradients, and margin marks.
        2. Fallback: Projection profile variance optimization if insufficient line segments exist.

        Returns:
            Tuple of (angle_in_degrees, warning_message).
        """
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            h, w = gray.shape

            # Downsample if image is large for faster processing
            target_dim = 1000.0
            scale = min(1.0, target_dim / max(h, w))
            if scale < 1.0:
                small = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            else:
                small = gray

            # Primary: Canny edges + Hough lines
            edges = cv2.Canny(small, 50, 150, apertureSize=3)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40, minLineLength=40, maxLineGap=10)

            if lines is not None and len(lines) >= 3:
                angles = []
                for l in lines.reshape(-1, 4):
                    dx = float(l[2] - l[0])
                    dy = float(l[3] - l[1])
                    if dx != 0:
                        ang = float(np.degrees(np.arctan2(dy, dx)))
                        if abs(ang) <= self.config.max_deskew_angle:
                            angles.append(ang)

                if len(angles) >= 3:
                    median_angle = float(np.median(angles))
                    return median_angle, None

            # Fallback: Projection Profile Variance on adaptive thresholded canvas
            thresh = cv2.adaptiveThreshold(
                small, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
            )
            sh, sw = thresh.shape
            center = (sw / 2.0, sh / 2.0)
            margin_y = int(sh * 0.1)
            margin_x = int(sw * 0.1)

            best_angle = 0.0
            best_var = -1.0
            coarse_angles = np.arange(-self.config.max_deskew_angle, self.config.max_deskew_angle + 0.5, 0.5)

            for a in coarse_angles:
                m = cv2.getRotationMatrix2D(center, float(a), 1.0)
                rotated = cv2.warpAffine(thresh, m, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
                inner = rotated[margin_y : sh - margin_y, margin_x : sw - margin_x]
                proj = np.sum(inner, axis=1)
                v = float(np.var(proj))
                if v > best_var:
                    best_var = v
                    best_angle = float(a)

            return -best_angle, None

        except Exception as e:
            logger.warning("Deskew angle estimation failed: %s", e)
            return 0.0, f"Skew estimation failed: {e}"

    @staticmethod
    def rotate_image_bound(image: np.ndarray, angle: float) -> np.ndarray:
        """Rotate image by an arbitrary angle while preserving the canvas and white page background."""
        h, w = image.shape[:2]
        center = (w / 2.0, h / 2.0)

        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        # Determine new bounding dimensions
        cos_val = abs(rot_mat[0, 0])
        sin_val = abs(rot_mat[0, 1])
        new_w = int((h * sin_val) + (w * cos_val))
        new_h = int((h * cos_val) + (w * sin_val))

        # Adjust the rotation matrix with translation
        rot_mat[0, 2] += (new_w / 2.0) - center[0]
        rot_mat[1, 2] += (new_h / 2.0) - center[1]

        border_val = (255, 255, 255) if len(image.shape) == 3 else 255
        return cv2.warpAffine(
            image,
            rot_mat,
            (new_w, new_h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=border_val,
        )
