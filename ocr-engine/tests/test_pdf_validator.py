"""Tests for PDFValidator."""

from pathlib import Path
import pytest

from app.ingestion.config import IngestionConfig
from app.ingestion.exceptions import (
    CorruptedPDFError,
    EmptyPDFError,
    FileTooLargeError,
    InvalidPDFError,
    PageLimitExceededError,
    PasswordProtectedPDFError,
    PathTraversalError,
    ZeroPagesPDFError,
)
from app.ingestion.pdf_validator import PDFValidator


def test_validate_valid_single_page(sample_single_page_pdf: Path):
    validator = PDFValidator()
    doc = validator.validate_document_structure(sample_single_page_pdf)
    assert doc is not None
    assert doc.page_count == 1
    doc.close()


def test_validate_valid_multi_page(sample_multi_page_pdf: Path):
    validator = PDFValidator()
    doc = validator.validate_document_structure(sample_multi_page_pdf)
    assert doc is not None
    assert doc.page_count == 3
    doc.close()


def test_validate_empty_file(empty_pdf_file: Path):
    validator = PDFValidator()
    with pytest.raises(EmptyPDFError) as exc_info:
        validator.validate_file(empty_pdf_file)
    assert "empty" in str(exc_info.value).lower()


def test_validate_fake_renamed_pdf(fake_renamed_pdf: Path):
    validator = PDFValidator()
    with pytest.raises(InvalidPDFError) as exc_info:
        validator.validate_file(fake_renamed_pdf)
    assert "signature" in str(exc_info.value).lower()


def test_validate_nonexistent_file(tmp_path: Path):
    validator = PDFValidator()
    missing_file = tmp_path / "does_not_exist.pdf"
    with pytest.raises(InvalidPDFError) as exc_info:
        validator.validate_file(missing_file)
    assert "not found" in str(exc_info.value).lower()


def test_validate_corrupted_pdf(corrupted_pdf_file: Path):
    validator = PDFValidator()
    with pytest.raises(CorruptedPDFError) as exc_info:
        validator.validate_document_structure(corrupted_pdf_file)
    assert "corrupted" in str(exc_info.value).lower()


def test_validate_password_protected_pdf(password_protected_pdf: Path):
    validator = PDFValidator()
    with pytest.raises(PasswordProtectedPDFError) as exc_info:
        validator.validate_document_structure(password_protected_pdf)
    assert "password protected" in str(exc_info.value).lower()


def test_validate_zero_page_pdf(zero_page_pdf: Path):
    validator = PDFValidator()
    with pytest.raises(ZeroPagesPDFError) as exc_info:
        validator.validate_document_structure(zero_page_pdf)
    assert "zero pages" in str(exc_info.value).lower()


def test_validate_file_too_large(sample_single_page_pdf: Path):
    # Set limit to 10 bytes so the sample exceeds it
    custom_config = IngestionConfig(max_file_size_bytes=10)
    validator = PDFValidator(config=custom_config)
    with pytest.raises(FileTooLargeError) as exc_info:
        validator.validate_file(sample_single_page_pdf)
    assert "exceeds" in str(exc_info.value).lower()
    assert exc_info.value.details.get("file_size_bytes") is not None


def test_validate_page_limit_exceeded(sample_multi_page_pdf: Path):
    # Set max_pages to 2 when sample has 3
    custom_config = IngestionConfig(max_pages=2)
    validator = PDFValidator(config=custom_config)
    with pytest.raises(PageLimitExceededError) as exc_info:
        validator.validate_document_structure(sample_multi_page_pdf)
    assert "limit of 2 pages" in str(exc_info.value)
    assert exc_info.value.details.get("page_count") == 3


@pytest.mark.parametrize(
    "invalid_id",
    [
        "../traversal",
        "..\\traversal",
        "/etc/passwd",
        "sub/folder",
        "sub\\folder",
        "sub 123",
        "sub@123",
        "sub$123",
        "",
        "   ",
        "sub\0id",
    ],
)
def test_validate_submission_id_path_traversal(invalid_id: str):
    with pytest.raises(PathTraversalError):
        PDFValidator.validate_submission_id(invalid_id)


@pytest.mark.parametrize(
    "valid_id",
    [
        "submission-123",
        "submission_456",
        "SUB-789-abc",
        "12345",
        "student_sub_2026_01",
    ],
)
def test_validate_submission_id_valid(valid_id: str):
    assert PDFValidator.validate_submission_id(valid_id) == valid_id

