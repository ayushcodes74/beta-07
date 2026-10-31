"""Supabase implementation of SubmissionRepository and related models.

Maps to existing Supabase tables:
- submissions (id, assignment_id, student_id, assignment_version_id, pdf_path, status, submitted_at, created_at, updated_at)
- submission_answers (id, submission_id, question_id, answer_text, selected_option_id, created_at, updated_at)
- ocr_jobs (id, submission_id, status, ..., processing_metadata jsonb NOT NULL, created_at, updated_at)
  `id` is a database UUID. The OCR engine's job id ("job-<hex>") plus `stage`/`progress`
  are kept in `processing_metadata`, since the table has no columns for them.

Enforces:
- One submission per student per assignment.
- One OCR job per submission.
- Real question UUID references.
- Student data isolation under RLS.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from app.database.supabase import get_user_supabase
from app.services.submission_service import (
    SubmissionIntegrationNotConfiguredError,
    SubmissionRecord,
    SubmissionRepository,
    SubmissionRepositoryError,
    SubmissionValidationError,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Database Record Models
# --------------------------------------------------------------------------


class SubmissionAnswerRecord(BaseModel):
    """Database representation of a student question response in submission_answers."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    submission_id: UUID
    question_id: UUID
    answer_text: Optional[str] = None
    selected_option_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Status mapping between the API/OCR engine and the database CHECK constraints
# ---------------------------------------------------------------------------
# The API (and frontend) use OCR-centric submission statuses such as "ocr_queued" and
# "ocr_degraded". The database models two separate things:
#   submissions.status IN (submitted, late_pending, late_accepted, late_rejected,
#                          under_review, graded, published)        -- grading lifecycle
#   ocr_jobs.status    IN (pending, processing, completed, failed, needs_review)
# While OCR is involved the submission stays "submitted"; the OCR engine's exact status
# is kept in ocr_jobs.processing_metadata.engine_status and mapped back on read.

_DB_SUBMISSION_STATUSES = {
    "submitted", "late_pending", "late_accepted", "late_rejected", "under_review", "graded", "published",
}

_ENGINE_TO_DB_OCR_STATUS = {
    "queued": "pending",
    "processing": "processing",
    "completed": "completed",
    "completed_with_warnings": "completed",
    "degraded": "needs_review",
    "failed": "failed",
    "cancelled": "failed",
}

_DB_OCR_TO_ENGINE_STATUS = {
    "pending": "queued",
    "processing": "processing",
    "completed": "completed",
    "needs_review": "degraded",
    "failed": "failed",
}

_OCR_TERMINAL_STATUSES = {"completed", "completed_with_warnings", "degraded", "failed", "cancelled"}


def _db_submission_status(api_status: str) -> str:
    """API submission status -> submissions.status value allowed by the database."""
    if api_status in _DB_SUBMISSION_STATUSES:
        return api_status
    # OCR stages ("ocr_queued", "ocr_degraded", ...) precede teacher review.
    return "submitted"


def _engine_status(api_status: str) -> str:
    return api_status.removeprefix("ocr_")


def _job_metadata(ocr_job_id: str, engine_status: str) -> dict[str, Any]:
    return {
        "ocr_job_id": str(ocr_job_id),
        "engine_status": engine_status,
        "stage": engine_status,
        "progress": 100 if engine_status in _OCR_TERMINAL_STATUSES else 0,
    }


def _job_engine_status(job_row: dict[str, Any]) -> str:
    metadata = job_row.get("processing_metadata") if isinstance(job_row.get("processing_metadata"), dict) else {}
    return str(metadata.get("engine_status") or _DB_OCR_TO_ENGINE_STATUS.get(str(job_row.get("status")), "queued"))


# Statuses in which a student may still replace their submission (mirrors the
# "Students update editable submissions" policy on public.submissions).
_RESUBMITTABLE_DB_STATUSES = {"submitted", "late_pending"}


# "*" rather than a column list: the late_* columns come from phase3b_late_submissions.sql, and
# selecting them by name would break every submission query on a database without that migration.
_SUBMISSION_COLUMNS = "*"


