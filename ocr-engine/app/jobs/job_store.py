"""Thread-safe job store managing OCR job lifecycles.

Records live in memory and are mirrored to ``<job_dir>/job.json`` (+ ``result.json`` once finished)
so that JobManager can restore them after a service restart.

LIMITATIONS:
1. Records are not shared across multiple worker processes without external shared storage.
2. For enterprise production workloads, jobs should be backed by a durable database queue.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import threading
from typing import Any, Dict, List, Optional
import uuid

from app.api.schemas import OCRDocumentResult

logger = logging.getLogger(__name__)

JOB_META_FILENAME = "job.json"
JOB_RESULT_FILENAME = "result.json"


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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
    def reset_instance(cls, cleanup_files: bool = True) -> None:
        """Reset the singleton instance.

        Args:
            cleanup_files: Delete the job workspaces too (isolated unit tests). Service shutdown
                passes False so finished results survive a restart.
        """
        with cls._lock:
            if cls._instance is not None and cleanup_files:
                cls._instance.cleanup_all()
            cls._instance = None

    def persist(self, job: JobRecord) -> None:
        """Mirror a job's state (and result, once available) into its workspace. Best-effort."""
        if not job.temp_dir or not Path(job.temp_dir).is_dir():
            return
        try:
            job_dir = Path(job.temp_dir)
            if job.result is not None:
                _atomic_write_text(job_dir / JOB_RESULT_FILENAME, job.result.model_dump_json())
            _atomic_write_text(job_dir / JOB_META_FILENAME, json.dumps(job.to_dict()))
        except Exception as e:  # persistence must never break job processing
            logger.warning("Could not persist job %s: %s", job.job_id, e)

    def register(self, record: JobRecord) -> JobRecord:
        """Add an externally constructed (e.g. restored-from-disk) record; keeps any existing one."""
        with self._lock:
            return self._jobs.setdefault(record.job_id, record)

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
                self.persist(job)
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
                self.persist(job)
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

