"""Main recognition pipeline orchestrating text detection, OCR inference, and reading-order reconstruction."""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.preprocessing.image_loader import ImageLoader
from app.recognition.config import RecognitionConfig, DEFAULT_RECOGNITION_CONFIG
from app.recognition.exceptions import (
    RecognitionError,
    RecognitionPipelineError,
)
from app.recognition.handwriting import HandwritingRecognizer
from app.recognition.model_manager import ModelManager
from app.recognition.printed_text import PrintedTextRecognizer
from app.recognition.reading_order import ReadingOrderReconstructor
from app.recognition.schemas import (
    PageRecognitionResult,
    TextBlock,
)
from app.recognition.text_classifier import TextClassifier
from app.recognition.text_detector import TextDetector
from app.recognition.text_normalizer import TextNormalizer

logger = logging.getLogger(__name__)

# Pattern to detect mathematical notation symbols in transcribed text
MATH_SYMBOLS_PATTERN = re.compile(r"[=+\-*/^\\_∑∫√∂πθλ]|x_\d|f\(x\)")


def _detect_math_notation(text: str, crop: np.ndarray) -> bool:
    """Detect presence of mathematical notation from text or visual stroke geometry.

    Exposes candidate mathematical regions for downstream Module 4 without guessing or rewriting equations.
    """
    if text and MATH_SYMBOLS_PATTERN.search(text):
        return True

    if crop is not None and crop.size > 0:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
        # Search for parallel horizontal bars (equal signs or fraction bars)
        for i in range(1, num_labels):
            w1, h1 = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            x1, y1 = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
            if 6 <= w1 <= 60 and 1 <= h1 <= 10:
                for j in range(i + 1, num_labels):
                    w2, h2 = stats[j, cv2.CC_STAT_WIDTH], stats[j, cv2.CC_STAT_HEIGHT]
                    x2, y2 = stats[j, cv2.CC_STAT_LEFT], stats[j, cv2.CC_STAT_TOP]
                    if abs(w1 - w2) <= 5 and abs(x1 - x2) <= 5 and 3 <= abs(y1 - y2) <= 24:
                        return True
    return False


