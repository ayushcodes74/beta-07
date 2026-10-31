"""Validation service for input page images."""

from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

from app.preprocessing.config import PreprocessingConfig, DEFAULT_PREPROCESSING_CONFIG
from app.preprocessing.exceptions import (
    InvalidImageError,
    UnsupportedImageFormatError,
)

# Supported image signatures
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


class ImageValidator:
    """Validates image files before loading and processing."""

    def __init__(self, config: Optional[PreprocessingConfig] = None) -> None:
        self.config = config or DEFAULT_PREPROCESSING_CONFIG

    def validate_file(self, image_path: str | Path) -> Tuple[Path, str, Tuple[int, int]]:
        """Validate an image file for existence, supported format, and dimensions.

        Args:
            image_path: Path to the candidate image file.

        Returns:
            Tuple of (resolved_path, format_name, (width, height)).

        Raises:
            InvalidImageError: If the file does not exist, is empty, is corrupted,
                               or has invalid/extremely small dimensions.
            UnsupportedImageFormatError: If the image format is not PNG or JPEG.
        """
        path = Path(image_path).resolve()

        if not path.exists():
            raise InvalidImageError(f"Image file not found: '{image_path}'")

        if not path.is_file():
            raise InvalidImageError(f"Path is not a regular file: '{image_path}'")

        if path.stat().st_size == 0:
            raise InvalidImageError(f"Image file is empty (0 bytes): '{image_path}'")

        # Verify extension
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise UnsupportedImageFormatError(
                f"Unsupported image extension '{ext}'. Only PNG and JPEG are supported."
            )

        # Inspect binary magic signature
        try:
            with open(path, "rb") as f:
                header = f.read(16)
        except OSError as e:
            raise InvalidImageError(f"Could not read image header: {e}") from e

        format_name: str
        if header.startswith(PNG_MAGIC):
            format_name = "PNG"
        elif header.startswith(JPEG_MAGIC):
            format_name = "JPEG"
        else:
            raise UnsupportedImageFormatError(
                f"File '{image_path}' is not a valid PNG or JPEG image (magic bytes mismatch)."
            )

        # Verify readability and dimensions via Pillow without loading entire pixel buffer
        try:
            with Image.open(path) as img:
                img.verify()
                # Reopen to read dimensions since verify() closes image state in PIL
            with Image.open(path) as img:
                width, height = img.size
        except Exception as e:
            raise InvalidImageError(f"Corrupted or unreadable image file '{image_path}': {e}") from e

        if width < self.config.min_valid_width or height < self.config.min_valid_height:
            raise InvalidImageError(
                f"Image dimensions ({width}x{height}) are too small for processing. "
                f"Minimum required is {self.config.min_valid_width}x{self.config.min_valid_height}."
            )

        return path, format_name, (width, height)

