"""Reading-order reconstruction supporting multi-column layouts and question-answer blocks."""

import logging
from typing import Any, Dict, List, Optional

from app.recognition.config import RecognitionConfig, DEFAULT_RECOGNITION_CONFIG
from app.recognition.schemas import BoundingBox

logger = logging.getLogger(__name__)


class ReadingOrderReconstructor:
    """Sorts detected text regions into natural human reading order."""

    def __init__(self, config: Optional[RecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_RECOGNITION_CONFIG

    def order_regions(
        self,
        regions: List[Dict[str, Any]],
        page_width: int,
    ) -> List[Dict[str, Any]]:
        """Order a list of region dictionaries into natural reading order.

        Handles:
        1. Multi-column layouts (processes spanning headers first, then left column, then right column).
        2. Top-to-bottom paragraph flow.
        3. Left-to-right alignment within the same horizontal text line band.

        Args:
            regions: List of dicts, each having a 'bounding_box' key (BoundingBox).
            page_width: Total page width in pixels.

        Returns:
            Ordered list of region dicts with 'sequence' and updated 'block_id' keys.
        """
        if not regions:
            return []

        # 1. Check for multi-column layout
        if self.config.multi_column_detection and len(regions) >= 4:
            ordered = self._order_multi_column(regions, page_width)
        else:
            ordered = self._order_single_column(regions)

        # 2. Assign stable sequence numbers and block IDs
        for seq, reg in enumerate(ordered, start=1):
            reg["sequence"] = seq
            page_num = reg.get("page_number", 1)
            reg["block_id"] = f"page-{page_num}-block-{seq}"

        return ordered

    def _order_single_column(self, regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort blocks using vertical banding (top-to-bottom, then left-to-right)."""
        # Sort primarily by y1
        sorted_by_y = sorted(regions, key=lambda r: r["bounding_box"].y1)

        bands: List[List[Dict[str, Any]]] = []
        current_band: List[Dict[str, Any]] = []
        current_y = -1

        tol = self.config.vertical_band_tolerance

        for reg in sorted_by_y:
            y1 = reg["bounding_box"].y1
            if current_y == -1 or abs(y1 - current_y) <= tol:
                current_band.append(reg)
                current_y = y1 if current_y == -1 else current_y
            else:
                bands.append(current_band)
                current_band = [reg]
                current_y = y1

        if current_band:
            bands.append(current_band)

        # Sort within each band by x1 (left-to-right)
        ordered: List[Dict[str, Any]] = []
        for band in bands:
            band_sorted = sorted(band, key=lambda r: r["bounding_box"].x1)
            ordered.extend(band_sorted)

        return ordered

    def _order_multi_column(
        self,
        regions: List[Dict[str, Any]],
        page_width: int,
    ) -> List[Dict[str, Any]]:
        """Detect column split and sort multi-column layouts."""
        mid_x = page_width / 2.0
        gap = self.config.column_gap_threshold

        spanning_headers: List[Dict[str, Any]] = []
        left_col: List[Dict[str, Any]] = []
        right_col: List[Dict[str, Any]] = []

        # Classify each block by column span
        for reg in regions:
            box: BoundingBox = reg["bounding_box"]
            # Spanning header if it crosses across center and spans > 50% page width
            if box.x1 < (mid_x - gap) and box.x2 > (mid_x + gap) and box.width > (page_width * 0.45):
                spanning_headers.append(reg)
            elif box.x2 <= (mid_x + gap / 2.0):
                left_col.append(reg)
            elif box.x1 >= (mid_x - gap / 2.0):
                right_col.append(reg)
            else:
                # Ambiguous: assign to column based on centroid
                center_x = (box.x1 + box.x2) / 2.0
                if center_x < mid_x:
                    left_col.append(reg)
                else:
                    right_col.append(reg)

        # Check if true multi-column distribution exists
        if len(left_col) >= 2 and len(right_col) >= 2:
            ordered_headers = self._order_single_column(spanning_headers)
            ordered_left = self._order_single_column(left_col)
            ordered_right = self._order_single_column(right_col)

            # Insert headers in vertical order relative to columns if headers are interspersed
            return ordered_headers + ordered_left + ordered_right

        # If not clearly multi-column, fall back to standard single column
        return self._order_single_column(regions)

