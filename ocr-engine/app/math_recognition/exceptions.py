"""Custom exceptions for Mathematical Recognition & Quality Analysis Module 4."""

from typing import Optional


class MathRecognitionError(Exception):
    """Base exception for all mathematical recognition module errors."""

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


class MathImageError(MathRecognitionError):
    """Raised when a mathematical image crop cannot be loaded, decoded, or processed."""


class MathRegionValidationError(MathRecognitionError):
    """Raised when bounding-box coordinates or region dimensions are invalid or out of bounds."""


class MathModelLoadingError(MathRecognitionError):
    """Raised when a mathematical OCR model fails to download, initialize, or allocate."""


class MathInferenceError(MathRecognitionError):
    """Raised when mathematical inference crashes, encounters OOM, or times out."""


class LaTeXConversionError(MathRecognitionError):
    """Raised when mathematical representation cannot be converted to valid LaTeX."""


class MathPipelineError(MathRecognitionError):
    """Raised when mathematical pipeline orchestration encounters an unrecoverable failure."""

