"""Submission management and OCR integration business logic (Module 5 Backend Integration).

Enforces:
  - Role-based submission creation (Students only).
  - Published assignment access validation.
  - Asynchronous OCR job dispatch.
  - Strict student-to-student data isolation (students can never access another student's submission).
  - Teacher course-level ownership validation (teachers can only access submissions for assignments they own).
  - Repository abstraction pattern with UnconfiguredSubmissionRepository pending database owner schema confirmation.
  - Explicit 202 processing handling vs 200 completion without text fabrication.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
import logging
from typing import Any, Dict, List, Optional, Protocol, Union
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict

from app.schemas.integrity import IntegrityReport, OCRQualitySummary
from app.schemas.ocr import (
    JobStatusResponse,
    OCRDocumentResult,
    SubmissionOCRStatusResponse,
)
from app.schemas.user import Role
from app.services.assignment_service import (
    AssignmentNotFoundError,
    AssignmentPermissionError,
    AssignmentService,
    get_assignment_repository,
)
from app.services.auth_service import CurrentUser
from app.services.ocr_client import (
    OCRError,
    OCRInvalidFileError,
    OCRJobCancelledError,
    OCRJobFailedError,
    OCRJobNotFoundError,
    OCRServiceClient,
    OCRServiceUnavailableError,
    OCRTimeoutError,
    get_ocr_client,
)
from app.services.plagiarism import compare_ocr_documents, summarize_ocr

logger = logging.getLogger(__name__)

# Security & size limits
MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB limit
MIN_PDF_SIZE_BYTES = 10  # Minimum valid header bytes


class SubmissionRecord(BaseModel):
    """Internal submission record as stored in the repository."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    assignment_id: UUID
    student_id: UUID
    filename: str
    ocr_job_id: Optional[str] = None
    status: str = "submitted"  # 'submitted', 'ocr_queued', 'ocr_processing', 'ocr_completed', 'ocr_completed_with_warnings', 'ocr_degraded', 'ocr_failed', 'ocr_cancelled'
    created_at: str
    updated_at: str


class SubmissionRepositoryError(Exception):
    """Base exception for submission repository failures."""


class SubmissionIntegrationNotConfiguredError(SubmissionRepositoryError):
    """No confirmed submission repository is available yet."""


class SubmissionNotFoundError(Exception):
    """Submission does not exist or caller is unauthorized to view it."""


class SubmissionPermissionError(Exception):
    """User lacks required permissions for this submission."""


class SubmissionValidationError(Exception):
    """Submission rejected due to business validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SubmissionRepository(Protocol):
    """Protocol for submission persistence. access_token is the caller's verified Supabase token."""

    def create(
        self,
        submission_id: UUID,
        assignment_id: UUID,
        student_id: UUID,
        filename: str,
        ocr_job_id: Optional[str],
        status: str,
        *,
        access_token: str,
    ) -> SubmissionRecord: ...

    def get(self, submission_id: UUID, *, access_token: str) -> Optional[SubmissionRecord]: ...

    def list_by_assignment(
        self, assignment_id: UUID, *, access_token: str
    ) -> List[SubmissionRecord]: ...

    def list_by_student(
        self, student_id: UUID, *, access_token: str
    ) -> List[SubmissionRecord]: ...

    def update_status(
        self,
        submission_id: UUID,
        status: str,
        ocr_job_id: Optional[str] = None,
        *,
        access_token: str,
    ) -> Optional[SubmissionRecord]: ...


class UnconfiguredSubmissionRepository:
    """Placeholder repository until Person 4 / Database Owner confirms the submissions table contract."""

    def _fail(self, *args: Any, **kwargs: Any) -> Any:
        raise SubmissionIntegrationNotConfiguredError("submission repository is not configured")

    create = get = list_by_assignment = list_by_student = update_status = _fail


def get_submission_repository() -> SubmissionRepository:
    """Dependency provider returning the submission repository implementation."""
    from app.database.submission_repository import SupabaseSubmissionRepository

    return SupabaseSubmissionRepository()


