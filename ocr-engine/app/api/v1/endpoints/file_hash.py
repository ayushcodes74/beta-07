"""SHA-256 fingerprint of a job's uploaded PDF.

Lets the backend spot the *same file* handed in by different students for one assignment (exact
duplicate), which works even when OCR could read no text. Computed once from the stored
``submission.pdf`` and cached next to it, so it also covers jobs submitted before this endpoint existed.
"""

import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.jobs.job_manager import JobManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Integrity"])

_CACHE_FILE = "submission.sha256"


def _sha256(job_dir: Path) -> str | None:
    cache = job_dir / _CACHE_FILE
    if cache.is_file():
        cached = cache.read_text(encoding="ascii").strip()
        if len(cached) == 64:
            return cached
    pdf = job_dir / "submission.pdf"
    if not pdf.is_file():
        return None
    digest = hashlib.sha256()
    with pdf.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    try:
        cache.write_text(value, encoding="ascii")
    except OSError as exc:
        logger.warning("Could not cache file hash: %s", exc)
    return value


@router.get(
    "/file-hash/{job_id}",
    responses={
        200: {"description": "{'job_id', 'sha256'}; sha256 is null when the uploaded file is no longer stored"},
        404: {"description": "Job not found"},
    },
)
async def get_file_hash(job_id: str) -> dict:
    """SHA-256 of the PDF uploaded for this job (exact-duplicate detection; no content is returned)."""
    job = JobManager.get_instance().store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found.")
    if not job.temp_dir:
        return {"job_id": job_id, "sha256": None}
    return {"job_id": job_id, "sha256": await run_in_threadpool(_sha256, Path(job.temp_dir))}
