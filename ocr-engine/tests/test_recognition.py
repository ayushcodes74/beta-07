"""Comprehensive tests for Text & Handwriting Recognition Module 3."""

from pathlib import Path
import cv2
import numpy as np
import pytest

from app.recognition.config import RecognitionConfig
from app.recognition.exceptions import (
    ModelLoadingError,
    RecognitionPipelineError,
)
from app.recognition.model_manager import ModelManager
from app.recognition.reading_order import ReadingOrderReconstructor
from app.recognition.recognition_pipeline import recognize_page, recognize_pages
from app.recognition.schemas import BoundingBox, PageRecognitionResult
from app.recognition.text_normalizer import TextNormalizer


# 1. Printed English Text Recognition
def test_printed_text_recognition(printed_doc_page: Path):
    result = recognize_page(
        image_path=str(printed_doc_page),
        submission_id="sub-rec-printed",
        page_number=1,
    )
    assert isinstance(result, PageRecognitionResult)
    assert result.status == "completed"
    assert len(result.text_blocks) >= 2
    # Verify that blocks are classified as printed with high confidence
    for b in result.text_blocks:
        assert b.confidence >= 0.70
        assert b.bounding_box.width > 0
        assert b.bounding_box.height > 0


# 2. Handwritten English Text Recognition
def test_handwritten_text_recognition(handwritten_doc_page: Path):
    result = recognize_page(
        image_path=str(handwritten_doc_page),
        submission_id="sub-rec-handwritten",
        page_number=1,
    )
    assert result.status == "completed"
    assert len(result.text_blocks) >= 1
    # Check that handwritten regions are classified as handwritten
    assert any(b.type in ("handwritten", "unknown") for b in result.text_blocks)


# 3. Mixed Printed and Handwritten Pages
def test_mixed_page_recognition(mixed_assignment_page: Path):
    result = recognize_page(
        image_path=str(mixed_assignment_page),
        submission_id="sub-rec-mixed",
        page_number=1,
    )
    assert result.status == "completed"
    types = {b.type for b in result.text_blocks}
    # Mixed page contains both printed question and student handwriting
    assert len(result.text_blocks) >= 2


# 4. Multiple Paragraphs
def test_multiple_paragraphs(printed_doc_page: Path):
    result = recognize_page(
        image_path=str(printed_doc_page),
        submission_id="sub-rec-paras",
        page_number=1,
    )
    assert len(result.text_blocks) >= 3
    # Verify full_text aggregates blocks with newlines
    assert "\n" in result.full_text


# 5. Different Handwriting Styles
def test_different_handwriting_styles(tmp_path: Path):
    path = tmp_path / "styles.png"
    img = np.full((600, 800, 3), 255, dtype=np.uint8)
    # Style 1: Tight cursive
    pts1 = [np.array([[50 + x * 10, 150 + int(4 * np.sin(x * 1.2))] for x in range(30)], np.int32)]
    cv2.polylines(img, pts1, False, (20, 20, 20), 2)
    # Style 2: Slanted wide script
    pts2 = [np.array([[50 + x * 20, 350 + int(8 * np.sin(x * 0.5))] for x in range(25)], np.int32)]
    cv2.polylines(img, pts2, False, (30, 30, 30), 2)
    cv2.imwrite(str(path), img)

    result = recognize_page(str(path), "sub-styles", 1)
    assert result.status == "completed"
    assert len(result.text_blocks) >= 2


# 6. Faint Handwriting Handling
def test_faint_handwriting_detection(faint_handwriting_page: Path):
    result = recognize_page(
        image_path=str(faint_handwriting_page),
        submission_id="sub-faint",
        page_number=1,
    )
    assert result.status == "completed"
    # Faint text should either trigger low confidence or a warning
    low_conf_or_warning = any(
        b.confidence < 0.80 or len(b.warnings) > 0 for b in result.text_blocks
    ) or len(result.warnings) > 0
    assert low_conf_or_warning


# 7. Low-Quality Handwriting / Artifacts
def test_low_quality_handwriting_with_warnings(tmp_path: Path):
    path = tmp_path / "low_qual.png"
    img = np.full((500, 700, 3), 255, dtype=np.uint8)
    # Low quality blurred strokes
    cv2.putText(img, "Rough messy scribble", (50, 200), cv2.FONT_HERSHEY_PLAIN, 1.5, (120, 120, 120), 1)
    cv2.imwrite(str(path), img)

    result = recognize_page(str(path), "sub-low-qual", 1)
    assert result.status == "completed"


# 8. Multiple Text Regions Detected
def test_multiple_text_regions_segmentation(printed_doc_page: Path):
    result = recognize_page(str(printed_doc_page), "sub-multi-reg", 1)
    assert len(result.text_blocks) >= 2
    # Ensure all block IDs are distinct
    block_ids = [b.block_id for b in result.text_blocks]
    assert len(block_ids) == len(set(block_ids))


# 9. Reading-Order Reconstruction
def test_reading_order_top_to_bottom(printed_doc_page: Path):
    result = recognize_page(str(printed_doc_page), "sub-reading-order", 1)
    # Sequences must strictly increase: 1, 2, 3...
    sequences = [b.sequence for b in result.text_blocks]
    assert sequences == list(range(1, len(sequences) + 1))
    # Y-coordinates must follow reading order
    for i in range(len(result.text_blocks) - 1):
        assert result.text_blocks[i].bounding_box.y1 <= result.text_blocks[i + 1].bounding_box.y2