def _late_decision_locked(exc: Exception) -> bool:
    """Raised by the submissions_late_guard trigger when a judged late submission is replaced."""
    return "late_decision_locked" in str(exc)


def _optional_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_unique_violation(exc: Exception) -> bool:
    return getattr(exc, "code", None) == "23505" or "duplicate key value" in str(exc)


def _storage_error(exc: Exception, message: str) -> Exception:
    """Map a Supabase failure to the repository error the API layer expects.

    PGRST301 / "No suitable key" means the project cannot verify the caller's JWT (auth
    integration not configured), which is reported as 503 service_unavailable rather than
    a storage failure. Applied to every query so the first query in a flow decides it.
    """
    text = str(exc)
    if "PGRST301" in text or "No suitable key" in text:
        return SubmissionIntegrationNotConfiguredError("Supabase JWT verification is not configured on remote host")
    return SubmissionRepositoryError(message)


def _api_submission_status(sub_row: dict[str, Any], job_row: Optional[dict[str, Any]]) -> str:
    """submissions row (+ its ocr_jobs row) -> the API status the rest of the backend expects."""
    db_status = str(sub_row["status"])
    if db_status != "submitted" or job_row is None:
        return db_status
    return f"ocr_{_job_engine_status(job_row)}"


def _engine_job_id(job_row: dict[str, Any]) -> Optional[str]:
    """OCR engine job id stored in ocr_jobs.processing_metadata (the row id is a separate DB UUID)."""
    metadata = job_row.get("processing_metadata") or {}
    job_id = metadata.get("ocr_job_id") if isinstance(metadata, dict) else None
    return str(job_id) if job_id else None


def _filename_from_row(row: dict[str, Any]) -> str:
    """submissions has no filename column; derive a display name from pdf_path when present."""
    pdf_path = row.get("pdf_path")
    return str(pdf_path).rsplit("/", 1)[-1] if pdf_path else "submission.pdf"


class OCRJobRecord(BaseModel):
    """Database representation of an OCR processing job in ocr_jobs."""

    model_config = ConfigDict(frozen=True)

    id: str
    submission_id: UUID
    status: str
    stage: str = "queued"
    progress: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# --------------------------------------------------------------------------
# Supabase Repository Implementation
# --------------------------------------------------------------------------


