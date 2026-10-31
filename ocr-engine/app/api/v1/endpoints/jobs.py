"""Job management and cancellation endpoints."""

from typing import Dict
from fastapi import APIRouter, HTTPException, status

from app.jobs.job_manager import JobManager

router = APIRouter(tags=["Jobs"])


@router.delete("/jobs/{job_id}", response_model=Dict[str, str])
def cancel_job(job_id: str) -> Dict[str, str]:
    """Cancel an active or queued OCR processing job and clean up temporary storage.

    Returns:
        JSON confirmation if cancelled.
    """
    job_mgr = JobManager.get_instance()
    job_status = job_mgr.get_job_status(job_id)

    if not job_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if job_status.status in ("completed", "completed_with_warnings", "degraded", "failed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job '{job_id}' is already in terminal state '{job_status.status}' and cannot be cancelled.",
        )

    success = job_mgr.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel job '{job_id}'.",
        )

    return {
        "job_id": job_id,
        "status": "cancelled",
        "message": f"Job '{job_id}' has been cancelled and temporary files were cleaned up.",
    }

