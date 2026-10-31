"""Job execution status polling endpoint."""

from fastapi import APIRouter, HTTPException, status

from app.api.schemas import JobStatusResponse
from app.jobs.job_manager import JobManager

router = APIRouter(tags=["Status"])


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    """Retrieve the current processing lifecycle status and stage of an OCR job."""
    job_mgr = JobManager.get_instance()
    status_resp = job_mgr.get_job_status(job_id)

    if not status_resp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    return status_resp

