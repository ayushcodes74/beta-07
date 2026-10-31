"""Supabase implementation of SubmissionRepository and related models.

Maps to existing Supabase tables:
- submissions (id, assignment_id, student_id, filename, status, created_at, updated_at)
- submission_answers (id, submission_id, question_id, answer_text, selected_option_id, created_at, updated_at)
- ocr_jobs (id, submission_id, status, stage, progress, created_at, updated_at)

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
            # 1. Insert into submissions
            sub_payload = {
                "id": str(submission_id),
                "assignment_id": str(assignment_id),
                "student_id": str(student_id),
                "filename": filename,
                "status": status,
                "created_at": now_str,
                "updated_at": now_str,
            }
            client.table("submissions").insert(sub_payload).execute()

            # 2. Upsert into ocr_jobs if job ID is known (one per submission)
            if ocr_job_id:
                job_payload = {
                    "id": str(ocr_job_id),
                    "submission_id": str(submission_id),
                    "status": "queued",
                    "stage": "queued",
                    "progress": 0,
                    "created_at": now_str,
                    "updated_at": now_str,
                }
                client.table("ocr_jobs").upsert(job_payload, on_conflict="submission_id").execute()

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
        except SubmissionRepositoryError:
            raise
        except Exception as exc:
            err_msg = str(exc)
            if "PGRST301" in err_msg or "No suitable key" in err_msg:
                raise SubmissionIntegrationNotConfiguredError("Supabase JWT verification is not configured on remote host") from exc
            logger.exception("Failed to create submission in Supabase: %s", exc)
            raise SubmissionRepositoryError("Failed to create submission") from exc

    def get(self, submission_id: UUID, *, access_token: str) -> Optional[SubmissionRecord]:
        """Fetch submission by ID along with its associated OCR job ID."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("submissions")
                .select("id, assignment_id, student_id, filename, status, created_at, updated_at")
                .eq("id", str(submission_id))
                .execute()
            )
            data = resp.data
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data

            # Fetch linked OCR job id
            job_resp = (
                client.table("ocr_jobs")
                .select("id")
                .eq("submission_id", str(submission_id))
                .execute()
            )
            job_id = None
            if job_resp.data:
                job_row = job_resp.data[0] if isinstance(job_resp.data, list) else job_resp.data
                job_id = str(job_row["id"])

            return SubmissionRecord(
                id=UUID(str(row["id"])),
                assignment_id=UUID(str(row["assignment_id"])),
                student_id=UUID(str(row["student_id"])),
                filename=row["filename"],
                ocr_job_id=job_id,
                status=row["status"],
                created_at=row.get("created_at") or "",
                updated_at=row.get("updated_at") or "",
            )
        except Exception as exc:
            logger.exception("Failed to get submission from Supabase: %s", exc)
            raise SubmissionRepositoryError("Failed to fetch submission") from exc

    def list_by_assignment(
        self, assignment_id: UUID, *, access_token: str
    ) -> List[SubmissionRecord]:
        """List all submissions for a given assignment."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("submissions")
                .select("id, assignment_id, student_id, filename, status, created_at, updated_at")
                .eq("assignment_id", str(assignment_id))
                .execute()
            )
            rows = resp.data or []
            return [
                SubmissionRecord(
                    id=UUID(str(r["id"])),
                    assignment_id=UUID(str(r["assignment_id"])),
                    student_id=UUID(str(r["student_id"])),
                    filename=r["filename"],
                    ocr_job_id=None,
                    status=r["status"],
                    created_at=r.get("created_at") or "",
                    updated_at=r.get("updated_at") or "",
                )
                for r in rows
            ]
        except Exception as exc:
            logger.exception("Failed to list submissions by assignment: %s", exc)
            raise SubmissionRepositoryError("Failed to list submissions") from exc

    def list_by_student(
        self, student_id: UUID, *, access_token: str
    ) -> List[SubmissionRecord]:
        """List submissions belonging to a student (strictly self-scoped under RLS)."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("submissions")
                .select("id, assignment_id, student_id, filename, status, created_at, updated_at")
                .eq("student_id", str(student_id))
                .execute()
            )
            rows = resp.data or []
            return [
                SubmissionRecord(
                    id=UUID(str(r["id"])),
                    assignment_id=UUID(str(r["assignment_id"])),
                    student_id=UUID(str(r["student_id"])),
                    filename=r["filename"],
                    ocr_job_id=None,
                    status=r["status"],
                    created_at=r.get("created_at") or "",
                    updated_at=r.get("updated_at") or "",
                )
                for r in rows
            ]
        except Exception as exc:
            logger.exception("Failed to list submissions by student: %s", exc)
            raise SubmissionRepositoryError("Failed to list student submissions") from exc

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
                "status": status,
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

            # Upsert ocr_jobs if job id is supplied
            if ocr_job_id:
                client.table("ocr_jobs").upsert(
                    {
                        "id": str(ocr_job_id),
                        "submission_id": str(submission_id),
                        "status": status.removeprefix("ocr_"),
                        "updated_at": now_str,
                    },
                    on_conflict="submission_id",
                ).execute()

            return self.get(submission_id, access_token=access_token)
        except Exception as exc:
            logger.exception("Failed to update submission status in Supabase: %s", exc)
            raise SubmissionRepositoryError("Failed to update submission status") from exc

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
            raise SubmissionRepositoryError("Failed to get student answers") from exc

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
            raise SubmissionRepositoryError("Failed to save student answers") from exc

    def get_ocr_job(
        self, submission_id: UUID, *, access_token: str
    ) -> Optional[OCRJobRecord]:
        """Retrieve the OCR processing job record for a submission."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("ocr_jobs")
                .select("id, submission_id, status, stage, progress, created_at, updated_at")
                .eq("submission_id", str(submission_id))
                .execute()
            )
            data = resp.data
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data
            return OCRJobRecord(
                id=str(row["id"]),
                submission_id=UUID(str(row["submission_id"])),
                status=str(row["status"]),
                stage=str(row.get("stage") or "done"),
                progress=int(row.get("progress") or 100),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
        except Exception as exc:
            logger.exception("Failed to get OCR job for submission: %s", exc)
            raise SubmissionRepositoryError("Failed to get OCR job") from exc

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