def recognize_page(
    image_path: str,
    submission_id: str,
    page_number: int,
    config: Optional[RecognitionConfig] = None,
) -> PageRecognitionResult:
    """Extract printed and handwritten text from a preprocessed assignment page.

    Pipeline:
    1. Load image safely into memory.
    2. Detect candidate text regions and line bounding boxes.
    3. Reconstruct human reading order (including multi-column support).
    4. Classify regions as 'printed', 'handwritten', or 'unknown'.
    5. Route regions to the appropriate OCR recognition engine (TrOCR / PaddleOCR).
    6. Perform safe text normalization (preserving student phrasing and math).
    7. Generate structured TextBlocks with genuine confidence/quality scores and warnings.
    8. Assemble unified reading-order full text.

    Args:
        image_path: Path to the enhanced page image (from Module 2).
        submission_id: Unique submission ID.
        page_number: 1-based page number.
        config: Optional RecognitionConfig override.

    Returns:
        PageRecognitionResult containing ordered text_blocks, full_text, and honest diagnostics.

    Raises:
        RecognitionPipelineError: If image loading or recognition encounters an unrecoverable failure.
    """
    cfg = config or DEFAULT_RECOGNITION_CONFIG

    # Ensure models are initialized in ModelManager
    model_mgr = ModelManager.get_instance(cfg)
    model_mgr.initialize_models()

    path = Path(image_path).resolve()
    if not path.exists():
        raise RecognitionPipelineError(
            f"Input image not found: '{image_path}'", page_number=page_number
        )

    try:
        image = ImageLoader.load_image(path)
    except Exception as e:
        raise RecognitionPipelineError(
            f"Failed to load image '{image_path}': {e}", page_number=page_number
        ) from e

    h, w = image.shape[:2]
    page_warnings: List[str] = []

    # 1. Detect Text Regions
    detector = TextDetector(config=cfg)
    raw_regions = detector.detect_regions(image, page_number)

    if not raw_regions:
        page_warnings.append("Page contains no detectable text regions.")
        return PageRecognitionResult(
            submission_id=submission_id,
            page_number=page_number,
            status="completed",
            text_blocks=[],
            full_text="",
            warnings=page_warnings,
            metadata={
                "total_blocks": 0,
                "engine_used": ["none"],
                "is_fallback": False,
                "recognition_mode": "empty_page",
                "recognition_available": True,
            },
        )

    # 2. Reconstruct Reading Order
    order_reconstructor = ReadingOrderReconstructor(config=cfg)
    ordered_regions = order_reconstructor.order_regions(raw_regions, page_width=w)

    # 3. Classify and Transcribe Each Region
    printed_recognizer = PrintedTextRecognizer(config=cfg)
    handwriting_recognizer = HandwritingRecognizer(config=cfg)

    text_blocks: List[TextBlock] = []

    try:
        for reg in ordered_regions:
            block_id = reg["block_id"]
            seq = reg["sequence"]
            crop = reg["crop"]
            box = reg["bounding_box"]
            is_diag = reg.get("is_diagram", False)
            block_warnings: List[str] = []

            if is_diag:
                block_type = "unknown"
                raw_text = ""
                conf = None
                quality_score = 0.50
                block_meta = {
                    "engine_used": "none",
                    "is_fallback": True,
                    "recognition_mode": "diagram_region",
                    "recognition_available": False,
                    "model_version": None,
                }
                block_warnings.append("Illustration or diagram detected; coordinates preserved for Module 4.")
            else:
                block_type, class_conf = TextClassifier.classify_region(crop)

                if block_type == "printed":
                    raw_text, conf, quality_score, block_meta = printed_recognizer.recognize(crop, page_number, block_id)
                elif block_type == "handwritten":
                    raw_text, conf, quality_score, block_meta = handwriting_recognizer.recognize(crop, page_number, block_id)
                else:
                    raw_text, conf, quality_score, block_meta = handwriting_recognizer.recognize(crop, page_number, block_id)
                    block_warnings.append("Ambiguous text classification ('unknown'); confidence represents uncertainty.")

            # Check for mathematical symbols/notation
            if _detect_math_notation(raw_text, crop):
                block_warnings.append(
                    "Mathematical notation detected; bounding box preserved for specialized Module 4 processing."
                )

            # Check genuine confidence thresholds
            if conf is not None:
                if conf < cfg.medium_confidence_threshold and not is_diag:
                    block_warnings.append(
                        f"Low recognition confidence ({conf:.2f}). Manual teacher verification recommended."
                    )
            else:
                if not is_diag:
                    block_warnings.append("Model confidence unavailable; text extraction in degraded layout mode.")

            # Check quality heuristics
            if quality_score is not None and quality_score < 0.40 and not is_diag:
                block_warnings.append("Faint or low-contrast text strokes detected.")

            if not raw_text.strip() and not is_diag and not block_meta.get("is_fallback"):
                block_warnings.append("Unreadable text region.")

            # Safe Normalization
            clean_text = TextNormalizer.normalize_block_text(raw_text)

            text_blocks.append(
                TextBlock(
                    block_id=block_id,
                    sequence=seq,
                    type=block_type,
                    text=clean_text,
                    confidence=round(conf, 4) if conf is not None else None,
                    quality_score=round(quality_score, 2) if quality_score is not None else None,
                    bounding_box=box,
                    warnings=block_warnings,
                    metadata=block_meta,
                )
            )

    except Exception as e:
        if isinstance(e, RecognitionPipelineError):
            raise
        raise RecognitionPipelineError(
            f"Recognition pipeline failed on page {page_number}: {e}", page_number=page_number
        ) from e

    # 4. Assemble Full Text in Reading Order
    full_text = TextNormalizer.assemble_full_text([b.text for b in text_blocks])

    # 5. Determine Overall Page Metadata & Status
    total_blocks = len(text_blocks)
    distinct_engines = sorted(list({b.metadata.get("engine_used", "none") for b in text_blocks}))
    all_fallback = all(b.metadata.get("is_fallback", True) for b in text_blocks) if text_blocks else True
    any_fallback = any(b.metadata.get("is_fallback", True) for b in text_blocks) if text_blocks else True

    if all_fallback:
        page_status = "degraded"
        page_warnings.append("No genuine OCR engine was available; page processed in degraded layout-only mode.")
    else:
        page_status = "completed"

    page_metadata = {
        "total_blocks": total_blocks,
        "engine_used": distinct_engines if distinct_engines else ["none"],
        "is_fallback": any_fallback,
        "recognition_mode": "degraded_layout_only" if all_fallback else ("hybrid" if any_fallback else "deep_learning_inference"),
        "recognition_available": not all_fallback,
        "model_version": {
            "handwriting": model_mgr.handwriting_model_version,
            "printed": model_mgr.printed_model_version,
        },
    }

    return PageRecognitionResult(
        submission_id=submission_id,
        page_number=page_number,
        status=page_status,
        text_blocks=text_blocks,
        full_text=full_text,
        warnings=page_warnings,
        metadata=page_metadata,
    )


def recognize_pages(
    pages: List[Any],
    submission_id: str,
    config: Optional[RecognitionConfig] = None,
) -> List[PageRecognitionResult]:
    """Batch recognize text across multiple pages of an assignment submission.

    Ensures that a failure on one page does not cancel or corrupt other valid pages.

    Args:
        pages: List of image paths (strings), dicts, or PreprocessingResult objects.
        submission_id: Unique submission ID.
        config: Optional RecognitionConfig override.

    Returns:
        List of PageRecognitionResult objects.
    """
    results: List[PageRecognitionResult] = []

    for idx, item in enumerate(pages):
        page_num = idx + 1
        img_path = ""

        if isinstance(item, str):
            img_path = item
        elif isinstance(item, dict):
            img_path = str(item.get("enhanced_image_path") or item.get("image_path") or item.get("path"))
            page_num = int(item.get("page_number", idx + 1))
        elif hasattr(item, "enhanced_image_path"):
            img_path = str(item.enhanced_image_path)
            page_num = int(getattr(item, "page_number", idx + 1))
        elif hasattr(item, "image_path"):
            img_path = str(item.image_path)
            page_num = int(getattr(item, "page_number", idx + 1))
        else:
            raise RecognitionPipelineError(
                f"Unsupported page input format at index {idx}: {type(item)}", page_number=page_num
            )

        try:
            res = recognize_page(
                image_path=img_path,
                submission_id=submission_id,
                page_number=page_num,
                config=config,
            )
            results.append(res)
        except Exception as e:
            logger.error("Failed to recognize page %d in batch: %s", page_num, e)
            results.append(
                PageRecognitionResult(
                    submission_id=submission_id,
                    page_number=page_num,
                    status="failed",
                    text_blocks=[],
                    full_text="",
                    warnings=[f"Recognition failed on page {page_num}: {e}"],
                    metadata={
                        "total_blocks": 0,
                        "engine_used": ["none"],
                        "is_fallback": True,
                        "recognition_mode": "failed",
                        "recognition_available": False,
                    },
                )
            )

    return results