class SubmissionService:
    """Coordinates student assignment submissions, OCR processing, and status tracking."""

    def __init__(
        self,
        repository: SubmissionRepository,
        assignment_service: AssignmentService,
        ocr_client: OCRServiceClient,
    ) -> None:
        self.repo = repository
        self.assignment_service = assignment_service
        self.ocr_client = ocr_client

    def list_submissions(self, user: CurrentUser, *, access_token: str) -> list[SubmissionRecord]:
        """List only the caller's submissions or submissions for their own assignments."""
        if user.role is Role.STUDENT:
            records = self.repo.list_by_student(user.id, access_token=access_token)
            return sorted(
                (record for record in records if record.student_id == user.id),
                key=lambda record: record.created_at,
                reverse=True,
            )
        if user.role is Role.TEACHER:
            assignments = self.assignment_service.list_for(user, access_token=access_token)
            assignment_ids = sorted(record.id for record in assignments if record.teacher_id == user.id)
            records = [
                submission
                for assignment_id in assignment_ids
                for submission in self.repo.list_by_assignment(assignment_id, access_token=access_token)
                if submission.assignment_id == assignment_id
            ]
            return sorted(records, key=lambda record: record.created_at, reverse=True)
        raise SubmissionPermissionError("Invalid role")

    async def submit_assignment_pdf(
        self,
        student: CurrentUser,
        assignment_id: UUID,
        filename: str,
        file_bytes: bytes,
        *,
        access_token: str,
    ) -> SubmissionRecord:
        """Submit a PDF assignment for OCR processing."""
        if student.role is not Role.STUDENT:
            raise SubmissionPermissionError("Only students can submit assignments")

        # Validation: File size
        if len(file_bytes) > MAX_PDF_SIZE_BYTES:
            raise SubmissionValidationError(
                "file_too_large",
                f"File size exceeds maximum allowed limit of {MAX_PDF_SIZE_BYTES // (1024 * 1024)} MB.",
            )
        if len(file_bytes) < MIN_PDF_SIZE_BYTES:
            raise SubmissionValidationError("file_too_small", "File is empty or truncated.")

        # Validation: Extension and magic bytes
        if not filename.lower().endswith(".pdf"):
            raise SubmissionValidationError("invalid_file_type", "Submission must be a PDF document (.pdf).")

        if not file_bytes.startswith(b"%PDF-"):
            raise SubmissionValidationError("invalid_pdf_header", "File content does not start with valid PDF magic bytes.")

        # 1. Verify student has access to the published assignment
        # get_for raises AssignmentNotFoundError if assignment is draft or inaccessible
        assignment = self.assignment_service.get_for(student, assignment_id, access_token=access_token)
        if not assignment:
            raise SubmissionNotFoundError("Assignment not found or inaccessible")

        submission_id = uuid4()

        # 2. Submit to OCR service
        try:
            job_resp = await self.ocr_client.submit_pdf(
                file_bytes=file_bytes,
                filename=filename,
                submission_id=str(submission_id),
                run_async=True,
            )
            ocr_job_id = job_resp.job_id
            initial_status = "ocr_queued"
        except OCRInvalidFileError as e:
            raise SubmissionValidationError("ocr_file_rejected", str(e)) from e
        except OCRError as e:
            logger.error("OCR service failed to accept submission: %s", type(e).__name__)
            raise

        # 3. Store submission record in repository
        record = self.repo.create(
            submission_id=submission_id,
            assignment_id=assignment_id,
            student_id=student.id,
            filename=filename,
            ocr_job_id=ocr_job_id,
            status=initial_status,
            access_token=access_token,
        )
        return record

    async def get_submission_status(
        self,
        user: CurrentUser,
        submission_id: UUID,
        *,
        access_token: str,
    ) -> SubmissionOCRStatusResponse:
        """Query submission status, enforcing student isolation and teacher course-level access."""
        submission = self.repo.get(submission_id, access_token=access_token)
        if not submission:
            raise SubmissionNotFoundError("Submission not found")

        self._check_access(user, submission, access_token=access_token)

        # Check latest OCR status if job is queued or processing
        ocr_stage = None
        ocr_progress = 0
        error_msg = None
        warnings: List[str] = []

        if submission.ocr_job_id:
            try:
                ocr_status = await self.ocr_client.get_job_status(submission.ocr_job_id)
                ocr_stage = ocr_status.stage
                ocr_progress = ocr_status.progress
                warnings = ocr_status.warnings
                error_msg = ocr_status.error

                # Map OCR status to submission status if changed
                mapped_status = f"ocr_{ocr_status.status}"
                if mapped_status != submission.status:
                    self.repo.update_status(
                        submission_id=submission.id,
                        status=mapped_status,
                        ocr_job_id=submission.ocr_job_id,
                        access_token=access_token,
                    )
                    submission = submission.model_copy(update={"status": mapped_status})
            except OCRError as e:
                logger.warning("Could not refresh live OCR status for job %s: %s", submission.ocr_job_id, e)

        return SubmissionOCRStatusResponse(
            submission_id=submission.id,
            assignment_id=submission.assignment_id,
            student_id=submission.student_id,
            status=submission.status,
            ocr_job_id=submission.ocr_job_id,
            ocr_stage=ocr_stage,
            ocr_progress=ocr_progress,
            warnings=warnings,
            error_message=error_msg,
            created_at=submission.created_at,
            updated_at=submission.updated_at,
        )

    async def get_submission_ocr_result(
        self,
        user: CurrentUser,
        submission_id: UUID,
        *,
        access_token: str,
    ) -> Union[OCRDocumentResult, JobStatusResponse]:
        """Retrieve completed OCR result, or 202 processing status, enforcing strict authorization."""
        submission = self.repo.get(submission_id, access_token=access_token)
        if not submission:
            raise SubmissionNotFoundError("Submission not found")

        self._check_access(user, submission, access_token=access_token)

        if not submission.ocr_job_id:
            raise SubmissionValidationError("no_ocr_job", "No OCR processing job associated with this submission.")

        # Returns either OCRDocumentResult (200) or JobStatusResponse (202 processing)
        res = await self.ocr_client.get_job_result(submission.ocr_job_id)
        return res

    async def analyze_submission_integrity(
        self,
        user: CurrentUser,
        submission_id: UUID,
        *,
        access_token: str,
    ) -> IntegrityReport:
        """Compare a teacher-owned submission with completed OCR from its assignment only."""
        submission = self.repo.get(submission_id, access_token=access_token)
        if not submission:
            raise SubmissionNotFoundError("Submission not found")
        self._check_access(user, submission, access_token=access_token)

        if not submission.ocr_job_id:
            raise SubmissionValidationError("no_ocr_job", "No OCR processing job is associated with this submission.")

        current_result = await self.ocr_client.get_job_result(submission.ocr_job_id)
        if isinstance(current_result, JobStatusResponse):
            return IntegrityReport(
                submission_id=submission.id,
                review_status="processing",
                comparisons_completed=0,
                comparisons_skipped=0,
                comparison_complete=False,
                ocr_quality=OCRQualitySummary(),
                notes=["Integrity analysis will be available when OCR processing is complete."],
            )

        other_submissions = [
            record
            for record in self.repo.list_by_assignment(submission.assignment_id, access_token=access_token)
            if record.id != submission.id and record.assignment_id == submission.assignment_id
        ]
        skipped = 0
        sources: list[SubmissionRecord] = []
        for record in other_submissions:
            if record.ocr_job_id:
                sources.append(record)
            else:
                skipped += 1

        semaphore = asyncio.Semaphore(5)

        async def load_source(
            record: SubmissionRecord,
        ) -> tuple[SubmissionRecord, OCRDocumentResult | None]:
            async with semaphore:
                try:
                    result = await self.ocr_client.get_job_result(record.ocr_job_id or "")
                except (OCRJobCancelledError, OCRJobFailedError, OCRJobNotFoundError):
                    return record, None
                return record, result if isinstance(result, OCRDocumentResult) else None

        loaded_sources = await asyncio.gather(*(load_source(record) for record in sources))
        evidence = []
        comparisons_completed = 0
        for source_record, source_result in loaded_sources:
            if source_result is None:
                skipped += 1
                continue
            comparisons_completed += 1
            matches, _ = compare_ocr_documents(
                submission.id,
                current_result,
                source_record.id,
                source_result,
            )
            evidence.extend(matches)

        evidence.sort(key=lambda item: (-item.exact_match_score, item.source_submission_id.hex))
        quality = summarize_ocr(current_result)
        notes = [
            "This compares OCR text only with submissions for the same assignment; it does not search the internet.",
            "Text similarity is a review signal, not a finding of misconduct. Semantic embeddings are not configured.",
            "Printed OCR regions are excluded to reduce repeated question-prompt matches; question-level answer alignment is unavailable.",
            "Results are computed on request and are not persisted; no teacher decision or audit history is recorded yet.",
        ]
        if skipped:
            notes.append(f"{skipped} same-assignment submission(s) could not be compared because OCR was unavailable or incomplete.")
        if quality.low_confidence_regions or quality.unreadable_pages or quality.missing_pages:
            notes.append("OCR uncertainty or page gaps may affect these comparisons; verify the original scan.")

        return IntegrityReport(
            submission_id=submission.id,
            review_status="needs_teacher_review" if evidence else "no_matches",
            comparisons_completed=comparisons_completed,
            comparisons_skipped=skipped,
            comparison_complete=skipped == 0,
            ocr_quality=quality,
            evidence=evidence,
            notes=notes,
        )

    async def cancel_submission_ocr_job(
        self,
        user: CurrentUser,
        submission_id: UUID,
        *,
        access_token: str,
    ) -> Dict[str, str]:
        """Cancel an active OCR processing job (student who submitted or teacher owning assignment)."""
        submission = self.repo.get(submission_id, access_token=access_token)
        if not submission:
            raise SubmissionNotFoundError("Submission not found")

        self._check_access(user, submission, access_token=access_token)

        if not submission.ocr_job_id:
            raise SubmissionValidationError("no_ocr_job", "No OCR processing job associated with this submission.")

        resp = await self.ocr_client.cancel_job(submission.ocr_job_id)

        # Update repository status
        self.repo.update_status(
            submission_id=submission.id,
            status="ocr_cancelled",
            ocr_job_id=submission.ocr_job_id,
            access_token=access_token,
        )
        return resp

    def _check_access(self, user: CurrentUser, submission: SubmissionRecord, *, access_token: str) -> None:
        """Enforce access control rules:

        - Students can only see their own submissions.
        - Teachers can only see submissions for assignments they own.
        - Unauthorized requests return 404 (SubmissionNotFoundError) per privacy convention.
        """
        if user.role is Role.STUDENT:
            if submission.student_id != user.id:
                raise SubmissionNotFoundError("Submission not found")
        elif user.role is Role.TEACHER:
            self._check_teacher_assignment_ownership(user, submission.assignment_id, access_token=access_token)
        else:
            raise SubmissionPermissionError("Invalid role")

    def _check_teacher_assignment_ownership(
        self, teacher: CurrentUser, assignment_id: UUID, *, access_token: str
    ) -> None:
        """Verify that teacher owns the assignment; raise 404 if not found or not owned."""
        try:
            assignment = self.assignment_service.get_for(teacher, assignment_id, access_token=access_token)
            if not assignment:
                raise SubmissionNotFoundError("Assignment not found")
        except AssignmentNotFoundError:
            raise SubmissionNotFoundError("Assignment not found")
