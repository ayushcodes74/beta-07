"""Custom exception hierarchy for the PDF ingestion module."""

from typing import Optional


class IngestionError(Exception):
    """Base exception for all ingestion module errors."""

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details={self.details})"
        return self.message


class InvalidPDFError(IngestionError):
    """Raised when an input file is not a valid PDF format or fails initial signature checks."""


class EmptyPDFError(InvalidPDFError):
    """Raised when a PDF file is empty (0 bytes)."""


class ZeroPagesPDFError(InvalidPDFError):
    """Raised when a PDF file has zero pages."""


class CorruptedPDFError(IngestionError):
    """Raised when a PDF file is corrupted, truncated, or unreadable by the PDF parser."""


class PasswordProtectedPDFError(IngestionError):
    """Raised when a PDF file is encrypted and password-protected."""


class FileTooLargeError(IngestionError):
    """Raised when a PDF file exceeds the configured maximum file size."""

    def __init__(
        self,
        message: str,
        file_size_bytes: Optional[int] = None,
        max_size_bytes: Optional[int] = None,
    ) -> None:
        details = {}
        if file_size_bytes is not None:
            details["file_size_bytes"] = file_size_bytes
        if max_size_bytes is not None:
            details["max_size_bytes"] = max_size_bytes
        super().__init__(message, details=details)


class PageLimitExceededError(IngestionError):
    """Raised when a PDF contains more pages than the configured maximum page limit."""

    def __init__(
        self,
        message: str,
        page_count: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> None:
        details = {}
        if page_count is not None:
            details["page_count"] = page_count
        if max_pages is not None:
            details["max_pages"] = max_pages
        super().__init__(message, details=details)


class PDFRenderingError(IngestionError):
    """Raised when rendering a PDF page into an image fails."""

    def __init__(
        self,
        message: str,
        page_number: Optional[int] = None,
        original_error: Optional[str] = None,
    ) -> None:
        details = {}
        if page_number is not None:
            details["page_number"] = page_number
        if original_error is not None:
            details["original_error"] = original_error
        super().__init__(message, details=details)


class PathTraversalError(IngestionError):
    """Raised when an unsafe path or identifier is provided that could cause path traversal."""

