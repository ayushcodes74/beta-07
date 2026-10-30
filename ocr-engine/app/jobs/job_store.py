"""Thread-safe in-memory job store managing OCR job lifecycles.

LIMITATION NOTICE:
This is an in-memory job repository designed for the MVP service layer:
1. Job states and results are lost on service process termination or restart.
2. Job records are not shared across multiple worker processes without external shared storage (e.g. Redis/PostgreSQL).
3. For enterprise production workloads, jobs should be backed by a durable database queue.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
import threading
from typing import Any, Dict, List, Optional
import uuid

from app.api.schemas import OCRDocumentResult

logger = logging.getLogger(__name__)


class JobRecord:
    """Represents the in-memory state of an asynchronous OCR processing task."""

    def __init__(
        self,
        job_id: str,
        submission_id: str,
        temp_dir: Optional[Path] = None,
    ) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        self.job_id = job_id
        self.submission_id = submission_id
        self.status = "queued"
        self.stage = "queued"
        self.progress = 0
        self.created_at = now_str
        self.updated_at = now_str
        self.temp_dir = temp_dir
        self.result: Optional[OCRDocumentResult] = None
        self.error: Optional[str] = None
        self.warnings: List[str] = []
        self._future: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert job status to dictionary representation."""
        return {
            "job_id": self.job_id,
            "submission_id": self.submission_id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "warnings": list(self.warnings),
        }


class JobStore:
    """Thread-safe singleton job store managing lifecycle transitions."""

    _instance: Optional["JobStore"] = None
    _lock = threading.RLock()

    def __init__(self) -> None:
        self._jobs: Dict[str, JobRecord] = {}

    @classmethod
    def get_instance(cls) -> "JobStore":
        """Get or initialize singleton JobStore instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for isolated unit testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.cleanup_all()
            cls._instance = None

    def create_job(self, submission_id: str, temp_dir: Optional[Path] = None) -> JobRecord:
        """Create and register a new unique job in 'queued' state."""
        job_id = f"job-{uuid.uuid4().hex}"
        with self._lock:
            record = JobRecord(job_id=job_id, submission_id=submission_id, temp_dir=temp_dir)
            self._jobs[job_id] = record
            logger.info("Created job %s for submission %s", job_id, submission_id)
            return record

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Retrieve job record by unique identifier."""
        with self._lock:
            return self._jobs.get(job_id)

    def update_progress(self, job_id: str, stage: str, progress: int) -> None:
        """Update job stage and percentage completion."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "processing"
                job.stage = stage
                job.progress = max(0, min(100, progress))
                job.updated_at = datetime.now(timezone.utc).isoformat()

    def complete_job(self, job_id: str, result: OCRDocumentResult) -> None:
        """Mark job as successfully finished or degraded based on result status."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = result.status
                job.stage = "done"
                job.progress = 100
                job.result = result
                job.warnings.extend(result.warnings)
                job.updated_at = datetime.now(timezone.utc).isoformat()
                logger.info("Job %s completed with final status '%s'", job_id, job.status)

    def fail_job(self, job_id: str, error_msg: str) -> None:
        """Mark job as failed with explicit error details."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = "failed"
                job.stage = "done"
                job.error = error_msg
                job.updated_at = datetime.now(timezone.utc).isoformat()
                logger.error("Job %s failed: %s", job_id, error_msg)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued or executing job and release resources."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            if job.status in ("completed", "completed_with_warnings", "degraded", "failed", "cancelled"):
                return False  # Already finished

            if job._future and not job._future.done():
                job._future.cancel()

            job.status = "cancelled"
            job.stage = "done"
            job.error = "Job was cancelled by client request."
            job.updated_at = datetime.now(timezone.utc).isoformat()

            self.cleanup_job_files(job_id)
            logger.info("Job %s was cancelled", job_id)
            return True

    def cleanup_job_files(self, job_id: str) -> None:
        """Delete temporary storage directory associated with a job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.temp_dir and Path(job.temp_dir).exists():
                try:
                    shutil.rmtree(job.temp_dir, ignore_errors=True)
                    logger.info("Cleaned temporary files for job %s", job_id)
                except Exception as e:
                    logger.warning("Error cleaning temporary files for job %s: %s", job_id, e)

    def cleanup_all(self) -> None:
        """Clean all active jobs and temporary directories (for shutdown or testing)."""
        with self._lock:
            for jid in list(self._jobs.keys()):
                self.cleanup_job_files(jid)
            self._jobs.clear()

    def count_active_jobs(self) -> int:
        """Count jobs currently queued or executing."""
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ("queued", "processing"))

