"""Metadata extraction service for PDF documents and pages."""

import logging
from typing import Any, Dict, Optional, Tuple

import pymupdf

from app.ingestion.schemas import DocumentMetadata

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Extracts document-level and page-level metadata from PyMuPDF documents."""

    @staticmethod
    def extract_document_metadata(doc: pymupdf.Document) -> DocumentMetadata:
        """Extract metadata from an open PDF document.

        Safely parses available document metadata (title, author, subject, etc.).
        Failures to parse individual metadata fields will not crash processing.

        Args:
            doc: Open pymupdf.Document.

        Returns:
            DocumentMetadata object.
        """
        try:
            raw_meta: Dict[str, Any] = doc.metadata or {}
        except Exception as e:
            logger.warning("Failed to access document metadata: %s. Proceeding with empty metadata.", e)
            return DocumentMetadata()

        def _clean_str(val: Any) -> Optional[str]:
            if val is None:
                return None
            s = str(val).strip()
            return s if s else None

        try:
            return DocumentMetadata(
                title=_clean_str(raw_meta.get("title")),
                author=_clean_str(raw_meta.get("author")),
                subject=_clean_str(raw_meta.get("subject")),
                creator=_clean_str(raw_meta.get("creator")),
                producer=_clean_str(raw_meta.get("producer")),
                creation_date=_clean_str(raw_meta.get("creationDate")),
                modification_date=_clean_str(raw_meta.get("modDate")),
            )
        except Exception as e:
            logger.warning("Error constructing DocumentMetadata model: %s. Returning default.", e)
            return DocumentMetadata()

    @staticmethod
    def extract_page_dimensions(page: pymupdf.Page) -> Tuple[float, float, int]:
        """Extract dimensions and rotation angle from a single PDF page.

        Args:
            page: pymupdf.Page instance.

        Returns:
            Tuple of (original_width, original_height, rotation).
        """
        try:
            rect = page.rect
            width = float(round(rect.width, 2))
            height = float(round(rect.height, 2))
            rotation = int(page.rotation)
            return width, height, rotation
        except Exception as e:
            logger.warning("Failed to extract page dimensions: %s. Falling back to defaults.", e)
            return 0.0, 0.0, 0

