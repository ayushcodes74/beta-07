"""Custom exceptions for Image Preprocessing Module 2."""

from typing import Optional


class PreprocessingError(Exception):
    """Base exception for all image preprocessing errors."""

    def __init__(self, message: str, page_number: Optional[int] = None, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.page_number = page_number
        self.details = details or {}

    def __str__(self) -> str:
        parts = [self.message]
        if self.page_number is not None:
            parts.append(f"(page={self.page_number})")
        if self.details:
            parts.append(f"(details={self.details})")
        return " ".join(parts)


class InvalidImageError(PreprocessingError):
    """Raised when an image is invalid, corrupted, empty, or unreadable."""


class UnsupportedImageFormatError(InvalidImageError):
    """Raised when an image format is not supported (only PNG and JPEG are supported)."""


class ImageLoadError(PreprocessingError):
    """Raised when an image file cannot be decoded or loaded into memory."""


class ImageProcessingError(PreprocessingError):
    """Raised when a processing transformation fails."""


class ImageSaveError(PreprocessingError):
    """Raised when an enhanced image or variant cannot be written to disk."""

