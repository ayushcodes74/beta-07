"""Module 5 API package exposing FastAPI application factory, schemas, and configurations."""

from app.api.app import app, create_app
from app.api.config import APIConfig, DEFAULT_API_CONFIG
from app.api.schemas import (
    BoundingBoxSchema,
    DocumentMetadataSchema,
    HealthResponse,
    JobStatusResponse,
    MathBlockSchema,
    OCRDocumentResult,
    PageResultSchema,
    ProcessJobResponse,
    ProcessingSummarySchema,
    TextBlockSchema,
)

__all__ = [
    "app",
    "create_app",
    "APIConfig",
    "DEFAULT_API_CONFIG",
    "HealthResponse",
    "ProcessJobResponse",
    "JobStatusResponse",
    "OCRDocumentResult",
    "PageResultSchema",
    "TextBlockSchema",
    "MathBlockSchema",
    "BoundingBoxSchema",
    "ProcessingSummarySchema",
    "DocumentMetadataSchema",
]

