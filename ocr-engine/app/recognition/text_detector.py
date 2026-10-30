"""Text region and line detection service."""

import logging
from typing import Any, Dict, List, Optional
import cv2
import numpy as np

from app.recognition.config import RecognitionConfig, DEFAULT_RECOGNITION_CONFIG
from app.recognition.exceptions import TextDetectionError
from app.recognition.schemas import BoundingBox

logger = logging.getLogger(__name__)


class TextDetector:
    """Detects text regions, lines, and paragraphs from scanned assignment images."""

    def __init__(self, config: Optional[RecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_RECOGNITION_CONFIG

    def detect_regions(
        self,
        image: np.ndarray,
        page_number: int,
    ) -> List[Dict[str, Any]]:
        """Segment an enhanced page image into candidate text regions.

        Args:
            image: BGR numpy image array.
            page_number: 1-based page index.

        Returns:
            List of region dictionaries containing:
            - 'region_id': Unique region ID
            - 'page_number': Page number
            - 'bounding_box': BoundingBox model
            - 'crop': Cropped BGR image array
            - 'is_diagram': Whether region appears to be an illustration/figure
            - 'confidence': Detection confidence

        Raises:
            TextDetectionError: If detection algorithm encounters an unrecoverable failure.
        """
        try:
            if image is None or image.size == 0:
                return []

            h, w = image.shape[:2]
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

            # 1. Binarize using adaptive threshold to handle varying ink and lighting
            binary = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                blockSize=25,
                C=15,
            )

            # 2. Horizontal morphological dilation to merge character glyphs into lines
            kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (self.config.dilation_kernel_width, self.config.dilation_kernel_height),
            )
            dilated = cv2.dilate(binary, kernel, iterations=1)

            # 3. Find connected contours
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            raw_regions: List[Dict[str, Any]] = []

            for idx, cnt in enumerate(contours):
                x, y, bw, bh = cv2.boundingRect(cnt)

                # Filter tiny noise
                if bw < self.config.min_region_width or bh < self.config.min_region_height:
                    continue

                # Filter full-width rule dividers (e.g. header line: width > 90% page, height < 4px)
                if bw > int(w * 0.9) and bh < 4:
                    continue

                # Detect if region is a large drawing/diagram rather than standard text
                # (Large area but low pixel density)
                is_diagram = False
                area = bw * bh
                if area > (w * h * 0.15) and bw > (w * 0.4) and bh > (h * 0.25):
                    # Check density of ink in bounding box
                    box_binary = binary[y : y + bh, x : x + bw]
                    density = float(np.count_nonzero(box_binary)) / float(area)
                    if density < 0.05:
                        is_diagram = True

                crop = image[y : y + bh, x : x + bw]
                box = BoundingBox(x1=x, y1=y, x2=x + bw, y2=y + bh)

                raw_regions.append(
                    {
                        "region_id": f"page-{page_number}-region-{idx + 1}",
                        "page_number": page_number,
                        "bounding_box": box,
                        "crop": crop,
                        "is_diagram": is_diagram,
                        "confidence": 0.95,
                    }
                )

            return raw_regions

        except Exception as e:
            logger.error("Text region detection failed on page %d: %s", page_number, e)
            raise TextDetectionError(
                f"Failed to detect text regions on page {page_number}: {e}",
                page_number=page_number,
            ) from e

