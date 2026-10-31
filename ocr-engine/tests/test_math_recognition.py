"""Comprehensive test suite for Mathematical Recognition & Quality Analysis Module 4.

Covers all 20 required verification criteria:
1. Image crop validation.
2. Bounding-box validation.
3. Empty mathematical regions.
4. Invalid mathematical image inputs.
5. Model unavailable behavior.
6. Model loading failure.
7. Inference failure.
8. Printed equation recognition (mocked genuine inference).
9. Handwritten equation recognition (mocked genuine inference).
10. Fraction recognition and decomposition.
11. Superscript and subscript preservation.
12. Square root / radical recognition.
13. Mathematical symbol handling.
14. LaTeX output validation and delimiter checking.
15. Low-quality image detection (blur, faintness, cropped boundaries).
16. Ambiguous mathematical symbols auditing.
17. Manual review flags.
18. Multi-region processing.
19. Error isolation across regions.
20. Module 3 compatibility.
"""

from pathlib import Path
from unittest.mock import MagicMock
import cv2
import numpy as np
import pytest

from app.math_recognition.config import MathRecognitionConfig
from app.math_recognition.exceptions import (
    MathImageError,
    MathInferenceError,
    MathModelLoadingError,
    MathRegionValidationError,
)
from app.math_recognition.image_processor import MathImageProcessor
from app.math_recognition.latex_converter import LaTeXConverter
from app.math_recognition.model_manager import MathModelManager
from app.math_recognition.quality_analyzer import MathQualityAnalyzer
from app.math_recognition.recognition_pipeline import (
    MathRecognitionPipeline,
    process_math_batch,
    process_math_page,
    process_math_region,
)
from app.math_recognition.region_validator import MathRegionValidator
from app.math_recognition.schemas import (
    BoundingBox,
    MathQualityAssessment,
    MathRegionResult,
    PageMathRecognitionResult,
)
from app.math_recognition.structure_analyzer import MathStructureAnalyzer
from app.math_recognition.symbol_analyzer import MathSymbolAnalyzer


