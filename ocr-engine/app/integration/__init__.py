"""Module 5 Integration package connecting TrustGrade Backend and grading pipelines to OCR Engine."""

from app.integration.backend_client import TrustGradeOCRClient
from app.integration.contract import (
    BackendGradingPayload,
    BackendOCRJobResponse,
    BackendOCRRequest,
)

__all__ = [
    "TrustGradeOCRClient",
    "BackendOCRRequest",
    "BackendOCRJobResponse",
    "BackendGradingPayload",
]

