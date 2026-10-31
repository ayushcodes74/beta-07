"""Asynchronous background job manager executing OCR processing tasks via ThreadPoolExecutor."""

from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import re
import threading
from typing import Optional

from app.api.config import APIConfig, DEFAULT_API_CONFIG
from app.api.schemas import JobStatusResponse, OCRDocumentResult
from app.api.security import SecurityValidator
from app.jobs.job_store import JOB_META_FILENAME, JOB_RESULT_FILENAME, JobRecord, JobStore
from app.orchestration.ocr_orchestrator import OCROrchestrator

logger = logging.getLogger(__name__)

# Job IDs are generated as f"job-{uuid4().hex}"; anything else is never looked up on disk.
_JOB_ID_RE = re.compile(r"^job-[0-9a-f]{32}$")
_FINISHED_STATUSES = ("completed", "completed_with_warnings", "degraded", "failed", "cancelled")


class JobManager:
    """Manages thread-pool execution and lifecycle tracking for asynchronous OCR jobs."""

    _instance: Optional["JobManager"] = None

    def __init__(self, config: Optional[APIConfig] = None) -> None:
        self.config = config or DEFAULT_API_CONFIG
        self.store = JobStore.get_instance()
        self.validator = SecurityValidator(config=self.config)
        self.orchestrator = OCROrchestrator()
        self._executor = ThreadPoolExecutor(
            max_workers=self.config.concurrency_limit,
            thread_name_prefix="ocr-worker",
        )
        self._recover_lock = threading.Lock()

    @classmethod
    def shutdown(cls) -> None:
        """Stop workers on service shutdown WITHOUT deleting job workspaces, so finished
        results (and unfinished uploads, which are re-run) survive a restart."""
        if cls._instance is not None:
            cls._instance._executor.shutdown(wait=False, cancel_futures=True)
            JobStore.reset_instance(cleanup_files=False)
            cls._instance = None

    @classmethod
    def get_instance(cls, config: Optional[APIConfig] = None) -> "JobManager":
        """Get or initialize singleton JobManager instance."""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton and shutdown executor."""
        if cls._instance is not None:
            cls._instance._executor.shutdown(wait=False, cancel_futures=True)
            JobStore.reset_instance()
            cls._instance = None

    def submit_job(
        self,
        file_bytes: bytes,
        filename: str,
        submission_id: Optional[str] = None,
        run_async: bool = True,
    ) -> JobRecord:
        """Validate input file, create job record, and dispatch processing to background worker.

        Args:
            file_bytes: Raw bytes of uploaded PDF.
            filename: Original client filename.
            submission_id: Optional user-supplied submission identifier.
            run_async: If True, dispatch to thread pool; if False, run synchronously.

        Returns:
            JobRecord tracking the job state.
        """
        # 1. Enforce file size, extension, and magic byte validation
        self.validator.validate_file_content(file_bytes, filename)
        clean_sub_id = self.validator.sanitize_submission_id(submission_id)

        # 2. Register job record and allocate isolated workspace
        job = self.store.create_job(submission_id=clean_sub_id)
        job_dir = self.validator.create_job_storage(job.job_id)
        job.temp_dir = job_dir

        # 3. Save uploaded PDF safely to disk
        pdf_path = job_dir / "submission.pdf"
        pdf_path.write_bytes(file_bytes)
        self.store.persist(job)

        # 4. Dispatch processing
        self._dispatch(job, run_async)
        return job

    def _dispatch(self, job: JobRecord, run_async: bool = True) -> None:
        """Run the pipeline for a job whose workspace already contains submission.pdf."""
        job_dir = Path(job.temp_dir)
        output_dir = job_dir / "artifacts"
        output_dir.mkdir(parents=True, exist_ok=True)
        args = (job.job_id, job.submission_id, str(job_dir / "submission.pdf"), str(output_dir))
        if run_async:
            job._future = self._executor.submit(self._execute_job, *args)
        else:
            self._execute_job(*args)

    def _get_or_recover(self, job_id: str) -> Optional[JobRecord]:
        """Return the in-memory job, or restore it from its workspace after a service restart.

        - Finished job with a persisted result/status -> restored as-is.
        - Workspace with submission.pdf but no finished state (service stopped mid-run, or the job
          predates persistence) -> OCR is re-run in the background; callers see 'queued'.
        """
        job = self.store.get_job(job_id)
        if job is not None or not _JOB_ID_RE.match(job_id or ""):
            return job

        with self._recover_lock:
            job = self.store.get_job(job_id)
            if job is not None:
                return job

            job_dir = Path(self.config.storage_root).resolve() / job_id
            if not job_dir.is_dir():
                return None

            meta: dict = {}
            try:
                meta = json.loads((job_dir / JOB_META_FILENAME).read_text(encoding="utf-8"))
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.warning("Ignoring unreadable %s for job %s: %s", JOB_META_FILENAME, job_id, e)

            submission_id = meta.get("submission_id")
            if not submission_id:
                # Older workspaces have no job.json; the orchestrator names artifacts/<submission_id>/
                subdirs = [p.name for p in (job_dir / "artifacts").glob("*") if p.is_dir()]
                submission_id = subdirs[0] if len(subdirs) == 1 else job_id
            try:
                submission_id = self.validator.sanitize_submission_id(submission_id)
            except Exception:
                submission_id = job_id

            record = JobRecord(job_id=job_id, submission_id=submission_id, temp_dir=job_dir)
            status = meta.get("status")
            result_path = job_dir / JOB_RESULT_FILENAME

            if status in _FINISHED_STATUSES and (status in ("failed", "cancelled") or result_path.exists()):
                for key in ("status", "stage", "progress", "created_at", "updated_at", "error"):
                    if meta.get(key) is not None:
                        setattr(record, key, meta[key])
                record.warnings = list(meta.get("warnings") or [])
                if result_path.exists():
                    try:
                        record.result = OCRDocumentResult.model_validate_json(result_path.read_text(encoding="utf-8"))
                    except Exception as e:
                        logger.warning("Persisted result for job %s is unreadable (%s); re-running OCR.", job_id, e)
                        record = JobRecord(job_id=job_id, submission_id=submission_id, temp_dir=job_dir)
                if record.status in _FINISHED_STATUSES:
                    logger.info("Restored finished job %s (%s) from disk.", job_id, record.status)
                    return self.store.register(record)

            if not (job_dir / "submission.pdf").is_file():
                return None

            logger.info("Job %s was not finished before a restart; re-running OCR from its saved PDF.", job_id)
            record = self.store.register(record)
            self.store.persist(record)
            self._dispatch(record, run_async=True)
            return record

    def _execute_job(
        self,
        job_id: str,
        submission_id: str,
        pdf_path: str,
        output_dir: str,
    ) -> None:
        """Worker thread entry point executing the full orchestrator pipeline."""
        logger.info("[Worker] Starting processing for job %s...", job_id)
        try:
            self.store.update_progress(job_id, "ingestion", 5)

            def progress_cb(stage: str, percent: int) -> None:
                self.store.update_progress(job_id, stage, percent)

            result = self.orchestrator.process_submission(
                pdf_path=pdf_path,
                submission_id=submission_id,
                output_dir=output_dir,
                job_id=job_id,
                progress_callback=progress_cb,
            )

            self.store.complete_job(job_id, result)

        except Exception as e:
            logger.exception("[Worker] Unhandled failure processing job %s: %s", job_id, e)
            self.store.fail_job(job_id, str(e))

    def get_job_status(self, job_id: str) -> Optional[JobStatusResponse]:
        """Query the current state of a job."""
        job = self._get_or_recover(job_id)
        if not job:
            return None

        return JobStatusResponse(
            job_id=job.job_id,
            submission_id=job.submission_id,
            status=job.status,
            stage=job.stage,
            progress=job.progress,
            created_at=job.created_at,
            updated_at=job.updated_at,
            error=job.error,
            warnings=job.warnings,
        )

    def get_job_result(self, job_id: str) -> Optional[OCRDocumentResult]:
        """Retrieve completed OCRDocumentResult if available."""
        job = self._get_or_recover(job_id)
        if not job:
            return None
        return job.result

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or active job."""
        return self.store.cancel_job(job_id)

    def get_active_count(self) -> int:
        """Return count of currently active jobs."""
        return self.store.count_active_jobs()
