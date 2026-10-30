"""Pydantic schemas for PDF ingestion input and output models."""

from typing import List, Optional
from pydantic import BaseModel, Field


class PageRecord(BaseModel):
    """Structured information for an individual rendered page.

    Attributes:
        page_number: 1-based page index.
        image_path: Relative or standardized path to the rendered page image.
        width: Rendered image width in pixels.
        height: Rendered image height in pixels.
        original_width: Original page width in points.
        original_height: Original page height in points.
        rotation: Page rotation angle in degrees (0, 90, 180, 270).
    """

    page_number: int = Field(..., ge=1, description="1-based page number")
    image_path: str = Field(..., description="Path to rendered page image")
    width: int = Field(..., ge=1, description="Rendered image width in pixels")
    height: int = Field(..., ge=1, description="Rendered image height in pixels")
    original_width: float = Field(..., ge=0.0, description="Original page width in points")
    original_height: float = Field(..., ge=0.0, description="Original page height in points")
    rotation: int = Field(default=0, description="Page rotation in degrees")


class DocumentMetadata(BaseModel):
    """PDF document metadata attributes.

    Gracefully stores standard PDF metadata keys when present.
    """

    title: Optional[str] = Field(default=None, description="PDF title")
    author: Optional[str] = Field(default=None, description="PDF author")
    subject: Optional[str] = Field(default=None, description="PDF subject")
    creator: Optional[str] = Field(default=None, description="PDF creator tool")
    producer: Optional[str] = Field(default=None, description="PDF producer engine")
    creation_date: Optional[str] = Field(default=None, description="Creation timestamp")
    modification_date: Optional[str] = Field(default=None, description="Last modification timestamp")


class PDFProcessingResult(BaseModel):
    """Standardized output structure for processed PDF submissions.

    Attributes:
        submission_id: Unique identifier for the assignment submission.
        status: Status of the ingestion process (e.g. 'processed').
        total_pages: Total number of pages extracted.
        pages: List of PageRecord objects in page order.
        metadata: DocumentMetadata object containing extracted document info.
    """

    submission_id: str = Field(..., description="Submission ID")
    status: str = Field(default="processed", description="Ingestion processing status")
    total_pages: int = Field(..., ge=0, description="Total pages processed")
    pages: List[PageRecord] = Field(default_factory=list, description="Extracted page records")
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata, description="Extracted PDF metadata")

