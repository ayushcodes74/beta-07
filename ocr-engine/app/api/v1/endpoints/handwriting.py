"""Within-submission handwriting consistency (teacher review signal; unvalidated heuristic).

Internal endpoint: the backend calls it for teachers only. Results are cached in the job workspace.
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.handwriting.consistency import ANALYSIS_VERSION, analyze
from app.handwriting.job_loader import pages_from_result
from app.jobs.job_manager import JobManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Handwriting"])

_CACHE_FILE = "handwriting.json"


def _run(job_dir: Path, result: dict) -> dict:
    cache = job_dir / _CACHE_FILE
    if cache.is_file():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if cached.get("version") == ANALYSIS_VERSION:
                return cached
        except (OSError, ValueError):
            pass
    pages = pages_from_result(job_dir, result)
    if not pages:
        return {"version": ANALYSIS_VERSION, "status": "unavailable",
                "reason": "Page images for this submission are no longer available."}
    analysis = analyze(pages)
    try:
        cache.write_text(json.dumps(analysis), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not cache handwriting analysis: %s", exc)
    return analysis


@router.get(
    "/handwriting/{job_id}",
    responses={
        200: {"description": "Analysis (status: consistent, possible_different_handwriting, insufficient_handwriting, unavailable)"},
        202: {"description": "OCR still processing"},
        404: {"description": "Job not found"},
    },
)
async def get_handwriting_consistency(job_id: str) -> Any:
    """Compare handwriting style across answers/pages of one submission. Teacher review signal only."""
    manager = JobManager.get_instance()
    job_status = manager.get_job_status(job_id)
    if not job_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    if job_status.status in ("queued", "processing"):
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="OCR is still processing.")
    result = manager.get_job_result(job_id)
    job = manager.store.get_job(job_id)
    if result is None or job is None or not job.temp_dir:
        return {"version": ANALYSIS_VERSION, "status": "unavailable", "reason": "No OCR result for this job."}
    return await run_in_threadpool(_run, Path(job.temp_dir), result.model_dump(mode="json"))
