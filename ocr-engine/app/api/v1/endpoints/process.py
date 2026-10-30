"""PDF upload and asynchronous job submission endpoint."""

import logging
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.schemas import ProcessJobResponse
from app.ingestion.exceptions import IngestionError
from app.jobs.job_manager import JobManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Processing"])


@router.post("/process", response_model=ProcessJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def process_pdf(
    file: UploadFile = File(..., description="Student assignment PDF document"),
    submission_id: Optional[str] = Form(default=None, description="Optional submission identifier"),
    run_async: bool = Form(default=True, description="Whether to execute in background thread pool"),
) -> ProcessJobResponse:
    """Accept a PDF assignment submission, validate security boundaries, and queue an OCR job.

    Returns:
        ProcessJobResponse containing unique job_id for status tracking.
    """
    job_mgr = JobManager.get_instance()

    try:
        content = await file.read()
        filename = file.filename or "submission.pdf"

        job = job_mgr.submit_job(
            file_bytes=content,
            filename=filename,
            submission_id=submission_id,
            run_async=run_async,
        )

        return ProcessJobResponse(
            job_id=job.job_id,
            submission_id=job.submission_id,
            status=job.status,
            created_at=job.created_at,
            message="PDF submission accepted and scheduled for processing.",
        )

    except IngestionError as e:
        logger.warning("Rejected PDF submission: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Failed to accept submission: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Processing submission failed: {e}") from e

