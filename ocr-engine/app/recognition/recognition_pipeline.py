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

# Pattern to detect mathematical notation symbols
MATH_SYMBOLS_PATTERN = re.compile(r"[=+\-*/^\\_∑∫√∂πθλ]|x_\d|f\(x\)")


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
    5. Route regions to the appropriate OCR recognition engine.
    6. Perform safe text normalization (preserving student phrasing and math).
    7. Generate structured TextBlocks with honest confidence scores and warnings.
    8. Assemble unified reading-order full text.

    Args:
        image_path: Path to the enhanced page image (from Module 2).
        submission_id: Unique submission ID.
        page_number: 1-based page number.
        config: Optional RecognitionConfig override.

    Returns:
        PageRecognitionResult containing ordered text_blocks, full_text, and diagnostics.

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
                # Illustration or diagram detected: do not treat as ordinary text
                block_type = "unknown"
                raw_text = ""
                conf = 0.50
                block_warnings.append("Illustration or diagram detected; coordinates preserved for Module 4.")
            else:
                # Classify printed vs. handwritten
                block_type, class_conf = TextClassifier.classify_region(crop)

                # Recognize based on classification
                if block_type == "printed":
                    raw_text, conf = printed_recognizer.recognize(crop, page_number, block_id)
                elif block_type == "handwritten":
                    raw_text, conf = handwriting_recognizer.recognize(crop, page_number, block_id)
                else:
                    # Unknown: try handwriting recognizer as fallback, but flag uncertainty
                    raw_text, conf = handwriting_recognizer.recognize(crop, page_number, block_id)
                    block_warnings.append("Ambiguous text classification ('unknown'); confidence represents uncertainty.")

            # Check for mathematical symbols
            if MATH_SYMBOLS_PATTERN.search(raw_text):
                block_warnings.append(
                    "Mathematical notation detected; bounding box preserved for specialized Module 4 processing."
                )

            # Check confidence thresholds
            if conf < cfg.medium_confidence_threshold and not is_diag:
                block_warnings.append(
                    f"Low recognition confidence ({conf:.2f}). Manual teacher verification recommended."
                )

            if not raw_text.strip() and not is_diag:
                block_warnings.append("Unreadable or faint text region.")

            # Safe Normalization
            clean_text = TextNormalizer.normalize_block_text(raw_text)

            text_blocks.append(
                TextBlock(
                    block_id=block_id,
                    sequence=seq,
                    type=block_type,
                    text=clean_text,
                    confidence=round(conf, 2),
                    bounding_box=box,
                    warnings=block_warnings,
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

    return PageRecognitionResult(
        submission_id=submission_id,
        page_number=page_number,
        status="completed",
        text_blocks=text_blocks,
        full_text=full_text,
        warnings=page_warnings,
        metadata={"total_blocks": len(text_blocks)},
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
            # Create graceful failed page result preserving other pages
            results.append(
                PageRecognitionResult(
                    submission_id=submission_id,
                    page_number=page_num,
                    status="failed",
                    text_blocks=[],
                    full_text="",
                    warnings=[f"Recognition failed on page {page_num}: {e}"],
                )
            )

    return results
