"""Tests for the PDF processing pipeline."""

from pathlib import Path
import pymupdf
import pytest

from app.ingestion.config import IngestionConfig
from app.ingestion.exceptions import (
    CorruptedPDFError,
    EmptyPDFError,
    FileTooLargeError,
    InvalidPDFError,
    PageLimitExceededError,
    PasswordProtectedPDFError,
    ZeroPagesPDFError,
)
from app.ingestion.pdf_processor import process_pdf
from app.ingestion.schemas import PDFProcessingResult


def test_process_valid_single_page(sample_single_page_pdf: Path, tmp_path: Path):
    output_dir = tmp_path / "processed"
    submission_id = "submission-001"

    result = process_pdf(
        pdf_path=str(sample_single_page_pdf),
        submission_id=submission_id,
        output_dir=str(output_dir),
    )

    assert isinstance(result, PDFProcessingResult)
    assert result.submission_id == submission_id
    assert result.status == "processed"
    assert result.total_pages == 1
    assert len(result.pages) == 1

    page = result.pages[0]
    assert page.page_number == 1
    assert page.image_path.endswith("page_001.png")
    assert page.width > 0
    assert page.height > 0
    assert page.original_width == 595.0
    assert page.original_height == 842.0
    assert page.rotation == 0

    # Verify image actually exists on disk
    expected_image_file = output_dir / submission_id / "pages" / "page_001.png"
    assert expected_image_file.exists()
    assert expected_image_file.stat().st_size > 0

    # Verify image is a valid PNG
    with open(expected_image_file, "rb") as f:
        png_header = f.read(8)
    assert png_header.startswith(b"\x89PNG\r\n\x1a\n")

    # Verify metadata
    assert result.metadata.title == "Assignment 1"
    assert result.metadata.author == "Student 101"


def test_process_valid_multi_page(sample_multi_page_pdf: Path, tmp_path: Path):
    output_dir = tmp_path / "processed"
    submission_id = "submission-002"

    result = process_pdf(
        pdf_path=str(sample_multi_page_pdf),
        submission_id=submission_id,
        output_dir=str(output_dir),
    )

    assert result.status == "processed"
    assert result.total_pages == 3
    assert len(result.pages) == 3

    for idx, page in enumerate(result.pages):
        expected_page_num = idx + 1
        assert page.page_number == expected_page_num
        expected_filename = f"page_{expected_page_num:03d}.png"
        assert page.image_path.endswith(expected_filename)

        img_file = output_dir / submission_id / "pages" / expected_filename
        assert img_file.exists()
        assert img_file.stat().st_size > 0


def test_process_rotated_pages(rotated_pages_pdf: Path, tmp_path: Path):
    output_dir = tmp_path / "processed"
    submission_id = "submission-rotated"

    result = process_pdf(
        pdf_path=str(rotated_pages_pdf),
        submission_id=submission_id,
        output_dir=str(output_dir),
    )

    assert result.total_pages == 4
    expected_rotations = [0, 90, 180, 270]
    for idx, page in enumerate(result.pages):
        assert page.rotation == expected_rotations[idx]
        assert (output_dir / submission_id / "pages" / f"page_{idx + 1:03d}.png").exists()


def test_process_multiple_submissions_no_collision(
    sample_single_page_pdf: Path, sample_multi_page_pdf: Path, tmp_path: Path
):
    output_dir = tmp_path / "processed"

    res1 = process_pdf(
        pdf_path=str(sample_single_page_pdf),
        submission_id="student-A",
        output_dir=str(output_dir),
    )
    res2 = process_pdf(
        pdf_path=str(sample_multi_page_pdf),
        submission_id="student-B",
        output_dir=str(output_dir),
    )

    # Submissions are in separate directories
    dir_a = output_dir / "student-A" / "pages"
    dir_b = output_dir / "student-B" / "pages"

    assert dir_a.exists()
    assert dir_b.exists()
    assert (dir_a / "page_001.png").exists()
    assert (dir_b / "page_001.png").exists()
    assert (dir_b / "page_002.png").exists()
    assert (dir_b / "page_003.png").exists()
    assert not (dir_a / "page_002.png").exists()

    assert res1.submission_id == "student-A"
    assert res2.submission_id == "student-B"


def test_process_custom_dpi(sample_single_page_pdf: Path, tmp_path: Path):
    output_dir = tmp_path / "processed"
    config_100_dpi = IngestionConfig(rendering_dpi=100)
    config_300_dpi = IngestionConfig(rendering_dpi=300)

    res_100 = process_pdf(
        pdf_path=str(sample_single_page_pdf),
        submission_id="sub-100",
        output_dir=str(output_dir),
        config=config_100_dpi,
    )
    res_300 = process_pdf(
        pdf_path=str(sample_single_page_pdf),
        submission_id="sub-300",
        output_dir=str(output_dir),
        config=config_300_dpi,
    )

    assert res_300.pages[0].width > res_100.pages[0].width
    assert res_300.pages[0].height > res_100.pages[0].height


def test_process_pdf_exception_propagations(
    empty_pdf_file: Path,
    fake_renamed_pdf: Path,
    corrupted_pdf_file: Path,
    password_protected_pdf: Path,
    zero_page_pdf: Path,
    sample_multi_page_pdf: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "processed"

    # 1. Empty file
    with pytest.raises(EmptyPDFError):
        process_pdf(str(empty_pdf_file), "sub-err-1", str(output_dir))

    # 2. Fake renamed file
    with pytest.raises(InvalidPDFError):
        process_pdf(str(fake_renamed_pdf), "sub-err-2", str(output_dir))

    # 3. Corrupted file
    with pytest.raises(CorruptedPDFError):
        process_pdf(str(corrupted_pdf_file), "sub-err-3", str(output_dir))

    # 4. Password protected
    with pytest.raises(PasswordProtectedPDFError):
        process_pdf(str(password_protected_pdf), "sub-err-4", str(output_dir))

    # 5. Zero page PDF
    with pytest.raises(ZeroPagesPDFError):
        process_pdf(str(zero_page_pdf), "sub-err-5", str(output_dir))

    # 6. Page limit exceeded
    tight_config = IngestionConfig(max_pages=1)
    with pytest.raises(PageLimitExceededError):
        process_pdf(str(sample_multi_page_pdf), "sub-err-6", str(output_dir), config=tight_config)

    # 7. File size exceeded
    small_size_config = IngestionConfig(max_file_size_bytes=50)
    with pytest.raises(FileTooLargeError):
        process_pdf(str(sample_multi_page_pdf), "sub-err-7", str(output_dir), config=small_size_config)


def test_contract_json_serialization(sample_single_page_pdf: Path, tmp_path: Path):
    output_dir = tmp_path / "processed"
    submission_id = "submission-123"

    result = process_pdf(
        pdf_path=str(sample_single_page_pdf),
        submission_id=submission_id,
        output_dir=str(output_dir),
    )

    data = result.model_dump()
    assert data["submission_id"] == "submission-123"
    assert data["status"] == "processed"
    assert data["total_pages"] == 1
    assert "pages" in data
    assert len(data["pages"]) == 1
    first_page = data["pages"][0]
    assert "page_number" in first_page
    assert "image_path" in first_page
    assert "width" in first_page
    assert "height" in first_page
    assert "original_width" in first_page
    assert "original_height" in first_page
    assert "rotation" in first_page
    assert "metadata" in data
    assert "title" in data["metadata"]
    assert "author" in data["metadata"]
