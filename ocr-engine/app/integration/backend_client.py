"""Reference client demonstrating how TrustGrade Backend communicates with the OCR Service."""

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union
import httpx

from app.api.schemas import HealthResponse, JobStatusResponse, OCRDocumentResult
from app.integration.contract import BackendGradingPayload

logger = logging.getLogger(__name__)


class TrustGradeOCRClient:
    """Client for TrustGrade backend services to interact with the OCR Engine API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8001", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check_health(self) -> HealthResponse:
        """Query OCR service operational health and model readiness."""
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            resp = client.get("/health")
            resp.raise_for_status()
            return HealthResponse(**resp.json())

    def submit_pdf(
        self,
        pdf_input: Union[str, Path, bytes],
        submission_id: str,
        filename: str = "submission.pdf",
    ) -> str:
        """Upload assignment PDF to OCR service and receive unique job_id.

        Args:
            pdf_input: File path or raw PDF bytes.
            submission_id: Unique submission ID from the backend database.
            filename: Original PDF filename.

        Returns:
            job_id string for status polling.
        """
        data = {"submission_id": submission_id, "run_async": "true"}

        if isinstance(pdf_input, (str, Path)):
            p = Path(pdf_input)
            files = {"file": (p.name, p.read_bytes(), "application/pdf")}
        else:
            files = {"file": (filename, pdf_input, "application/pdf")}

        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            resp = client.post("/api/v1/ocr/process", data=data, files=files)
            resp.raise_for_status()
            payload = resp.json()
            return payload["job_id"]

    def poll_job_until_complete(
        self,
        job_id: str,
        timeout_seconds: float = 120.0,
        poll_interval: float = 1.0,
    ) -> JobStatusResponse:
        """Poll job status until it reaches a terminal state (completed, degraded, failed, cancelled)."""
        start_time = time.time()

        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            while time.time() - start_time < timeout_seconds:
                resp = client.get(f"/api/v1/ocr/status/{job_id}")
                resp.raise_for_status()
                status_obj = JobStatusResponse(**resp.json())

                if status_obj.status in ("completed", "completed_with_warnings", "degraded", "failed", "cancelled"):
                    return status_obj

                time.sleep(poll_interval)

        raise TimeoutError(f"Job '{job_id}' timed out after {timeout_seconds}s polling.")

    def get_result(self, job_id: str) -> OCRDocumentResult:
        """Retrieve the completed OCR document result."""
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            resp = client.get(f"/api/v1/ocr/result/{job_id}")
            resp.raise_for_status()
            return OCRDocumentResult(**resp.json())

    def cancel_job(self, job_id: str) -> Dict[str, str]:
        """Request cancellation of an active or queued job."""
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            resp = client.delete(f"/api/v1/ocr/jobs/{job_id}")
            resp.raise_for_status()
            return resp.json()

    @classmethod
    def convert_to_grading_payload(cls, ocr_result: OCRDocumentResult) -> BackendGradingPayload:
        """Format an OCRDocumentResult into the canonical payload expected by AI grading."""
        full_texts = [p.full_text for p in ocr_result.pages if p.full_text.strip()]
        combined_text = "\n\n--- Page Break ---\n\n".join(full_texts)

        all_formulas: list[str] = []
        requires_review = False
        all_warnings: list[str] = list(ocr_result.warnings)

        for p in ocr_result.pages:
            all_warnings.extend(p.warnings)
            for mb in p.math_blocks:
                if mb.latex.strip():
                    all_formulas.append(mb.latex.strip())
                if mb.requires_manual_review:
                    requires_review = True

        if ocr_result.status in ("degraded", "completed_with_warnings", "failed"):
            requires_review = True

        return BackendGradingPayload(
            submission_id=ocr_result.submission_id,
            overall_status=ocr_result.status,
            extracted_full_text=combined_text,
            extracted_formulas_latex=all_formulas,
            page_count=len(ocr_result.pages),
            requires_manual_teacher_review=requires_review,
            quality_warnings=all_warnings,
        )

