"""Module 1: PDF Ingestion & Processing for TrustGrade OCR Engine."""

from app.ingestion.config import IngestionConfig, DEFAULT_CONFIG
from app.ingestion.exceptions import (
    CorruptedPDFError,
    EmptyPDFError,
    FileTooLargeError,
    IngestionError,
    InvalidPDFError,
    PageLimitExceededError,
    PasswordProtectedPDFError,
    PathTraversalError,
    PDFRenderingError,
    ZeroPagesPDFError,
)
from app.ingestion.metadata_extractor import MetadataExtractor
from app.ingestion.pdf_processor import process_pdf
from app.ingestion.pdf_validator import PDFValidator
from app.ingestion.schemas import DocumentMetadata, PageRecord, PDFProcessingResult

__all__ = [
    "process_pdf",
    "PDFValidator",
    "MetadataExtractor",
    "IngestionConfig",
    "DEFAULT_CONFIG",
    "PDFProcessingResult",
    "PageRecord",
    "DocumentMetadata",
    "IngestionError",
    "InvalidPDFError",
    "EmptyPDFError",
    "ZeroPagesPDFError",
    "CorruptedPDFError",
    "PasswordProtectedPDFError",
    "FileTooLargeError",
    "PageLimitExceededError",
    "PDFRenderingError",
    "PathTraversalError",
]

