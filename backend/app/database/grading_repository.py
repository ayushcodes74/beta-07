"""Supabase implementation of GradingRepository and related models.

Maps strictly to existing Supabase table:
- grading_results (
    submission_id [PK],
    ai_score,
    final_score,
    ai_feedback,
    final_feedback,
    evidence [JSONB],
    flags [JSONB],
    confidence,
    status [TEXT: 'pending_review', 'approved', 'published', 'rejected'],
    reviewed_by,
    reviewed_at,
    published_at,
    created_at,
    updated_at
  )

Enforces:
- One grading result per submission (PK is submission_id).
- Safe duplicate handling via idempotent upsert on submission_id.
- Strict status validation: 'pending_review', 'approved', 'published', 'rejected'.
- Never introduces 'reviewed' or 'graded' statuses.
- Student data isolation: students cannot view unpublished grades.
- Teachers can only view/modify grading results for assignments they own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import logging
from typing import Any, Dict, List, Optional, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.database.supabase import get_user_supabase

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Grading Status & Exceptions
# --------------------------------------------------------------------------


class GradingStatus(StrEnum):
    """Authoritative grading lifecycle states in grading_results."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"


class GradingRepositoryError(Exception):
    """Base exception for grading repository failures."""


class InvalidGradingStatusError(GradingRepositoryError):
    """Raised when an unrecognized or forbidden grading status is supplied."""


class GradingResultNotFoundError(GradingRepositoryError):
    """Requested grading result does not exist."""


class GradingPermissionError(GradingRepositoryError):
    """User lacks authorization to view or mutate this grading result."""


# --------------------------------------------------------------------------
# Database Record Models
# --------------------------------------------------------------------------


class GradingResultRecord(BaseModel):
    """Immutable model representing an authoritative record from grading_results."""

    model_config = ConfigDict(frozen=True)

    submission_id: UUID
    ai_score: Decimal
    final_score: Decimal
    ai_feedback: str
    final_feedback: str
    evidence: Any  # JSONB: dict or list
    flags: Dict[str, Any]  # JSONB: dict
    confidence: Decimal
    status: GradingStatus
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[AwareDatetime] = None
    published_at: Optional[AwareDatetime] = None
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None


class GradingResultCreate(BaseModel):
    """Payload for creating or safely upserting a grading result."""

    submission_id: UUID
    ai_score: Decimal
    final_score: Optional[Decimal] = None
    ai_feedback: str
    final_feedback: Optional[str] = None
    evidence: Any = Field(default_factory=dict)
    flags: Dict[str, Any] = Field(default_factory=dict)
    confidence: Decimal
    status: GradingStatus = GradingStatus.PENDING_REVIEW

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, value: Any) -> GradingStatus:
        if isinstance(value, GradingStatus):
            return value
        if isinstance(value, str):
            try:
                return GradingStatus(value.lower().strip())
            except ValueError:
                pass
        raise InvalidGradingStatusError(f"Invalid grading status '{value}'. Allowed: {list(GradingStatus)}")


# --------------------------------------------------------------------------
# Repository Protocol
# --------------------------------------------------------------------------


class GradingRepository(Protocol):
    """Protocol for grading results persistence under caller's verified JWT/RLS context."""

    def insert(self, data: GradingResultCreate, *, access_token: str) -> GradingResultRecord: ...

    def get_by_submission_id(
        self, submission_id: UUID, *, access_token: str
    ) -> Optional[GradingResultRecord]: ...

    def get_published_for_student(
        self, submission_id: UUID, student_id: UUID, *, access_token: str
    ) -> Optional[GradingResultRecord]: ...

    def list_by_assignment(
        self, assignment_id: UUID, *, access_token: str
    ) -> List[GradingResultRecord]: ...

    def update_review(
        self,
        submission_id: UUID,
        final_score: Decimal,
        final_feedback: str,
        reviewed_by: UUID,
        status: GradingStatus = GradingStatus.APPROVED,
        *,
        access_token: str,
        flags: Optional[Dict[str, Any]] = None,
    ) -> Optional[GradingResultRecord]: ...

    def update_status(
        self, submission_id: UUID, status: GradingStatus | str, *, access_token: str
    ) -> Optional[GradingResultRecord]: ...

    def publish(
        self,
        submission_id: UUID,
        published_at: Optional[datetime] = None,
        *,
        access_token: str,
    ) -> Optional[GradingResultRecord]: ...

    def publish_by_assignment(
        self, assignment_id: UUID, *, access_token: str
    ) -> List[GradingResultRecord]: ...


# --------------------------------------------------------------------------
# Supabase Repository Implementation
# --------------------------------------------------------------------------


