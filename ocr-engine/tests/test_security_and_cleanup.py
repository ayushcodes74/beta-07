"""Tests for security, path traversal prevention, and failure cleanup."""

from pathlib import Path
import pytest
import pymupdf

from app.ingestion.exceptions import (
    PDFRenderingError,
    PathTraversalError,
)
from app.ingestion.pdf_processor import process_pdf


def test_cleanup_after_rendering_failure(sample_multi_page_pdf: Path, tmp_path: Path, monkeypatch):
    """Verify that if rendering fails halfway, already generated images are cleaned up and original PDF is preserved."""
    output_dir = tmp_path / "processed"
    submission_id = "fail-sub"

    original_pdf_bytes_before = sample_multi_page_pdf.read_bytes()

    # Monkeypatch get_pixmap to fail on page 2 (index 1)
    call_count = 0
    orig_get_pixmap = pymupdf.Page.get_pixmap

    def mock_get_pixmap(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Simulated rendering hardware/memory failure on page 2")
        return orig_get_pixmap(self, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", mock_get_pixmap)

    with pytest.raises(PDFRenderingError) as exc_info:
        process_pdf(
            pdf_path=str(sample_multi_page_pdf),
            submission_id=submission_id,
            output_dir=str(output_dir),
        )

    assert "page 2" in str(exc_info.value).lower()

    # Verify that partial files (page_001.png) were cleaned up
    submission_pages_dir = output_dir / submission_id / "pages"
    assert not (submission_pages_dir / "page_001.png").exists()
    assert not (submission_pages_dir / "page_002.png").exists()

    # Verify that the original PDF file was NOT deleted or altered
    assert sample_multi_page_pdf.exists()
    assert sample_multi_page_pdf.read_bytes() == original_pdf_bytes_before


@pytest.mark.parametrize(
    "malicious_id",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32",
        "sub/subdir",
        "sub\\subdir",
        "../../output",
    ],
)
def test_path_traversal_rejection_in_processor(sample_single_page_pdf: Path, tmp_path: Path, malicious_id: str):
    output_dir = tmp_path / "processed"
    with pytest.raises(PathTraversalError):
        process_pdf(
            pdf_path=str(sample_single_page_pdf),
            submission_id=malicious_id,
            output_dir=str(output_dir),
        )


def test_no_image_bytes_in_result_payload(sample_single_page_pdf: Path, tmp_path: Path):
    output_dir = tmp_path / "processed"
    result = process_pdf(
        pdf_path=str(sample_single_page_pdf),
        submission_id="check-bytes",
        output_dir=str(output_dir),
    )
    result_dict = result.model_dump()

    # Confirm no base64 string or binary bytes fields are returned in the record
    for page in result_dict["pages"]:
        assert "bytes" not in page
        assert "image_base64" not in page
        assert "data" not in page
        assert isinstance(page["image_path"], str)

