"""OCR structured document result retrieval endpoint."""

from typing import Any, Union
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse

from app.api.schemas import OCRDocumentResult
from app.jobs.job_manager import JobManager

router = APIRouter(tags=["Results"])


@router.get(
    "/result/{job_id}",
    response_model=OCRDocumentResult,
    responses={
        200: {"description": "OCR document result ready"},
        202: {"description": "Job is still processing"},
        400: {"description": "Job failed or was cancelled"},
        404: {"description": "Job not found"},
    },
)
def get_job_result(job_id: str) -> Any:
    """Retrieve the completed OCR document result.

    Returns:
        - 200 OK with full OCRDocumentResult if finished.
        - 202 Accepted if still queued or processing.
        - 400 Bad Request if the job failed or was cancelled.
        - 404 Not Found if job_id does not exist.
    """
    job_mgr = JobManager.get_instance()
    job_status = job_mgr.get_job_status(job_id)

    if not job_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    # 1. Job Still Running
    if job_status.status in ("queued", "processing"):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "job_id": job_id,
                "status": job_status.status,
                "stage": job_status.stage,
                "progress": job_status.progress,
                "message": f"Job is currently in stage '{job_status.stage}' ({job_status.progress}%). Retry shortly.",
            },
        )

    # 2. Job Failed or Cancelled
    if job_status.status in ("failed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "job_id": job_id,
                "status": job_status.status,
                "error": job_status.error or "Job failed during execution",
                "warnings": job_status.warnings,
            },
        )

    # 3. Job Succeeded / Degraded
    result = job_mgr.get_job_result(job_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Result data missing for completed job '{job_id}'.",
        )

    return result
