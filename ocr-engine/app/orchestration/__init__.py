"""Module 5 Orchestration package executing end-to-end multi-module pipelines."""

from app.orchestration.ocr_orchestrator import OCROrchestrator
from app.orchestration.result_aggregator import ResultAggregator

__all__ = [
    "OCROrchestrator",
    "ResultAggregator",
]