# ------------------------------------------------------------------------------
# 1. Image Crop Validation
# ------------------------------------------------------------------------------
def test_image_crop_validation(tmp_path: Path):
    img = np.full((100, 300, 3), 255, dtype=np.uint8)
    cv2.putText(img, "x + y = 10", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    path = tmp_path / "crop.png"
    cv2.imwrite(str(path), img)

    loaded = MathImageProcessor.load_crop(str(path))
    assert loaded.shape == (100, 300, 3)

    pil_img = MathImageProcessor.to_rgb_pil(loaded)
    assert pil_img.size == (300, 100)

    padded = MathImageProcessor.pad_crop(loaded, padding=10)
    assert padded.shape == (120, 320, 3)


# ------------------------------------------------------------------------------
# 2. Bounding-Box Validation
# ------------------------------------------------------------------------------
def test_bounding_box_validation():
    validator = MathRegionValidator()

    # Valid box
    box = BoundingBox(x1=50, y1=50, x2=250, y2=150)
    assert box.width == 200
    assert box.height == 100
    is_valid, msg = validator.validate_region(box, page_width=1000, page_height=1000)
    assert is_valid
    assert msg is None

    # Invalid box: x2 <= x1
    with pytest.raises(ValueError):
        BoundingBox(x1=200, y1=50, x2=100, y2=150)

    # Box below minimum limits
    tiny_box = BoundingBox(x1=10, y1=10, x2=20, y2=15)  # w=10 < 15
    is_valid, msg = validator.validate_region(tiny_box)
    assert not is_valid
    assert "minimum threshold" in msg

    # Box exceeds page bounds
    exceed_box = BoundingBox(x1=100, y1=100, x2=1200, y2=300)
    is_valid, msg = validator.validate_region(exceed_box, page_width=1000, page_height=800)
    assert not is_valid
    assert "extends beyond page width" in msg


# ------------------------------------------------------------------------------
# 3. Empty Mathematical Regions
# ------------------------------------------------------------------------------
def test_empty_mathematical_regions():
    blank = np.full((100, 200, 3), 255, dtype=np.uint8)
    assert MathImageProcessor.is_blank_crop(blank)

    box = BoundingBox(x1=10, y1=10, x2=210, y2=110)
    result = process_math_region(blank, "reg-blank", "1", box)

    assert result.recognition_status == "unreadable"
    assert result.latex == ""
    assert result.confidence is None
    assert result.is_readable is False


# ------------------------------------------------------------------------------
# 4. Invalid Mathematical Image Inputs
# ------------------------------------------------------------------------------
def test_invalid_mathematical_image_inputs(tmp_path: Path):
    missing_path = tmp_path / "does_not_exist.png"
    with pytest.raises(MathImageError):
        MathImageProcessor.load_crop(missing_path)

    empty_array = np.array([])
    with pytest.raises(MathImageError):
        MathImageProcessor.load_crop(empty_array)

    with pytest.raises(MathImageError):
        MathImageProcessor.load_crop(12345)  # type: ignore


# ------------------------------------------------------------------------------
# 5. Model Unavailable Behavior (Honest Fallback, No Fake Math)
# ------------------------------------------------------------------------------
def test_model_unavailable_behavior():
    MathModelManager.reset_instance()
    mgr = MathModelManager.get_instance()
    mgr.initialize_models()

    if mgr.math_model is None:
        img = np.full((100, 300, 3), 255, dtype=np.uint8)
        cv2.putText(img, "y = mx + c", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
        box = BoundingBox(x1=0, y1=0, x2=300, y2=100)

        result = process_math_region(img, "reg-fallback", "1", box)
        assert result.engine_used == "none"
        assert result.metadata["is_fallback"] is True
        assert result.confidence is None
        assert result.recognition_status == "unavailable"
        # Zero fake formulas emitted!
        assert result.latex == ""


# ------------------------------------------------------------------------------
# 6. Model Loading Failure When Fallback Disabled
# ------------------------------------------------------------------------------
def test_model_loading_failure_when_fallback_disabled(monkeypatch):
    MathModelManager.reset_instance()
    cfg = MathRecognitionConfig(allow_degraded_fallback=False)

    def mock_pix2tex_fail():
        raise RuntimeError("Simulated network/model download failure")

    mgr = MathModelManager.get_instance(cfg)
    monkeypatch.setattr(mgr, "_load_pix2tex_model", mock_pix2tex_fail)

    with pytest.raises(MathModelLoadingError):
        mgr.initialize_models()

    MathModelManager.reset_instance()


# ------------------------------------------------------------------------------
# 7. Inference Failure Handling
# ------------------------------------------------------------------------------
def test_inference_failure_handling(monkeypatch):
    MathModelManager.reset_instance()
    mgr = MathModelManager.get_instance()
    mgr._initialized = True

    def mock_infer_crash(*args, **kwargs):
        raise RuntimeError("GPU out of memory during mathematical inference")

    monkeypatch.setattr(mgr, "recognize_math_crop", mock_infer_crash)

    img = np.full((100, 300, 3), 255, dtype=np.uint8)
    cv2.putText(img, "x + y = 10", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    box = BoundingBox(x1=0, y1=0, x2=300, y2=100)

    with pytest.raises(MathInferenceError):
        pipeline = MathRecognitionPipeline()
        pipeline.process_region(img, "reg-crash", "1", box)

    MathModelManager.reset_instance()


# ------------------------------------------------------------------------------
# 8. Printed Equation Recognition (Calibrated Mock)
# ------------------------------------------------------------------------------
def test_printed_equation_recognition_mocked(monkeypatch):
    MathModelManager.reset_instance()
    mgr = MathModelManager.get_instance()

    mock_latex_model = MagicMock(return_value="x^{2} - 4 = 0")
    mgr.math_model = mock_latex_model
    mgr.model_status = "loaded"
    mgr.model_version = "lukas-blecher/LaTeX-OCR"
    mgr._initialized = True

    img = np.full((100, 350, 3), 255, dtype=np.uint8)
    cv2.putText(img, "x^2 - 4 = 0", (30, 60), cv2.FONT_HERSHEY_TRIPLEX, 1.0, (20, 20, 20), 2)
    box = BoundingBox(x1=0, y1=0, x2=350, y2=100)

    result = process_math_region(img, "reg-print-mock", "1", box)

    assert result.latex == "x^{2} - 4 = 0"
    assert result.recognition_status == "completed"
    assert result.engine_used in ("pix2tex", "auto")
    assert result.confidence is not None

    MathModelManager.reset_instance()


# ------------------------------------------------------------------------------
# 9. Handwritten Equation Recognition (Calibrated Mock)
# ------------------------------------------------------------------------------
def test_handwritten_equation_recognition_mocked(monkeypatch):
    MathModelManager.reset_instance()
    mgr = MathModelManager.get_instance()

    mock_latex_model = MagicMock(return_value="E = mc^{2}")
    mgr.math_model = mock_latex_model
    mgr.model_status = "loaded"
    mgr.model_version = "lukas-blecher/LaTeX-OCR"
    mgr._initialized = True

    img = np.full((100, 350, 3), 255, dtype=np.uint8)
    cv2.putText(img, "E = mc^2", (30, 60), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 1.0, (25, 25, 25), 2)
    box = BoundingBox(x1=0, y1=0, x2=350, y2=100)

    result = process_math_region(img, "reg-hw-mock", "1", box)

    assert result.latex == "E = mc^{2}"
    assert result.recognition_status == "completed"

    MathModelManager.reset_instance()


# ------------------------------------------------------------------------------
# 10. Fraction Recognition and Decomposition
# ------------------------------------------------------------------------------
def test_fraction_recognition_and_decomposition():
    expr = "\\frac{a + b}{c}"
    structures = MathStructureAnalyzer.analyze_structures(expr)
    fractions = [s for s in structures if s.structure_type == "fraction"]
    assert len(fractions) == 1
    assert fractions[0].components["numerator"] == "a + b"
    assert fractions[0].components["denominator"] == "c"

    # Test conversion from ASCII (x+1)/2 -> \frac{x+1}{2}
    converted, _ = LaTeXConverter.convert_to_latex("(x + 1) / 2")
    assert converted == "\\frac{x + 1}{2}"


# ------------------------------------------------------------------------------
# 11. Superscript and Subscript Preservation
# ------------------------------------------------------------------------------
def test_superscript_and_subscript_preservation():
    expr = "x^{2} + y_{1} = 10"
    structures = MathStructureAnalyzer.analyze_structures(expr)

    supers = [s for s in structures if s.structure_type == "superscript"]
    assert len(supers) >= 1
    assert supers[0].components["base"] == "x"
    assert supers[0].components["exponent"] == "2"

    subs = [s for s in structures if s.structure_type == "subscript"]
    assert len(subs) >= 1
    assert subs[0].components["base"] == "y"
    assert subs[0].components["subscript"] == "1"

    # Unicode conversion
    conv, _ = LaTeXConverter.convert_to_latex("x² + x₁ = 0")
    assert conv == "x^{2} + x_{1} = 0"


# ------------------------------------------------------------------------------
# 12. Square Root / Radical Recognition
# ------------------------------------------------------------------------------
def test_square_root_and_radical_recognition():
    expr = "\\sqrt{x + 1} = 4"
    structures = MathStructureAnalyzer.analyze_structures(expr)
    radicals = [s for s in structures if s.structure_type == "radical"]
    assert len(radicals) == 1
    assert radicals[0].components["radicand"] == "x + 1"
    assert radicals[0].components["degree"] == "2"

    # Conversion from sqrt(2x + 3)
    conv, _ = LaTeXConverter.convert_to_latex("sqrt(2x + 3)")
    assert conv == "\\sqrt{2x + 3}"


# ------------------------------------------------------------------------------
# 13. Mathematical Symbol Handling
# ------------------------------------------------------------------------------
def test_mathematical_symbol_handling():
    expr = "\\int \\pi r^{2} dr = \\sum_{i=1}^{n} \\lambda"
    symbols, warnings = MathSymbolAnalyzer.analyze_symbols(expr)

    sym_names = {s.symbol for s in symbols}
    assert "\\int" in sym_names
    assert "\\pi" in sym_names
    assert "\\sum" in sym_names
    assert "\\lambda" in sym_names

    categories = {s.symbol: s.category for s in symbols}
    assert categories["\\int"] == "calculus"
    assert categories["\\pi"] == "greek"
    assert categories["\\sum"] == "calculus"


# ------------------------------------------------------------------------------
# 14. LaTeX Output Validation and Delimiter Checking
# ------------------------------------------------------------------------------
def test_latex_output_and_syntax_validation():
    # Valid expression
    valid_latex = "\\frac{x + 1}{x - 1} = \\sqrt{2}"
    is_valid, err = LaTeXConverter.validate_delimiters(valid_latex)
    assert is_valid
    assert err is None

    # Unbalanced delimiter
    broken_latex = "\\frac{x + 1{x - 1}"  # missing closing brace
    is_valid, err = LaTeXConverter.validate_delimiters(broken_latex)
    assert not is_valid
    assert "Unclosed delimiter" in err or "Unexpected" in err


# ------------------------------------------------------------------------------
# 15. Low-Quality Image Detection (Faint, Blur, Cropped Boundaries)
# ------------------------------------------------------------------------------
def test_low_quality_image_detection():
    analyzer = MathQualityAnalyzer()

    # 1. Faint Image
    faint_img = np.full((100, 300, 3), 245, dtype=np.uint8)
    cv2.putText(faint_img, "x + y = 2", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (230, 230, 230), 1)
    faint_assessment = analyzer.analyze_crop(faint_img)
    assert faint_assessment.is_faint is True
    assert faint_assessment.quality_score < 0.60
    assert any("faint" in w.lower() for w in faint_assessment.warnings)

    # 2. Cropped at Boundary
    cropped_img = np.full((80, 200, 3), 255, dtype=np.uint8)
    # Draw stroke touching top border (y=0)
    cv2.line(cropped_img, (0, 0), (199, 0), (20, 20, 20), 2)
    crop_assessment = analyzer.analyze_crop(cropped_img)
    assert crop_assessment.is_cropped is True
    assert crop_assessment.is_complete is False
    assert any("touches crop boundaries" in w.lower() for w in crop_assessment.warnings)


# ------------------------------------------------------------------------------
# 16. Ambiguous Mathematical Symbols Auditing
# ------------------------------------------------------------------------------
def test_ambiguous_mathematical_symbols_auditing():
    # '0' vs 'O', '1' vs 'l', 'x' vs '\times'
    expr = "10 + x = l"
    symbols, warnings = MathSymbolAnalyzer.analyze_symbols(expr)

    ambig_symbols = [s for s in symbols if s.is_ambiguous]
    assert len(ambig_symbols) >= 2
    assert any("O (uppercase O)" in alt for s in ambig_symbols for alt in s.suggested_alternatives)
    assert any("Verify whether student intended" in w for w in warnings)


# ------------------------------------------------------------------------------
# 17. Manual Review Flags
# ------------------------------------------------------------------------------
def test_manual_review_flags():
    # Region with faint text should trigger requires_manual_review
    faint_img = np.full((80, 250, 3), 245, dtype=np.uint8)
    cv2.putText(faint_img, "a + b = c", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 1)
    box = BoundingBox(x1=10, y1=10, x2=260, y2=90)

    result = process_math_region(faint_img, "reg-review-check", "1", box)
    assert result.requires_manual_review is True
    assert result.is_readable is False


# ------------------------------------------------------------------------------
# 18. Multi-Region Processing
# ------------------------------------------------------------------------------
def test_multi_region_processing(tmp_path: Path):
    page_img = np.full((800, 600, 3), 255, dtype=np.uint8)
    # Region 1
    cv2.putText(page_img, "f(x) = 2x + 1", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    # Region 2
    cv2.putText(page_img, "g(x) = x^2 - 4", (50, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    path = tmp_path / "page_multi.png"
    cv2.imwrite(str(path), page_img)

    explicit_regs = [
        {"region_id": "math-1", "bounding_box": BoundingBox(x1=40, y1=100, x2=400, y2=200)},
        {"region_id": "math-2", "bounding_box": BoundingBox(x1=40, y1=300, x2=400, y2=400)},
    ]

    pipeline = MathRecognitionPipeline()
    res: PageMathRecognitionResult = pipeline.process_page(
        image_input=str(path),
        submission_id="sub-multi",
        page_number=1,
        explicit_regions=explicit_regs,
    )

    assert len(res.math_regions) == 2
    assert res.math_regions[0].region_id == "math-1"
    assert res.math_regions[1].region_id == "math-2"


# ------------------------------------------------------------------------------
# 19. Error Isolation Across Regions
# ------------------------------------------------------------------------------
def test_error_isolation_between_regions(tmp_path: Path, monkeypatch):
    page_img = np.full((800, 600, 3), 255, dtype=np.uint8)
    cv2.putText(page_img, "x + 1 = 2", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    cv2.putText(page_img, "y + 2 = 4", (50, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    path = tmp_path / "page_isolation.png"
    cv2.imwrite(str(path), page_img)

    pipeline = MathRecognitionPipeline()

    original_process_region = pipeline.process_region

    def mock_flaky_region(crop, region_id, page_id, bounding_box, **kwargs):
        if region_id == "math-broken":
            raise RuntimeError("Fatal memory crash during region 1 parsing")
        return original_process_region(crop, region_id, page_id, bounding_box, **kwargs)

    monkeypatch.setattr(pipeline, "process_region", mock_flaky_region)

    explicit_regs = [
        {"region_id": "math-broken", "bounding_box": BoundingBox(x1=40, y1=100, x2=400, y2=200)},
        {"region_id": "math-working", "bounding_box": BoundingBox(x1=40, y1=300, x2=400, y2=400)},
    ]

    res = pipeline.process_page(str(path), "sub-iso", 1, explicit_regions=explicit_regs)

    assert len(res.math_regions) == 2
    # Broken region isolated with status="failed"
    assert res.math_regions[0].region_id == "math-broken"
    assert res.math_regions[0].recognition_status == "failed"
    assert "Fatal memory crash" in res.math_regions[0].warnings[0]

    # Working region succeeded unharmed!
    assert res.math_regions[1].region_id == "math-working"
    assert res.math_regions[1].recognition_status in ("completed", "unavailable")


# ------------------------------------------------------------------------------
# 20. Module 3 Compatibility
# ------------------------------------------------------------------------------
def test_module_3_compatibility(tmp_path: Path):
    # Create page image with math equations
    page_img = np.full((800, 600, 3), 255, dtype=np.uint8)
    cv2.putText(page_img, "f(x) = x^2 + 3.1415", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    path = tmp_path / "page_m3.png"
    cv2.imwrite(str(path), page_img)

    # Mock Module 3 PageRecognitionResult
    mock_m3_block = MagicMock()
    mock_m3_block.block_id = "page-1-block-2"
    mock_m3_block.bounding_box = BoundingBox(x1=40, y1=160, x2=450, y2=250)
    mock_m3_block.warnings = ["Mathematical notation detected; bounding box preserved for specialized Module 4 processing."]
    mock_m3_block.text = "f(x) = x^2 + 3.1415"

    mock_m3_result = MagicMock()
    mock_m3_result.submission_id = "sub-m3-compat"
    mock_m3_result.page_number = 1
    mock_m3_result.text_blocks = [mock_m3_block]

    # Process page through Module 4 pipeline
    pipeline = MathRecognitionPipeline()
    page_math_res = pipeline.process_page(
        image_input=str(path),
        submission_id="sub-m3-compat",
        page_number=1,
        page_recognition_result=mock_m3_result,
    )

    assert len(page_math_res.math_regions) == 1
    m_reg = page_math_res.math_regions[0]
    assert m_reg.region_id == "math-page-1-block-2"
    assert m_reg.bounding_box.width == 410
    assert m_reg.bounding_box.height == 90
    assert m_reg.quality_score > 0.70
    assert m_reg.is_readable is True