class SupabaseGradingRepository:
    """Supabase-backed grading repository operating under the caller's JWT/RLS context."""

    def insert(self, data: GradingResultCreate, *, access_token: str) -> GradingResultRecord:
        """Insert or safely update a grading result record (handled safely via upsert on PK)."""
        client = get_user_supabase(access_token)
        now_str = datetime.now(UTC).isoformat()

        # Strict validation of status
        if data.status not in GradingStatus:
            raise InvalidGradingStatusError(f"Forbidden grading status '{data.status}'.")

        final_score = data.final_score if data.final_score is not None else data.ai_score
        final_feedback = data.final_feedback if data.final_feedback is not None else data.ai_feedback

        payload: Dict[str, Any] = {
            "submission_id": str(data.submission_id),
            "ai_score": float(data.ai_score),
            "final_score": float(final_score),
            "ai_feedback": data.ai_feedback,
            "final_feedback": final_feedback,
            "evidence": data.evidence,
            "flags": data.flags,
            "confidence": float(data.confidence),
            "status": data.status.value,
            "created_at": now_str,
            "updated_at": now_str,
        }

        try:
            # Safe duplicate handling: upsert on submission_id ensures idempotent writes
            resp = client.table("grading_results").upsert(payload, on_conflict="submission_id").execute()
            rows = resp.data or []
            if not rows:
                raise GradingRepositoryError("Grading result upsert returned empty response.")
            row = rows[0] if isinstance(rows, list) else rows
            return self._to_record(row)
        except GradingRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to insert grading result in Supabase: %s", exc)
            raise GradingRepositoryError("Failed to store grading result") from exc

    def get_by_submission_id(
        self, submission_id: UUID, *, access_token: str
    ) -> Optional[GradingResultRecord]:
        """Fetch grading result by submission ID (teacher access or internal verification)."""
        client = get_user_supabase(access_token)
        try:
            resp = (
                client.table("grading_results")
                .select(
                    "submission_id, ai_score, final_score, ai_feedback, final_feedback, "
                    "evidence, flags, confidence, status, reviewed_by, reviewed_at, "
                    "published_at, created_at, updated_at"
                )
                .eq("submission_id", str(submission_id))
                .execute()
            )
            data = resp.data
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data
            return self._to_record(row)
        except GradingRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to get grading result: %s", exc)
            raise GradingRepositoryError("Failed to fetch grading result") from exc

    def get_published_for_student(
        self, submission_id: UUID, student_id: UUID, *, access_token: str
    ) -> Optional[GradingResultRecord]:
        """Fetch grading result for a student.

        CRITICAL SECURITY RULES:
        1. Verifies submission belongs to this student.
        2. Returns record ONLY if status == 'published'.
        3. Returns None for 'pending_review', 'approved', or 'rejected'.
        """
        client = get_user_supabase(access_token)
        try:
            # Verify student owns the submission
            sub_resp = (
                client.table("submissions")
                .select("id, student_id")
                .eq("id", str(submission_id))
                .eq("student_id", str(student_id))
                .execute()
            )
            if not sub_resp.data:
                return None

            # Fetch grading result strictly where status is 'published'
            resp = (
                client.table("grading_results")
                .select(
                    "submission_id, ai_score, final_score, ai_feedback, final_feedback, "
                    "evidence, flags, confidence, status, reviewed_by, reviewed_at, "
                    "published_at, created_at, updated_at"
                )
                .eq("submission_id", str(submission_id))
                .eq("status", GradingStatus.PUBLISHED.value)
                .execute()
            )
            data = resp.data
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data
            return self._to_record(row)
        except GradingRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to get published grade for student: %s", exc)
            raise GradingRepositoryError("Failed to fetch student grading result") from exc

    def list_by_assignment(
        self, assignment_id: UUID, *, access_token: str
    ) -> List[GradingResultRecord]:
        """List all grading results for submissions belonging to an assignment (teacher only)."""
        client = get_user_supabase(access_token)
        try:
            # 1. Fetch submission IDs for the assignment
            sub_resp = (
                client.table("submissions")
                .select("id")
                .eq("assignment_id", str(assignment_id))
                .execute()
            )
            sub_rows = sub_resp.data or []
            if not sub_rows:
                return []

            sub_ids = [str(r["id"]) for r in sub_rows]

            # 2. Fetch grading results for these submissions
            resp = (
                client.table("grading_results")
                .select(
                    "submission_id, ai_score, final_score, ai_feedback, final_feedback, "
                    "evidence, flags, confidence, status, reviewed_by, reviewed_at, "
                    "published_at, created_at, updated_at"
                )
                .in_("submission_id", sub_ids)
                .execute()
            )
            rows = resp.data or []
            return [self._to_record(r) for r in rows]
        except GradingRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list grading results by assignment: %s", exc)
            raise GradingRepositoryError("Failed to list assignment grading results") from exc

    def update_review(
        self,
        submission_id: UUID,
        final_score: Decimal,
        final_feedback: str,
        reviewed_by: UUID,
        status: GradingStatus = GradingStatus.APPROVED,
        *,
        access_token: str,
        flags: Optional[Dict[str, Any]] = None,
    ) -> Optional[GradingResultRecord]:
        """Update teacher-approved final score, feedback, and review metadata (and optionally flags)."""
        client = get_user_supabase(access_token)
        now_str = datetime.now(UTC).isoformat()

        if status not in GradingStatus:
            raise InvalidGradingStatusError(f"Invalid review status: '{status}'.")

        payload = {
            "final_score": float(final_score),
            "final_feedback": final_feedback,
            "reviewed_by": str(reviewed_by),
            "reviewed_at": now_str,
            "status": status.value,
            "updated_at": now_str,
        }
        if flags is not None:
            payload["flags"] = flags

        try:
            resp = (
                client.table("grading_results")
                .update(payload)
                .eq("submission_id", str(submission_id))
                .execute()
            )
            data = resp.data or []
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data
            return self._to_record(row)
        except GradingRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to update grading review: %s", exc)
            raise GradingRepositoryError("Failed to update grading review") from exc

    def update_status(
        self, submission_id: UUID, status: GradingStatus | str, *, access_token: str
    ) -> Optional[GradingResultRecord]:
        """Update grading status through authorized operations."""
        client = get_user_supabase(access_token)
        now_str = datetime.now(UTC).isoformat()

        # Strict validation
        if isinstance(status, str):
            try:
                status = GradingStatus(status.lower().strip())
            except ValueError:
                raise InvalidGradingStatusError(
                    f"Forbidden grading status '{status}'. Must be one of: {list(GradingStatus)}"
                ) from None

        try:
            resp = (
                client.table("grading_results")
                .update({"status": status.value, "updated_at": now_str})
                .eq("submission_id", str(submission_id))
                .execute()
            )
            data = resp.data or []
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data
            return self._to_record(row)
        except GradingRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to update grading status: %s", exc)
            raise GradingRepositoryError("Failed to update grading status") from exc

    def publish(
        self,
        submission_id: UUID,
        published_at: Optional[datetime] = None,
        *,
        access_token: str,
    ) -> Optional[GradingResultRecord]:
        """Publish an approved grading result, making it visible to the student."""
        client = get_user_supabase(access_token)
        now_str = (published_at or datetime.now(UTC)).isoformat()

        payload = {
            "status": GradingStatus.PUBLISHED.value,
            "published_at": now_str,
            "updated_at": now_str,
        }

        try:
            resp = (
                client.table("grading_results")
                .update(payload)
                .eq("submission_id", str(submission_id))
                .execute()
            )
            data = resp.data or []
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data
            return self._to_record(row)
        except Exception as exc:
            logger.exception("Failed to publish grading result: %s", exc)
            raise GradingRepositoryError("Failed to publish grading result") from exc

    def publish_by_assignment(
        self, assignment_id: UUID, *, access_token: str
    ) -> List[GradingResultRecord]:
        """Bulk publish all approved grading results for an assignment."""
        client = get_user_supabase(access_token)
        now_str = datetime.now(UTC).isoformat()

        try:
            # 1. Fetch submission IDs for this assignment
            sub_resp = (
                client.table("submissions")
                .select("id")
                .eq("assignment_id", str(assignment_id))
                .execute()
            )
            sub_rows = sub_resp.data or []
            if not sub_rows:
                return []

            sub_ids = [str(r["id"]) for r in sub_rows]

            # 2. Update status to 'published' for approved submissions
            resp = (
                client.table("grading_results")
                .update(
                    {
                        "status": GradingStatus.PUBLISHED.value,
                        "published_at": now_str,
                        "updated_at": now_str,
                    }
                )
                .in_("submission_id", sub_ids)
                .eq("status", GradingStatus.APPROVED.value)
                .execute()
            )
            rows = resp.data or []
            return [self._to_record(r) for r in rows]
        except Exception as exc:
            logger.exception("Failed to bulk publish assignment grading results: %s", exc)
            raise GradingRepositoryError("Failed to publish assignment grading results") from exc

    # ---- Internal Parser Helper -------------------------------------------

    @staticmethod
    def _to_record(data: Dict[str, Any]) -> GradingResultRecord:
        """Parse raw Supabase row into strict GradingResultRecord."""
        try:
            raw_status = data["status"]
            try:
                status = GradingStatus(raw_status)
            except ValueError:
                raise InvalidGradingStatusError(f"Database contains invalid status '{raw_status}'.")

            return GradingResultRecord(
                submission_id=UUID(str(data["submission_id"])),
                ai_score=Decimal(str(data["ai_score"])),
                final_score=Decimal(str(data["final_score"])),
                ai_feedback=str(data.get("ai_feedback") or ""),
                final_feedback=str(data.get("final_feedback") or ""),
                evidence=data.get("evidence") or {},
                flags=data.get("flags") or {},
                confidence=Decimal(str(data.get("confidence") or "1.0")),
                status=status,
                reviewed_by=UUID(str(data["reviewed_by"])) if data.get("reviewed_by") else None,
                reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
                published_at=datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None,
                created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
                updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            )
        except GradingRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to parse grading result record: %s", exc)
            raise GradingRepositoryError("Failed to parse grading result data") from exc