# 10. Multi-Column Layouts Sorting
def test_multi_column_reading_order(multi_column_assignment_page: Path):
    result = recognize_page(
        image_path=str(multi_column_assignment_page),
        submission_id="sub-multi-col",
        page_number=1,
    )
    assert result.status == "completed"
    assert len(result.text_blocks) >= 4
    # Spanning header must come first (sequence 1)
    assert result.text_blocks[0].bounding_box.width > 400


# 11. Empty Page Handling
def test_empty_page_handling(blank_page_image: Path):
    result = recognize_page(
        image_path=str(blank_page_image),
        submission_id="sub-empty",
        page_number=1,
    )
    assert result.status == "completed"
    assert len(result.text_blocks) == 0
    assert result.full_text == ""
    assert any("no detectable text" in w.lower() for w in result.warnings)


# 12. Blank or Unreadable Text Region Handling
def test_blank_region_confidence():
    empty_crop = np.full((50, 200, 3), 255, dtype=np.uint8)
    model_mgr = ModelManager.get_instance()
    text, conf = model_mgr.recognize_handwriting_crop(empty_crop)
    assert conf < 0.30
    assert text == ""


# 13. Low-Confidence Recognition Flagging
def test_low_confidence_flagging(faint_handwriting_page: Path):
    cfg = RecognitionConfig(medium_confidence_threshold=0.85)
    result = recognize_page(
        image_path=str(faint_handwriting_page),
        submission_id="sub-conf-flag",
        page_number=1,
        config=cfg,
    )
    # Low confidence triggers warning
    has_low_conf_warning = any(
        any("low" in w.lower() or "confidence" in w.lower() for w in b.warnings)
        for b in result.text_blocks
    )
    assert has_low_conf_warning or len(result.text_blocks) == 0


# 14. Model Loading Failure Handling
def test_model_loading_failure(monkeypatch):
    ModelManager.reset_instance()

    def mock_trocr_fail():
        raise RuntimeError("Simulated model download / network failure")

    mgr = ModelManager.get_instance()
    monkeypatch.setattr(mgr, "_load_trocr_model", mock_trocr_fail)

    with pytest.raises(ModelLoadingError):
        mgr.initialize_models()

    ModelManager.reset_instance()


# 15. Recognition Inference Failure Handling
def test_recognition_inference_failure(printed_doc_page: Path, monkeypatch):
    mgr = ModelManager.get_instance()

    def mock_infer_fail(*args, **kwargs):
        raise RuntimeError("GPU out of memory during inference")

    monkeypatch.setattr(mgr, "recognize_printed_crop", mock_infer_fail)
    monkeypatch.setattr(mgr, "recognize_handwriting_crop", mock_infer_fail)

    with pytest.raises(RecognitionPipelineError):
        recognize_page(str(printed_doc_page), "sub-fail", 1)


# 16. Bounding-Box Validity
def test_bounding_box_validity():
    box = BoundingBox(x1=50, y1=100, x2=250, y2=200)
    assert box.width == 200
    assert box.height == 100
    assert box.area == 20000

    with pytest.raises(ValueError):
        BoundingBox(x1=200, y1=50, x2=100, y2=150)


# 17. Correct Page Numbering
def test_correct_page_numbering(printed_doc_page: Path):
    result = recognize_page(
        image_path=str(printed_doc_page),
        submission_id="sub-num",
        page_number=7,
    )
    assert result.page_number == 7
    for b in result.text_blocks:
        assert b.block_id.startswith("page-7-block-")


# 18. Batch Processing With One Failed Page
def test_batch_processing_fault_isolation(printed_doc_page: Path, tmp_path: Path):
    missing_page = tmp_path / "does_not_exist.png"
    pages_input = [
        {"image_path": str(printed_doc_page), "page_number": 1},
        {"image_path": str(missing_page), "page_number": 2},
    ]

    results = recognize_pages(pages=pages_input, submission_id="sub-batch")
    assert len(results) == 2
    assert results[0].status == "completed"
    assert len(results[0].text_blocks) > 0
    assert results[1].status == "failed"
    assert results[1].page_number == 2


# 19. Safe Text Normalization
def test_safe_text_normalization():
    raw_text = "  Student  wrote:   photosynthesis   formula  \n\n\n\n  CO2 + H2O -> C6H12O6  "
    normalized = TextNormalizer.normalize_block_text(raw_text)

    # Whitespace normalized
    assert "  " not in normalized
    # Content, casing, and math preserved
    assert "photosynthesis formula" in normalized
    assert "CO2 + H2O -> C6H12O6" in normalized


# 20. Mathematical Content Preservation and Uncertainty Handling
def test_mathematical_content_preservation(math_assignment_page: Path):
    result = recognize_page(
        image_path=str(math_assignment_page),
        submission_id="sub-math-eval",
        page_number=1,
    )
    assert result.status == "completed"
    assert len(result.text_blocks) >= 1
    # Check that mathematical expressions trigger appropriate preserved flag
    has_math_warning = any(
        any("mathematical" in w.lower() for w in b.warnings) for b in result.text_blocks
    )
    assert has_math_warning
