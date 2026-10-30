"""Custom exceptions for Text & Handwriting Recognition Module 3."""

from typing import Optional


class RecognitionError(Exception):
    """Base exception for all recognition module errors."""

    def __init__(
        self,
        message: str,
        page_number: Optional[int] = None,
        region_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.page_number = page_number
        self.region_id = region_id
        self.details = details or {}

    def __str__(self) -> str:
        parts = [self.message]
        if self.page_number is not None:
            parts.append(f"(page={self.page_number})")
        if self.region_id is not None:
            parts.append(f"(region={self.region_id})")
        if self.details:
            parts.append(f"(details={self.details})")
        return " ".join(parts)


class TextDetectionError(RecognitionError):
    """Raised when text region detection fails on an image."""


class PrintedRecognitionError(RecognitionError):
    """Raised when printed text recognition inference fails."""


class HandwritingRecognitionError(RecognitionError):
    """Raised when handwriting recognition inference fails."""


class ModelLoadingError(RecognitionError):
    """Raised when an OCR model cannot be initialized, downloaded, or loaded."""


class RecognitionPipelineError(RecognitionError):
    """Raised when pipeline orchestration encounters an unrecoverable failure."""