class SupabaseSubmissionRepository:
    """Supabase-backed submission repository operating under caller's JWT/RLS context."""

    @staticmethod
    def _client(access_token: str):
        try:
            return get_user_supabase(access_token)
        except Exception as exc:
            raise SubmissionIntegrationNotConfiguredError(str(exc)) from exc

    @staticmethod
    def _ocr_jobs(client: Any, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """submission id -> its ocr_jobs row (status + processing_metadata)."""
        submission_ids = [str(row["id"]) for row in rows]
        jobs: dict[str, dict[str, Any]] = {}
        for start in range(0, len(submission_ids), 100):  # keep the in.(...) filter URL short
            response = (
                client.table("ocr_jobs")
                .select("submission_id, status, processing_metadata")
                .in_("submission_id", submission_ids[start : start + 100])
                .execute()
            )
            jobs.update({str(row["submission_id"]): row for row in (response.data or [])})
        return jobs

    @staticmethod
    def _record(row: dict[str, Any], job_row: Optional[dict[str, Any]]) -> SubmissionRecord:
        return SubmissionRecord(
            id=UUID(str(row["id"])),
            assignment_id=UUID(str(row["assignment_id"])),
            student_id=UUID(str(row["student_id"])),
            filename=_filename_from_row(row),
            ocr_job_id=_engine_job_id(job_row) if job_row else None,
            status=_api_submission_status(row, job_row),
            created_at=row.get("created_at") or "",
            updated_at=row.get("updated_at") or "",
            submitted_at=row.get("submitted_at"),
            late_status=row.get("late_status"),
            late_penalty_percent=_optional_float(row.get("late_penalty_percent")),
            late_decision_note=row.get("late_decision_note"),
            late_decided_at=row.get("late_decided_at"),
        )

    @staticmethod
    def _reuse_existing_submission(
        client: Any, assignment_id: UUID, student_id: UUID, status: str, now_str: str
    ) -> UUID:
        """Resubmission: refresh the student's existing submission if it is still editable."""
        existing = (
            client.table("submissions")
            .select("id, status")
            .eq("assignment_id", str(assignment_id))
            .eq("student_id", str(student_id))
            .execute()
        ).data or []
        if not existing:
            raise SubmissionRepositoryError("Duplicate submission reported but no existing row is visible")
        row = existing[0]
        if row["status"] not in _RESUBMITTABLE_DB_STATUSES:
            raise SubmissionValidationError(
                "already_submitted",
                "You have already submitted this assignment and it is being reviewed, so it can no longer be replaced.",
            )
        client.table("submissions").update(
            {"status": _db_submission_status(status), "submitted_at": now_str, "updated_at": now_str}
        ).eq("id", str(row["id"])).execute()
        return UUID(str(row["id"]))

    @staticmethod
    def _save_ocr_job(
        client: Any, submission_id: UUID, ocr_job_id: str, engine_status: str, now_str: str
    ) -> None:
        """Write the submission's single ocr_jobs row: update if present, otherwise insert.

        Avoids upsert/ON CONFLICT, which would require a unique constraint on submission_id.
        """
        job_fields = {
            "status": _ENGINE_TO_DB_OCR_STATUS.get(engine_status, "needs_review"),
            "processing_metadata": _job_metadata(ocr_job_id, engine_status),
            "updated_at": now_str,
        }
        updated = (
            client.table("ocr_jobs")
            .update(job_fields)
            .eq("submission_id", str(submission_id))
            .execute()
        )
        if not updated.data:
            client.table("ocr_jobs").insert(
                {"submission_id": str(submission_id), "created_at": now_str, **job_fields}
            ).execute()

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
    ) -> SubmissionRecord:
        """Create a submission record and associated initial OCR job."""
        client = self._client(access_token)
        now_str = datetime.now(UTC).isoformat()

        try:
            # 1. Insert into submissions. The table allows one submission per student per
            #    assignment; a resubmission reuses the existing row while it is still editable.
            sub_payload = {
                "id": str(submission_id),
                "assignment_id": str(assignment_id),
                "student_id": str(student_id),
                "status": _db_submission_status(status),
                "submitted_at": now_str,
                "created_at": now_str,
                "updated_at": now_str,
            }
            try:
                client.table("submissions").insert(sub_payload).execute()
            except Exception as exc:
                if not _is_unique_violation(exc):
                    raise
                submission_id = self._reuse_existing_submission(
                    client, assignment_id, student_id, status, now_str
                )

            # 2. Record the OCR job for this (new or reused) submission
            if ocr_job_id:
                engine_status = _engine_status(status) if status.startswith("ocr_") else "queued"
                self._save_ocr_job(client, submission_id, ocr_job_id, engine_status, now_str)

            return SubmissionRecord(
                id=submission_id,
                assignment_id=assignment_id,
                student_id=student_id,
                filename=filename,
                ocr_job_id=ocr_job_id,
                status=status,
                created_at=now_str,
                updated_at=now_str,
            )
        except (SubmissionRepositoryError, SubmissionValidationError):
            raise
        except Exception as exc:
            if _late_decision_locked(exc):
                raise SubmissionValidationError(
                    "late_decision_locked",
                    "Your teacher has already decided on this late submission, so it can no longer be replaced.",
                ) from None
            logger.exception("Failed to create submission in Supabase: %s", exc)
            raise _storage_error(exc, "Failed to create submission") from exc

    def get(self, submission_id: UUID, *, access_token: str) -> Optional[SubmissionRecord]:
        """Fetch submission by ID along with its associated OCR job ID."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("submissions")
                .select(_SUBMISSION_COLUMNS)
                .eq("id", str(submission_id))
                .execute()
            )
            data = resp.data
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data

            # Fetch linked OCR job (engine job id + status)
            job_resp = (
                client.table("ocr_jobs")
                .select("submission_id, status, processing_metadata")
                .eq("submission_id", str(submission_id))
                .execute()
            )
            job_row = None
            if job_resp.data:
                job_row = job_resp.data[0] if isinstance(job_resp.data, list) else job_resp.data

            return self._record(row, job_row)
        except Exception as exc:
            logger.exception("Failed to get submission from Supabase: %s", exc)
            raise _storage_error(exc, "Failed to fetch submission") from exc

    def list_by_assignment(
        self, assignment_id: UUID, *, access_token: str
    ) -> List[SubmissionRecord]:
        """List all submissions for a given assignment."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("submissions")
                .select(_SUBMISSION_COLUMNS)
                .eq("assignment_id", str(assignment_id))
                .execute()
            )
            rows = resp.data or []
            jobs = self._ocr_jobs(client, rows)
            return [self._record(r, jobs.get(str(r["id"]))) for r in rows]
        except Exception as exc:
            logger.exception("Failed to list submissions by assignment: %s", exc)
            raise _storage_error(exc, "Failed to list submissions") from exc

    def list_by_assignments(
        self, assignment_ids: List[UUID], *, access_token: str
    ) -> List[SubmissionRecord]:
        """Submissions for many assignments: one query per 100 assignments, not one per assignment."""
        if not assignment_ids:
            return []
        client = self._client(access_token)
        ids = [str(a) for a in assignment_ids]
        rows: list[dict[str, Any]] = []
        try:
            for start in range(0, len(ids), 100):  # keep the in.(...) filter URL short
                resp = (
                    client.table("submissions")
                    .select(_SUBMISSION_COLUMNS)
                    .in_("assignment_id", ids[start : start + 100])
                    .execute()
                )
                rows.extend(resp.data or [])
            jobs = self._ocr_jobs(client, rows)
            return [self._record(r, jobs.get(str(r["id"]))) for r in rows]
        except Exception as exc:
            logger.exception("Failed to list submissions by assignments: %s", exc)
            raise _storage_error(exc, "Failed to list submissions") from exc

    def list_by_student(
        self, student_id: UUID, *, access_token: str
    ) -> List[SubmissionRecord]:
        """List submissions belonging to a student (strictly self-scoped under RLS)."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("submissions")
                .select(_SUBMISSION_COLUMNS)
                .eq("student_id", str(student_id))
                .execute()
            )
            rows = resp.data or []
            jobs = self._ocr_jobs(client, rows)
            return [self._record(r, jobs.get(str(r["id"]))) for r in rows]
        except Exception as exc:
            logger.exception("Failed to list submissions by student: %s", exc)
            raise _storage_error(exc, "Failed to list student submissions") from exc

    def update_status(
        self,
        submission_id: UUID,
        status: str,
        ocr_job_id: Optional[str] = None,
        *,
        access_token: str,
    ) -> Optional[SubmissionRecord]:
        """Update submission lifecycle status and optional OCR job state."""
        client = self._client(access_token)
        now_str = datetime.now(UTC).isoformat()
        try:
            update_payload: Dict[str, Any] = {
                "status": _db_submission_status(status),
                "updated_at": now_str,
            }
            resp = (
                client.table("submissions")
                .update(update_payload)
                .eq("id", str(submission_id))
                .execute()
            )
            if not resp.data:
                return None

            # Record OCR progress on the submission's ocr_jobs row. Update first and insert only if
            # missing, so this does not depend on a unique constraint for ON CONFLICT.
            if ocr_job_id and status.startswith("ocr_"):
                self._save_ocr_job(client, submission_id, ocr_job_id, _engine_status(status), now_str)

            return self.get(submission_id, access_token=access_token)
        except Exception as exc:
            logger.exception("Failed to update submission status in Supabase: %s", exc)
            raise _storage_error(exc, "Failed to update submission status") from exc

    def set_late_decision(
        self,
        submission_id: UUID,
        late_status: str,
        penalty_percent: Optional[float],
        note: Optional[str],
        *,
        access_token: str,
    ) -> Optional[SubmissionRecord]:
        """Write the teacher's late decision. The trigger stamps late_decided_by / late_decided_at."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("submissions")
                .update(
                    {
                        "late_status": late_status,
                        "late_penalty_percent": penalty_percent,
                        "late_decision_note": note,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                )
                .eq("id", str(submission_id))
                .execute()
            )
            if not resp.data:
                return None
            return self.get(submission_id, access_token=access_token)
        except Exception as exc:
            text = str(exc)
            if "not_late" in text:
                raise SubmissionValidationError("not_late", "This submission was handed in on time.") from None
            if "late_status" in text and ("PGRST204" in text or "column" in text):
                logger.error("Late-submission columns missing: run backend/phase3b_late_submissions.sql")
                raise SubmissionIntegrationNotConfiguredError("late-submission columns are missing") from exc
            logger.exception("Failed to save late decision: %s", exc)
            raise _storage_error(exc, "Failed to save late decision") from exc

    def get_student_answers(
        self, submission_id: UUID, *, access_token: str
    ) -> List[SubmissionAnswerRecord]:
        """Retrieve question-level student answers from submission_answers."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("submission_answers")
                .select("id, submission_id, question_id, answer_text, selected_option_id, created_at, updated_at")
                .eq("submission_id", str(submission_id))
                .execute()
            )
            rows = resp.data or []
            return [
                SubmissionAnswerRecord(
                    id=UUID(str(r["id"])),
                    submission_id=UUID(str(r["submission_id"])),
                    question_id=UUID(str(r["question_id"])),
                    answer_text=r.get("answer_text"),
                    selected_option_id=r.get("selected_option_id"),
                    created_at=r.get("created_at"),
                    updated_at=r.get("updated_at"),
                )
                for r in rows
            ]
        except Exception as exc:
            logger.exception("Failed to get student answers: %s", exc)
            raise _storage_error(exc, "Failed to get student answers") from exc

    def save_student_answers(
        self, submission_id: UUID, answers: List[Dict[str, Any]], *, access_token: str
    ) -> int:
        """Upsert student answer records for this submission."""
        client = self._client(access_token)
        now_str = datetime.now(UTC).isoformat()
        try:
            records = []
            for ans in answers:
                records.append(
                    {
                        "id": str(ans.get("id") or uuid4()),
                        "submission_id": str(submission_id),
                        "question_id": str(ans["question_id"]),
                        "answer_text": ans.get("answer_text"),
                        "selected_option_id": ans.get("selected_option_id"),
                        "created_at": now_str,
                        "updated_at": now_str,
                    }
                )
            if not records:
                return 0
            resp = client.table("submission_answers").upsert(records).execute()
            return len(resp.data) if hasattr(resp, "data") and resp.data else len(records)
        except Exception as exc:
            logger.exception("Failed to save student answers: %s", exc)
            raise _storage_error(exc, "Failed to save student answers") from exc

    def get_ocr_job(
        self, submission_id: UUID, *, access_token: str
    ) -> Optional[OCRJobRecord]:
        """Retrieve the OCR processing job record for a submission."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("ocr_jobs")
                .select("id, submission_id, status, processing_metadata, created_at, updated_at")
                .eq("submission_id", str(submission_id))
                .execute()
            )
            data = resp.data
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data
            raw_metadata = row.get("processing_metadata")
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            engine_status = _job_engine_status(row)
            done = engine_status in _OCR_TERMINAL_STATUSES
            return OCRJobRecord(
                id=_engine_job_id(row) or str(row["id"]),
                submission_id=UUID(str(row["submission_id"])),
                status=engine_status,
                stage=str(metadata.get("stage") or engine_status),
                progress=int(metadata.get("progress", 100 if done else 0)),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
        except Exception as exc:
            logger.exception("Failed to get OCR job for submission: %s", exc)
            raise _storage_error(exc, "Failed to get OCR job") from exc

    def verify_submission_assignment(
        self, submission_id: UUID, assignment_id: UUID, *, access_token: str
    ) -> bool:
        """Verify that a submission belongs to the specified assignment."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("submissions")
                .select("id")
                .eq("id", str(submission_id))
                .eq("assignment_id", str(assignment_id))
                .execute()
            )
            return bool(resp.data)
        except Exception as exc:
            logger.exception("Failed to verify submission assignment link: %s", exc)
            return False
