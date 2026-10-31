"""Asynchronous HTTPX client for TrustGrade OCR Microservice."""

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Any, Dict, Optional, Union
import httpx

from app.core.config import settings
from app.schemas.ocr import (
    HealthResponse,
    JobStatusResponse,
    OCRDocumentResult,
    ProcessJobResponse,
)

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Base exception for OCR service client errors."""


class OCRServiceUnavailableError(OCRError):
    """OCR service is down, unreachable, or returning 5xx errors."""


class OCRTimeoutError(OCRError):
    """Network connection, response read, or polling timeout."""


class OCRInvalidFileError(OCRError):
    """OCR engine rejected the uploaded file (e.g. non-PDF, corrupt, password-protected, >20MB)."""


class OCRJobFailedError(OCRError):
    """OCR job failed during pipeline execution."""

    def __init__(self, message: str, job_id: str, error_detail: Optional[str] = None):
        super().__init__(message)
        self.job_id = job_id
        self.error_detail = error_detail


class OCRJobCancelledError(OCRError):
    """OCR job was cancelled before or during processing."""

    def __init__(self, message: str, job_id: str):
        super().__init__(message)
        self.job_id = job_id


class OCRJobNotFoundError(OCRError):
    """Requested OCR job ID does not exist in the OCR service."""


class OCRServiceClient:
    """Asynchronous HTTP client communicating with the OCR Engine API microservice."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        poll_timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = (base_url or settings.OCR_SERVICE_URL).rstrip("/")
        self.connect_timeout = (
            connect_timeout if connect_timeout is not None else settings.OCR_CONNECT_TIMEOUT_SECONDS
        )
        self.read_timeout = (
            read_timeout if read_timeout is not None else settings.OCR_READ_TIMEOUT_SECONDS
        )
        self.poll_timeout = (
            poll_timeout if poll_timeout is not None else settings.OCR_POLL_TIMEOUT_SECONDS
        )
        self.poll_interval = (
            poll_interval if poll_interval is not None else settings.OCR_POLL_INTERVAL_SECONDS
        )
        self._custom_client = client

    @asynccontextmanager
    async def _get_client(self):
        if self._custom_client is not None:
            yield self._custom_client
        else:
            timeout_config = httpx.Timeout(
                timeout=self.read_timeout,
                connect=self.connect_timeout,
            )
            headers = {}
            if settings.OCR_API_KEY:
                headers["Authorization"] = f"Bearer {settings.OCR_API_KEY.get_secret_value()}"
            async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout_config, headers=headers) as client:
                yield client

    async def check_health(self) -> HealthResponse:
        """Query OCR service operational health and model readiness.

        Never logs sensitive tokens or internal paths.
        """
        async with self._get_client() as client:
            try:
                resp = await client.get("/health")
                resp.raise_for_status()
                return HealthResponse(**resp.json())
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                logger.error("OCR service connection failed on health check: %s", type(e).__name__)
                raise OCRServiceUnavailableError("OCR service connection failed") from e
            except httpx.HTTPStatusError as e:
                logger.error("OCR service returned status %d on health check", e.response.status_code)
                raise OCRServiceUnavailableError(f"OCR service health check returned status {e.response.status_code}") from e
            except Exception as e:
                logger.error("OCR health check unexpected error: %s", type(e).__name__)
                raise OCRServiceUnavailableError("OCR service health check failed") from e

    async def submit_pdf(
        self,
        file_bytes: bytes,
        filename: str = "submission.pdf",
        submission_id: Optional[str] = None,
        run_async: bool = True,
    ) -> ProcessJobResponse:
        """Upload assignment PDF to OCR service and receive unique job_id.

        Security Note: The binary bytes and filename are transmitted directly,
        never logged to disk or console.
        """
        data = {
            "run_async": "true" if run_async else "false",
        }
        if submission_id:
            data["submission_id"] = submission_id

        files = {
            "file": (filename, file_bytes, "application/pdf"),
        }

        async with self._get_client() as client:
            try:
                resp = await client.post("/api/v1/ocr/process", data=data, files=files)
                if resp.status_code == 400:
                    detail = resp.json().get("detail", "Invalid PDF submission")
                    raise OCRInvalidFileError(f"PDF validation rejected by OCR engine: {detail}")
                resp.raise_for_status()
                payload = resp.json()
                logger.info(
                    "Submitted OCR job %s for submission %s",
                    payload.get("job_id"),
                    submission_id or "anonymous",
                )
                return ProcessJobResponse(**payload)

            except OCRInvalidFileError:
                raise
            except httpx.TimeoutException as e:
                logger.error("Timeout uploading PDF to OCR service")
                raise OCRTimeoutError("Timeout communicating with OCR service") from e
            except (httpx.ConnectError, httpx.NetworkError) as e:
                logger.error("Failed to connect to OCR service: %s", type(e).__name__)
                raise OCRServiceUnavailableError("OCR service is currently unavailable") from e
            except httpx.HTTPStatusError as e:
                logger.error("OCR service returned status %d on submission", e.response.status_code)
                raise OCRServiceUnavailableError(f"OCR service returned error: {e.response.status_code}") from e
            except Exception as e:
                logger.error("Unexpected error submitting to OCR service: %s", type(e).__name__)
                raise OCRServiceUnavailableError("OCR service processing failed") from e

    async def get_job_status(self, job_id: str) -> JobStatusResponse:
        """Poll the current processing lifecycle status of an OCR job."""
        async with self._get_client() as client:
            try:
                resp = await client.get(f"/api/v1/ocr/status/{job_id}")
                if resp.status_code == 404:
                    raise OCRJobNotFoundError(f"OCR Job '{job_id}' not found")
                resp.raise_for_status()
                return JobStatusResponse(**resp.json())

            except OCRJobNotFoundError:
                raise
            except httpx.TimeoutException as e:
                raise OCRTimeoutError("Timeout checking OCR job status") from e
            except (httpx.ConnectError, httpx.NetworkError) as e:
                raise OCRServiceUnavailableError("OCR service is currently unreachable") from e
            except httpx.HTTPStatusError as e:
                raise OCRServiceUnavailableError(f"OCR service returned status {e.response.status_code}") from e

    async def get_job_result(self, job_id: str) -> Union[OCRDocumentResult, JobStatusResponse]:
        """Retrieve the completed OCR document result.

        Returns:
            - OCRDocumentResult if finished (200 OK)
            - JobStatusResponse if still running (202 Accepted)

        Raises:
            - OCRJobFailedError if the job failed (400 Bad Request)
            - OCRJobCancelledError if the job was cancelled (400 Bad Request)
            - OCRJobNotFoundError if job does not exist (404 Not Found)
        """
        async with self._get_client() as client:
            try:
                resp = await client.get(f"/api/v1/ocr/result/{job_id}")

                if resp.status_code == 200:
                    return OCRDocumentResult(**resp.json())

                if resp.status_code == 202:
                    payload = resp.json()
                    # Return partial status response
                    return JobStatusResponse(
                        job_id=job_id,
                        status=payload.get("status", "processing"),
                        stage=payload.get("stage", "processing"),
                        progress=payload.get("progress", 0),
                        created_at="",
                        updated_at="",
                    )

                if resp.status_code == 400:
                    detail = resp.json().get("detail", {})
                    if isinstance(detail, dict):
                        status_val = detail.get("status")
                        err_msg = detail.get("error", "Job failed")
                        if status_val == "cancelled":
                            raise OCRJobCancelledError(f"OCR Job '{job_id}' was cancelled", job_id=job_id)
                        raise OCRJobFailedError(f"OCR Job '{job_id}' failed: {err_msg}", job_id=job_id, error_detail=err_msg)
                    raise OCRJobFailedError(f"OCR Job '{job_id}' failed: {detail}", job_id=job_id)

                if resp.status_code == 404:
                    raise OCRJobNotFoundError(f"OCR Job '{job_id}' not found")

                resp.raise_for_status()
                return OCRDocumentResult(**resp.json())

            except (OCRJobFailedError, OCRJobCancelledError, OCRJobNotFoundError):
                raise
            except httpx.TimeoutException as e:
                raise OCRTimeoutError("Timeout retrieving OCR result") from e
            except (httpx.ConnectError, httpx.NetworkError) as e:
                raise OCRServiceUnavailableError("OCR service is currently unreachable") from e
            except httpx.HTTPStatusError as e:
                raise OCRServiceUnavailableError(f"OCR service returned status {e.response.status_code}") from e

    async def poll_until_complete(
        self,
        job_id: str,
        poll_interval: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> OCRDocumentResult:
        """Poll job status until it reaches a terminal state and fetch result.

        Terminal states:
          - 'completed', 'completed_with_warnings', 'degraded' -> returns OCRDocumentResult
          - 'failed' -> raises OCRJobFailedError (never fabricates answers or treats as zero marks)
          - 'cancelled' -> raises OCRJobCancelledError
        """
        interval = poll_interval if poll_interval is not None else self.poll_interval
        max_wait = timeout if timeout is not None else self.poll_timeout

        loop = asyncio.get_event_loop()
        start_time = loop.time()

        while (loop.time() - start_time) < max_wait:
            status_obj = await self.get_job_status(job_id)

            if status_obj.status in ("completed", "completed_with_warnings", "degraded"):
                result = await self.get_job_result(job_id)
                if isinstance(result, OCRDocumentResult):
                    return result
                # In rare race conditions where status is completed but result still returns 202
                await asyncio.sleep(interval)
                continue

            if status_obj.status == "failed":
                raise OCRJobFailedError(
                    f"OCR Job '{job_id}' failed: {status_obj.error or 'Pipeline execution failed'}",
                    job_id=job_id,
                    error_detail=status_obj.error,
                )

            if status_obj.status == "cancelled":
                raise OCRJobCancelledError(f"OCR Job '{job_id}' was cancelled", job_id=job_id)

            await asyncio.sleep(interval)

        raise OCRTimeoutError(f"Polling OCR Job '{job_id}' exceeded timeout limit of {max_wait:.1f}s")

    async def cancel_job(self, job_id: str) -> Dict[str, str]:
        """Request cancellation and cleanup of an active or queued job."""
        async with self._get_client() as client:
            try:
                resp = await client.delete(f"/api/v1/ocr/jobs/{job_id}")
                if resp.status_code == 404:
                    raise OCRJobNotFoundError(f"OCR Job '{job_id}' not found")
                resp.raise_for_status()
                return resp.json()
            except OCRJobNotFoundError:
                raise
            except httpx.TimeoutException as e:
                raise OCRTimeoutError("Timeout cancelling OCR job") from e
            except (httpx.ConnectError, httpx.NetworkError) as e:
                raise OCRServiceUnavailableError("OCR service is currently unreachable") from e
            except httpx.HTTPStatusError as e:
                raise OCRServiceUnavailableError(f"OCR service returned status {e.response.status_code}") from e


def get_ocr_client() -> OCRServiceClient:
    """Dependency provider for OCR service client."""
    return OCRServiceClient()
