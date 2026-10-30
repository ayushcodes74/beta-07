"""Comprehensive tests for Image Preprocessing Module 2."""

from pathlib import Path
import cv2
import numpy as np
import pytest

from app.preprocessing.config import PreprocessingConfig
from app.preprocessing.exceptions import (
    InvalidImageError,
    UnsupportedImageFormatError,
)
from app.preprocessing.pipeline import preprocess_page, preprocess_pages
from app.preprocessing.schemas import PreprocessingResult


# 1. Valid PNG Image
def test_valid_png_preprocessing(valid_png_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(valid_png_page),
        submission_id="sub-valid-png",
        page_number=1,
        output_dir=str(out_dir),
    )
    assert isinstance(result, PreprocessingResult)
    assert result.status == "completed"
    assert result.page_number == 1
    assert result.submission_id == "sub-valid-png"
    assert (out_dir / "sub-valid-png" / "enhanced" / "page_001.png").exists()


# 2. Valid JPEG Image
def test_valid_jpeg_preprocessing(valid_jpeg_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(valid_jpeg_page),
        submission_id="sub-valid-jpg",
        page_number=1,
        output_dir=str(out_dir),
    )
    assert result.status == "completed"
    assert (out_dir / "sub-valid-jpg" / "enhanced" / "page_001.png").exists()


