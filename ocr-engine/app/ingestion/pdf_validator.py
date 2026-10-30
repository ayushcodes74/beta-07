"""PDF and file validation service for the ingestion module."""

import os
import re
from pathlib import Path
from typing import Optional

import pymupdf

from app.ingestion.config import IngestionConfig, DEFAULT_CONFIG
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

# Standard PDF header magic bytes
PDF_MAGIC_HEADER = b"%PDF-"
# Safe submission_id pattern: alphanumeric, hyphen, underscore
SAFE_SUBMISSION_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


class PDFValidator:
    """Validator for PDF files and ingestion parameters.

    Ensures that input files are safe, valid PDFs within configured
    operational boundaries before further processing.
    """

    def __init__(self, config: Optional[IngestionConfig] = None) -> None:
        self.config = config or DEFAULT_CONFIG

    @staticmethod
    def validate_submission_id(submission_id: str) -> str:
        """Validate submission identifier to prevent path traversal and shell injection.

        Args:
            submission_id: Identifier string to validate.

        Returns:
            The validated submission_id string.

        Raises:
            PathTraversalError: If submission_id contains invalid characters or path traversal components.
        """
        if not submission_id or not isinstance(submission_id, str):
            raise PathTraversalError("submission_id must be a non-empty string.")

        clean_id = submission_id.strip()
        if ".." in clean_id or "/" in clean_id or "\\" in clean_id or "\0" in clean_id:
            raise PathTraversalError(f"Potential path traversal in submission_id: '{submission_id}'")

        if not SAFE_SUBMISSION_ID_REGEX.match(clean_id):
            raise PathTraversalError(
                f"Invalid submission_id '{submission_id}'. Must contain only alphanumeric characters, "
                "hyphens, and underscores."
            )

        return clean_id

    def validate_file(self, file_path: str | Path) -> Path:
        """Validate that the file exists, is non-empty, within size limits, and has valid PDF header.

        Args:
            file_path: Path to the target PDF file.

        Returns:
            Resolved Path object.

        Raises:
            InvalidPDFError: If file does not exist, is a directory, or lacks PDF signature.
            EmptyPDFError: If file is 0 bytes.
            FileTooLargeError: If file exceeds maximum allowed file size.
        """
        path = Path(file_path).resolve()

        if not path.exists():
            raise InvalidPDFError(f"File not found: '{file_path}'")

        if not path.is_file():
            raise InvalidPDFError(f"Path is not a regular file: '{file_path}'")

        file_size = path.stat().st_size
        if file_size == 0:
            raise EmptyPDFError(f"PDF file is empty (0 bytes): '{file_path}'")

        if file_size > self.config.max_file_size_bytes:
            raise FileTooLargeError(
                f"File size {file_size} bytes exceeds maximum allowed limit of "
                f"{self.config.max_file_size_bytes} bytes ({self.config.max_file_size_bytes / (1024 * 1024):.1f} MB)",
                file_size_bytes=file_size,
                max_size_bytes=self.config.max_file_size_bytes,
            )

        # Inspect content header (never trust extension alone)
        try:
            with open(path, "rb") as f:
                header = f.read(1024)
        except OSError as e:
            raise InvalidPDFError(f"Could not read file header: {e}") from e

        if PDF_MAGIC_HEADER not in header:
            raise InvalidPDFError(
                f"File '{file_path}' does not contain a valid PDF signature header ({PDF_MAGIC_HEADER.decode()})."
            )

        return path

    def validate_document_structure(self, file_path: str | Path) -> pymupdf.Document:
        """Open and validate internal structure of PDF document using PyMuPDF.

        Verifies that the document can be parsed, is not password protected,
        contains at least 1 page, and does not exceed maximum page limits.

        Note: The caller is responsible for closing the returned pymupdf.Document
        when done with it.

        Args:
            file_path: Path to the PDF file.

        Returns:
            Open, validated pymupdf.Document instance.

        Raises:
            CorruptedPDFError: If PyMuPDF cannot parse or open the PDF stream.
            PasswordProtectedPDFError: If PDF requires a password to read.
            ZeroPagesPDFError: If PDF contains 0 pages.
            PageLimitExceededError: If PDF exceeds maximum allowed pages.
        """
        resolved_path = self.validate_file(file_path)

        doc = None
        try:
            doc = pymupdf.open(str(resolved_path))
        except (pymupdf.FileDataError, RuntimeError, Exception) as e:
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass
            raise CorruptedPDFError(f"Corrupted or unreadable PDF file: {e}") from e

        # Check password encryption
        if doc.is_encrypted or doc.needs_pass:
            doc.close()
            raise PasswordProtectedPDFError(f"PDF document is password protected and cannot be processed.")

        # Check page counts
        page_count = doc.page_count
        if page_count == 0:
            doc.close()
            raise ZeroPagesPDFError("PDF document contains zero pages.")

        if page_count > self.config.max_pages:
            doc.close()
            raise PageLimitExceededError(
                f"PDF has {page_count} pages, which exceeds the limit of {self.config.max_pages} pages.",
                page_count=page_count,
                max_pages=self.config.max_pages,
            )

        return doc

