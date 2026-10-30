"""Configuration settings and limits for the PDF ingestion module."""

from pydantic import BaseModel, Field


class IngestionConfig(BaseModel):
    """Configurable limits and options for PDF processing.

    Attributes:
        max_file_size_bytes: Maximum allowed PDF file size in bytes (default: 20 MB).
        max_pages: Maximum allowed number of pages in a PDF (default: 100).
        rendering_dpi: DPI used for rendering PDF pages to images (default: 200).
        image_format: Image file format for rendered pages (default: 'png').
        image_name_pattern: Format string for generated page filenames (default: 'page_{page_number:03d}.png').
    """

    max_file_size_bytes: int = Field(
        default=20 * 1024 * 1024,
        description="Maximum file size in bytes (default 20MB)",
        ge=1,
    )
    max_pages: int = Field(
        default=100,
        description="Maximum page count limit (default 100)",
        ge=1,
    )
    rendering_dpi: int = Field(
        default=200,
        description="Rendering DPI for output images (default 200)",
        ge=72,
        le=600,
    )
    image_format: str = Field(
        default="png",
        description="Image output format",
    )
    image_name_pattern: str = Field(
        default="page_{page_number:03d}.png",
        description="Naming pattern for page images",
    )


# Default configuration instance
DEFAULT_CONFIG = IngestionConfig()

