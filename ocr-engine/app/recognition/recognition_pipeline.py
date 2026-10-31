"""Main recognition pipeline orchestrating text detection, OCR inference, and reading-order reconstruction."""

import logging
import re
import time
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
from app.recognition.ocr_space import OCRSpaceError
from app.recognition.printed_text import PrintedTextRecognizer
from app.recognition.reading_order import ReadingOrderReconstructor
from app.recognition.schemas import (
    BoundingBox,
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


def _block_warnings(
    raw_text: str,
    crop: np.ndarray,
    conf: Optional[float],
    quality_score: Optional[float],
    is_diag: bool,
    is_fallback: bool,
    cfg: RecognitionConfig,
) -> List[str]:
    """Shared per-block math / confidence / quality warnings."""
    warnings: List[str] = []

    if _detect_math_notation(raw_text, crop):
        warnings.append(
            "Mathematical notation detected; bounding box preserved for specialized Module 4 processing."
        )

    if conf is not None:
        if conf < cfg.medium_confidence_threshold and not is_diag:
            warnings.append(
                f"Low recognition confidence ({conf:.2f}). Manual teacher verification recommended."
            )
    elif not is_diag and is_fallback:
        warnings.append("Model confidence unavailable; text extraction in degraded layout mode.")

    if quality_score is not None and quality_score < 0.40 and not is_diag:
        warnings.append("Faint or low-contrast text strokes detected.")

    if not raw_text.strip() and not is_diag and not is_fallback:
        warnings.append("Unreadable text region.")

    return warnings


def _group_paddle_lines(
    items: List[Dict[str, Any]], gap_factor: float
) -> List[List[List[Dict[str, Any]]]]:
    """Group PaddleOCR fragments into visual lines, then split each line at wide column gaps.

    PaddleOCR often returns individual words/numbers (especially for handwriting and tables).
    Fragments whose vertical extents overlap by at least half of the smaller height share a line.

    Returns:
        Lines in top-to-bottom order; each line is a list of segments in left-to-right order;
        each segment is a list of fragments.
    """
    lines: List[Dict[str, Any]] = []  # {"y1", "y2" (running means), "items"}

    for it in sorted(items, key=lambda r: (r["box"][1] + r["box"][3]) / 2.0):
        _, y1, _, y2 = it["box"]
        best, best_overlap = None, 0.0
        for ln in lines[-6:]:  # only nearby recent lines can overlap
            overlap = min(y2, ln["y2"]) - max(y1, ln["y1"])
            min_h = min(y2 - y1, ln["y2"] - ln["y1"])
            if min_h > 0 and overlap >= 0.5 * min_h and overlap > best_overlap:
                best, best_overlap = ln, overlap
        if best is None:
            lines.append({"y1": float(y1), "y2": float(y2), "items": [it]})
        else:
            best["items"].append(it)
            n = len(best["items"])
            best["y1"] += (y1 - best["y1"]) / n
            best["y2"] += (y2 - best["y2"]) / n

    lines.sort(key=lambda ln: (ln["y1"] + ln["y2"]) / 2.0)

    grouped: List[List[List[Dict[str, Any]]]] = []
    for ln in lines:
        row = sorted(ln["items"], key=lambda r: r["box"][0])
        heights = [r["box"][3] - r["box"][1] for r in row]
        max_gap = gap_factor * float(np.median(heights))
        segments: List[List[Dict[str, Any]]] = [[row[0]]]
        for prev, cur in zip(row, row[1:]):
            if cur["box"][0] - prev["box"][2] > max_gap:
                segments.append([cur])
            else:
                segments[-1].append(cur)
        grouped.append(segments)
    return grouped


def _recognize_page_with_paddle(
    image: np.ndarray,
    submission_id: str,
    page_number: int,
    cfg: RecognitionConfig,
    model_mgr: ModelManager,
) -> PageRecognitionResult:
    """Full-page PaddleOCR path: Paddle detects and recognizes all lines (printed and handwritten)."""
    try:
        fragments = model_mgr.recognize_page_lines(image)
    except Exception as e:
        raise RecognitionPipelineError(
            f"PaddleOCR recognition failed on page {page_number}: {e}", page_number=page_number
        ) from e
    return _build_page_from_lines(
        image, fragments, submission_id, page_number, cfg, model_mgr,
        engine="paddleocr", model_version=model_mgr.printed_model_version, device=model_mgr.device,
    )


# OCR.space errors that won't fix themselves page-by-page: skip the API for a while instead of
# paying a failing round trip on every page.
_OCR_SPACE_COOLDOWN_SECONDS = 600
_OCR_SPACE_HARD_ERROR_MARKERS = ("http 401", "http 403", "http 429", "limit", "quota", "exceeded", "api key")
_ocr_space_disabled_until = 0.0


def _recognize_page_with_ocr_space(
    image: np.ndarray,
    submission_id: str,
    page_number: int,
    cfg: RecognitionConfig,
    model_mgr: ModelManager,
) -> PageRecognitionResult:
    """OCR.space (cloud) path. Raises OCRSpaceError so the caller can fall back to PaddleOCR."""
    global _ocr_space_disabled_until
    client = model_mgr.ocr_space_client
    if time.monotonic() < _ocr_space_disabled_until:
        raise OCRSpaceError("OCR.space temporarily skipped after a key/quota error")
    try:
        lines = client.recognize_lines(image)
    except OCRSpaceError as e:
        if any(marker in str(e).lower() for marker in _OCR_SPACE_HARD_ERROR_MARKERS):
            _ocr_space_disabled_until = time.monotonic() + _OCR_SPACE_COOLDOWN_SECONDS
            logger.warning("OCR.space disabled for %ds after: %s", _OCR_SPACE_COOLDOWN_SECONDS, e)
        raise
    return _build_page_from_lines(
        image, lines, submission_id, page_number, cfg, model_mgr,
        engine="ocrspace", model_version=client.model_version, device="cloud",
    )


def _build_page_from_lines(
    image: np.ndarray,
    fragments: List[Dict[str, Any]],
    submission_id: str,
    page_number: int,
    cfg: RecognitionConfig,
    model_mgr: ModelManager,
    *,
    engine: str,
    model_version: Optional[str],
    device: str,
) -> PageRecognitionResult:
    """Turn engine line/fragment results (``text``, ``score`` or None, ``box``) into a page result."""
    page_warnings: List[str] = []

    page_meta_base = {
        "engine_used": [engine],
        "is_fallback": False,
        "recognition_available": True,
        "model_version": {"handwriting": model_version, "printed": model_version},
    }

    if not fragments:
        page_warnings.append("Page contains no detectable text regions.")
        return PageRecognitionResult(
            submission_id=submission_id,
            page_number=page_number,
            status="completed",
            text_blocks=[],
            full_text="",
            warnings=page_warnings,
            metadata={**page_meta_base, "total_blocks": 0, "recognition_mode": "empty_page"},
        )

    block_meta = {
        "engine_used": engine,
        "model_version": model_version,
        "is_fallback": False,
        "recognition_mode": "deep_learning_inference",
        "recognition_available": True,
        "device": device,
    }

    text_blocks: List[TextBlock] = []
    full_text_lines: List[str] = []
    seq = 0

    try:
        for line_segments in _group_paddle_lines(fragments, cfg.line_merge_gap_factor):
            line_texts: List[str] = []
            for segment in line_segments:
                seq += 1
                block_id = f"page-{page_number}-block-{seq}"

                x1 = min(f["box"][0] for f in segment)
                y1 = min(f["box"][1] for f in segment)
                x2 = max(f["box"][2] for f in segment)
                y2 = max(f["box"][3] for f in segment)
                crop = image[y1:y2, x1:x2]

                raw_text = " ".join(f["text"].strip() for f in segment)
                # Character-weighted mean of the engine's recognition scores (None if the engine
                # reports no confidence, e.g. OCR.space)
                conf: Optional[float] = None
                if all(f.get("score") is not None for f in segment):
                    weights = [max(1, len(f["text"].strip())) for f in segment]
                    conf = float(np.average([f["score"] for f in segment], weights=weights))
                    conf = min(1.0, max(0.0, conf))

                block_type, _ = TextClassifier.classify_region(crop)
                quality_score = model_mgr._compute_image_quality_score(crop) if crop.size else None
                clean_text = TextNormalizer.normalize_block_text(raw_text)

                text_blocks.append(
                    TextBlock(
                        block_id=block_id,
                        sequence=seq,
                        type=block_type,
                        text=clean_text,
                        confidence=round(conf, 4) if conf is not None else None,
                        quality_score=round(quality_score, 2) if quality_score is not None else None,
                        bounding_box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                        warnings=_block_warnings(raw_text, crop, conf, quality_score, False, False, cfg),
                        metadata={**block_meta, "fragments": len(segment)},
                    )
                )
                if clean_text:
                    line_texts.append(clean_text)
            if line_texts:
                full_text_lines.append(" ".join(line_texts))
    except Exception as e:
        if isinstance(e, RecognitionPipelineError):
            raise
        raise RecognitionPipelineError(
            f"Recognition pipeline failed on page {page_number}: {e}", page_number=page_number
        ) from e

    low_conf = sum(
        1 for b in text_blocks if b.confidence is not None and b.confidence < cfg.medium_confidence_threshold
    )
    if low_conf:
        page_warnings.append(
            f"{low_conf} of {len(text_blocks)} text blocks have low recognition confidence; teacher review recommended."
        )

    return PageRecognitionResult(
        submission_id=submission_id,
        page_number=page_number,
        status="completed",
        text_blocks=text_blocks,
        full_text="\n".join(full_text_lines),
        warnings=page_warnings,
        metadata={
            **page_meta_base,
            "total_blocks": len(text_blocks),
            "recognition_mode": "deep_learning_inference",
        },
    )


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

    # Primary path: OCR.space Engine 3 (cloud), falling back to local PaddleOCR on any failure.
    ocr_space_failure: Optional[str] = None
    if model_mgr.uses_ocr_space:
        try:
            return _recognize_page_with_ocr_space(image, submission_id, page_number, cfg, model_mgr)
        except OCRSpaceError as e:
            ocr_space_failure = str(e)
            logger.warning("Page %d: %s; falling back to local OCR.", page_number, e)

    # Local full-page path: PaddleOCR detects and recognizes the whole page.
    if model_mgr.uses_paddle_page_mode:
        result = _recognize_page_with_paddle(image, submission_id, page_number, cfg, model_mgr)
        if ocr_space_failure:
            result.warnings.insert(0, f"OCR.space unavailable ({ocr_space_failure}); recognized with local PaddleOCR.")
            result.metadata["ocr_space_error"] = ocr_space_failure
        return result

    # Legacy path (backend 'auto'/'trocr', or PaddleOCR unavailable -> degraded layout-only mode)
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

            block_warnings.extend(
                _block_warnings(
                    raw_text, crop, conf, quality_score, is_diag, bool(block_meta.get("is_fallback")), cfg
                )
            )

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