# 3. Corrupted Image
def test_corrupted_image_raises_error(corrupted_image_file: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    with pytest.raises(InvalidImageError) as exc_info:
        preprocess_page(
            image_path=str(corrupted_image_file),
            submission_id="sub-corrupt",
            page_number=1,
            output_dir=str(out_dir),
        )
    assert exc_info.value.page_number == 1


# 4. Unsupported Image Format (e.g. BMP)
def test_unsupported_image_format(unsupported_format_image: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    with pytest.raises(UnsupportedImageFormatError):
        preprocess_page(
            image_path=str(unsupported_format_image),
            submission_id="sub-unsupported",
            page_number=1,
            output_dir=str(out_dir),
        )


# 5. Very Small Image
def test_very_small_image_rejected(very_small_image: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    with pytest.raises(InvalidImageError) as exc_info:
        preprocess_page(
            image_path=str(very_small_image),
            submission_id="sub-tiny",
            page_number=1,
            output_dir=str(out_dir),
        )
    assert "small" in str(exc_info.value).lower()


# 6. Rotated Page
def test_rotated_page_orientation_correction(rotated_page_image: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    # Pass known_rotation=90 (such as extracted by Module 1)
    result = preprocess_page(
        image_path=str(rotated_page_image),
        submission_id="sub-rotated",
        page_number=1,
        output_dir=str(out_dir),
        known_rotation=90,
    )
    assert result.image_quality.orientation_corrected is True
    # Initial was landscape (width 1200 > height 900). After 90 deg rotation, it is portrait (height > width)
    assert result.image_quality.height > result.image_quality.width


# 7. Slightly Skewed Page
def test_deskewing_slightly_skewed_page(skewed_page_image: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(skewed_page_image),
        submission_id="sub-skewed",
        page_number=1,
        output_dir=str(out_dir),
    )
    # The image was syntactically rotated by 3.5 degrees
    assert abs(result.image_quality.estimated_skew_angle) > 1.0
    assert abs(result.image_quality.corrected_skew_angle) > 1.0


# 8. Noisy Scanned Page Denoising
def test_noisy_page_enhancement(noisy_page_image: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(noisy_page_image),
        submission_id="sub-noisy",
        page_number=1,
        output_dir=str(out_dir),
    )
    enhanced_file = out_dir / "sub-noisy" / "enhanced" / "page_001.png"
    assert enhanced_file.exists()
    enhanced_img = cv2.imread(str(enhanced_file))
    # Denoised image should not be empty
    assert enhanced_img is not None
    assert enhanced_img.shape[:2] == (1000, 800)


# 9. Low-Contrast Page Enhancement
def test_low_contrast_enhancement(low_contrast_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(low_contrast_page),
        submission_id="sub-contrast",
        page_number=1,
        output_dir=str(out_dir),
    )
    assert result.status == "completed"
    enhanced_file = out_dir / "sub-contrast" / "enhanced" / "page_001.png"
    assert enhanced_file.exists()


# 10. Uneven Illumination / Shadow Correction
def test_uneven_illumination_correction(uneven_illumination_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(uneven_illumination_page),
        submission_id="sub-shadow",
        page_number=1,
        output_dir=str(out_dir),
    )
    assert result.status == "completed"
    assert (out_dir / "sub-shadow" / "enhanced" / "page_001.png").exists()


# 11. Blank Page Detection
def test_blank_page_detection(blank_page_image: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(blank_page_image),
        submission_id="sub-blank",
        page_number=1,
        output_dir=str(out_dir),
    )
    assert result.image_quality.is_blank is True
    assert result.image_quality.needs_review is True
    assert any("blank" in w.lower() for w in result.image_quality.warnings)


# 12. Handwritten-like Thin Strokes Preservation
def test_thin_strokes_preservation(thin_strokes_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(thin_strokes_page),
        submission_id="sub-thin",
        page_number=1,
        output_dir=str(out_dir),
    )
    enhanced_path = out_dir / "sub-thin" / "enhanced" / "page_001.png"
    enhanced = cv2.imread(str(enhanced_path), cv2.IMREAD_GRAYSCALE)
    # The 1-pixel thin lines must remain distinct dark pixels (< 100)
    dark_pixels = np.sum(enhanced < 100)
    assert dark_pixels > 1000  # thin lines are preserved, not erased


# 13. Mathematical Symbols and Fine Details Preservation
def test_math_symbols_preservation(math_symbols_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(math_symbols_page),
        submission_id="sub-math",
        page_number=1,
        output_dir=str(out_dir),
    )
    enhanced_path = out_dir / "sub-math" / "enhanced" / "page_001.png"
    enhanced = cv2.imread(str(enhanced_path), cv2.IMREAD_GRAYSCALE)
    # Confirm decimal point region around (200, 350) has dark ink pixels
    crop = enhanced[345:355, 195:205]
    assert np.min(crop) < 80  # decimal point is clearly preserved


# 14. Successful Grayscale Output Variant
def test_grayscale_variant_generated(valid_png_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(valid_png_page),
        submission_id="sub-gray",
        page_number=1,
        output_dir=str(out_dir),
    )
    assert result.variants.grayscale is not None
    gray_file = out_dir / "sub-gray" / "variants" / "page_001_gray.png"
    assert gray_file.exists()
    img = cv2.imread(str(gray_file), cv2.IMREAD_UNCHANGED)
    assert len(img.shape) == 2 or img.shape[2] == 1


# 15. Successful Thresholded Output Variant
def test_thresholded_variant_generated(valid_png_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    result = preprocess_page(
        image_path=str(valid_png_page),
        submission_id="sub-thresh",
        page_number=1,
        output_dir=str(out_dir),
    )
    assert result.variants.thresholded is not None
    thresh_file = out_dir / "sub-thresh" / "variants" / "page_001_threshold.png"
    assert thresh_file.exists()
    img = cv2.imread(str(thresh_file), cv2.IMREAD_UNCHANGED)
    # Pure binary values: only 0 and 255
    unique_vals = set(np.unique(img))
    assert unique_vals.issubset({0, 255})


# 16. Original Image Remains Unchanged
def test_original_image_unaltered(valid_png_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    orig_bytes_before = valid_png_page.read_bytes()

    preprocess_page(
        image_path=str(valid_png_page),
        submission_id="sub-preserve",
        page_number=1,
        output_dir=str(out_dir),
    )

    orig_bytes_after = valid_png_page.read_bytes()
    assert orig_bytes_before == orig_bytes_after


# 17. Correct Page Numbering in Batch Processing
def test_batch_preprocessing_page_numbering(valid_png_page: Path, valid_jpeg_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"
    batch_input = [
        {"image_path": str(valid_png_page), "page_number": 1},
        {"image_path": str(valid_jpeg_page), "page_number": 2},
    ]

    results = preprocess_pages(
        page_images=batch_input,
        submission_id="sub-batch",
        output_dir=str(out_dir),
    )

    assert len(results) == 2
    assert results[0].page_number == 1
    assert results[0].enhanced_image_path.endswith("page_001.png")
    assert results[1].page_number == 2
    assert results[1].enhanced_image_path.endswith("page_002.png")


# 18. One Failed Page Does Not Corrupt Other Pages
def test_one_failed_page_isolation(valid_png_page: Path, corrupted_image_file: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"

    # Process page 1 (valid)
    res1 = preprocess_page(str(valid_png_page), "sub-isolation", 1, str(out_dir))
    assert res1.status == "completed"

    # Attempt page 2 (corrupted) -> raises error
    with pytest.raises(InvalidImageError):
        preprocess_page(str(corrupted_image_file), "sub-isolation", 2, str(out_dir))

    # Page 1 must still exist completely intact on disk
    assert (out_dir / "sub-isolation" / "enhanced" / "page_001.png").exists()
    assert not (out_dir / "sub-isolation" / "enhanced" / "page_002.png").exists()


# 19. Output Paths Do Not Collide Between Submissions
def test_submission_isolation_no_collisions(valid_png_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"

    res_a = preprocess_page(str(valid_png_page), "sub-AAA", 1, str(out_dir))
    res_b = preprocess_page(str(valid_png_page), "sub-BBB", 1, str(out_dir))

    path_a = out_dir / "sub-AAA" / "enhanced" / "page_001.png"
    path_b = out_dir / "sub-BBB" / "enhanced" / "page_001.png"

    assert path_a.exists()
    assert path_b.exists()
    assert path_a != path_b


# 20. Configuration Changes Affect Processing Pipeline
def test_configuration_overrides(valid_png_page: Path, tmp_path: Path):
    out_dir = tmp_path / "processed"

    # Config with variants disabled
    cfg_no_variants = PreprocessingConfig(
        generate_grayscale=False,
        generate_thresholded=False,
        enable_denoising=False,
        enable_contrast_enhancement=False,
    )

    result = preprocess_page(
        image_path=str(valid_png_page),
        submission_id="sub-custom-cfg",
        page_number=1,
        output_dir=str(out_dir),
        config=cfg_no_variants,
    )

    assert result.variants.grayscale is None
    assert result.variants.thresholded is None
    assert not (out_dir / "sub-custom-cfg" / "variants" / "page_001_gray.png").exists()
