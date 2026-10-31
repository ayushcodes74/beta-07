"""Asynchronous background job manager executing OCR processing tasks via ThreadPoolExecutor."""

from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
from typing import Optional

from app.api.config import APIConfig, DEFAULT_API_CONFIG
from app.api.schemas import JobStatusResponse, OCRDocumentResult
from app.api.security import SecurityValidator
from app.jobs.job_store import JobRecord, JobStore
from app.orchestration.ocr_orchestrator import OCROrchestrator

logger = logging.getLogger(__name__)


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

        output_dir = job_dir / "artifacts"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 4. Dispatch processing
        if run_async:
            future = self._executor.submit(
                self._execute_job,
                job.job_id,
                clean_sub_id,
                str(pdf_path),
                str(output_dir),
            )
            job._future = future
        else:
            self._execute_job(job.job_id, clean_sub_id, str(pdf_path), str(output_dir))

        return job

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
        job = self.store.get_job(job_id)
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
        job = self.store.get_job(job_id)
        if not job:
            return None
        return job.result

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or active job."""
        return self.store.cancel_job(job_id)

    def get_active_count(self) -> int:
        """Return count of currently active jobs."""
        return self.store.count_active_jobs()
