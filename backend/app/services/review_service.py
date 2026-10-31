"""Teacher review queue and student review (re-evaluation) requests.

``build_queue`` collects, for the signed-in teacher's own assignments, every submission that needs
manual attention, in three groups:

  ocr               OCR failed / cancelled / degraded / finished with warnings, pages failed, math
                    flagged for manual review, or mean OCR confidence below the threshold.
  low_trust         An unpublished AI answer check whose confidence is below the trust threshold or
                    that the AI Engine flagged as review-required.
  student_requests  Open requests from students who are not satisfied with a published grade.

Published grades are considered handled, so they only reappear through a student request.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from app.core.config import settings
from app.database.grading_repository import GradingRepository, GradingResultRecord, GradingStatus
from app.database.review_request_repository import (
    DuplicateOpenReviewRequestError,
    ReviewRequestRepository,
)
from app.schemas.ocr import OCRDocumentResult
from app.schemas.review import (
    ReviewQueueItem,
    ReviewQueueResponse,
    ReviewQueueThresholds,
    ReviewRequestResponse,
    ReviewRequestStatus,
)
from app.schemas.user import Role
from app.services.auth_service import CurrentUser
from app.services.ocr_client import (
    OCRJobCancelledError,
    OCRJobFailedError,
    OCRJobNotFoundError,
    OCRServiceClient,
)
from app.services.submission_service import (
    SubmissionNotFoundError,
    SubmissionPermissionError,
    SubmissionRecord,
    SubmissionService,
    SubmissionValidationError,
)

logger = logging.getLogger(__name__)

# OCR results are fetched from the OCR engine for unpublished submissions without a stored confidence.
_MAX_CONCURRENT_OCR_FETCHES = 8
_MAX_REASONS = 6


class ReviewConflictError(Exception):
    """The request cannot be created/changed in its current state (HTTP 409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ReviewService:
    def __init__(
        self,
        submissions: SubmissionService,
        grading_repo: GradingRepository,
        review_repo: ReviewRequestRepository,
        ocr_client: OCRServiceClient,
        *,
        ocr_threshold: Optional[float] = None,
        trust_threshold: Optional[float] = None,
    ) -> None:
        self.submissions = submissions
        self.grading_repo = grading_repo
        self.review_repo = review_repo
        self.ocr_client = ocr_client
        self.ocr_threshold = settings.REVIEW_OCR_CONFIDENCE_THRESHOLD if ocr_threshold is None else ocr_threshold
        self.trust_threshold = settings.REVIEW_TRUST_THRESHOLD if trust_threshold is None else trust_threshold

    # ------------------------------------------------------------------ teacher queue

    async def build_queue(self, teacher: CurrentUser, *, access_token: str) -> ReviewQueueResponse:
        if teacher.role is not Role.TEACHER:
            raise SubmissionPermissionError("Only teachers have a review queue")
        response = ReviewQueueResponse(
            thresholds=ReviewQueueThresholds(ocr_confidence=self.ocr_threshold, trust_score=self.trust_threshold)
        )
        records = await asyncio.to_thread(self.submissions.list_submissions, teacher, access_token=access_token)
        if not records:
            return response
        ids = [r.id for r in records]

        grades: dict[UUID, GradingResultRecord] = {}
        requests: list[ReviewRequestResponse] = []
        grade_task = asyncio.to_thread(self.grading_repo.list_by_submission_ids, ids, access_token=access_token)
        request_task = asyncio.to_thread(self.review_repo.list_by_submission_ids, ids, access_token=access_token)
        grade_rows, request_rows = await asyncio.gather(grade_task, request_task, return_exceptions=True)
        if isinstance(grade_rows, BaseException):
            logger.warning("Review queue: grading results unavailable: %s", type(grade_rows).__name__)
            response.notes.append("Grading results could not be loaded, so low-trust grades may be missing.")
        else:
            grades = {g.submission_id: g for g in grade_rows}
        if isinstance(request_rows, BaseException):
            logger.warning("Review queue: review requests unavailable: %s", type(request_rows).__name__)
            response.notes.append(
                "Student review requests could not be loaded (is phase3a_review_requests.sql applied?)."
            )
        else:
            requests = request_rows

        # ---- OCR review --------------------------------------------------------
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_OCR_FETCHES)
        unreachable = 0

        async def check_ocr(record: SubmissionRecord) -> Optional[ReviewQueueItem]:
            nonlocal unreachable
            grade = grades.get(record.id)
            if record.status == "published" or (grade is not None and grade.status is GradingStatus.PUBLISHED):
                return None
            async with semaphore:
                outcome = await self._ocr_findings(record, grade, access_token=access_token)
            if outcome is None:
                unreachable += 1
                return None
            status, confidence, reasons = outcome
            if not reasons:
                return None
            return _item("ocr", record, grade, status=status, ocr_confidence=confidence, reasons=reasons)

        ocr_items = [i for i in await asyncio.gather(*(check_ocr(r) for r in records)) if i is not None]
        if unreachable:
            response.notes.append(
                f"The OCR engine could not be reached for {unreachable} submission(s), so they were not checked."
            )
        # Failures first (no confidence), then lowest confidence.
        ocr_items.sort(key=lambda i: (i.ocr_confidence is not None, i.ocr_confidence or 0.0, i.submitted_at))
        response.ocr = ocr_items

        # ---- Low trust score ---------------------------------------------------
        by_id = {r.id: r for r in records}
        low_trust: list[ReviewQueueItem] = []
        for submission_id, grade in grades.items():
            record = by_id.get(submission_id)
            if record is None or grade.status not in (GradingStatus.PENDING_REVIEW, GradingStatus.APPROVED):
                continue
            suggestion = _suggestion(grade)
            if suggestion is None:  # teacher's own manual grade: nothing to distrust
                continue
            trust = _trust_score(grade, suggestion)
            reasons: list[str] = []
            if trust is not None and trust < self.trust_threshold:
                reasons.append(f"AI confidence {_pct(trust)} is below the {_pct(self.trust_threshold)} trust threshold.")
            flags = grade.flags or {}
            if flags.get("review_required") or suggestion.get("review_required"):
                flagged = [str(r) for r in (flags.get("review_reasons") or suggestion.get("review_reasons") or [])]
                reasons.extend(flagged or ["The AI flagged this grade for teacher review."])
            if not reasons:
                continue
            low_trust.append(
                _item(
                    "low_trust", record, grade, trust_score=trust, reasons=_dedupe(reasons),
                    ocr_confidence=_float(suggestion.get("ocr_confidence")),
                    max_score=_float(suggestion.get("total_max_marks")),
                )
            )
        low_trust.sort(key=lambda i: (i.trust_score is not None, i.trust_score or 0.0, i.submitted_at))
        response.low_trust = low_trust

        # ---- Student requests --------------------------------------------------
        student_items: list[ReviewQueueItem] = []
        for request in requests:
            record = by_id.get(request.submission_id)
            if record is None or request.status is not ReviewRequestStatus.OPEN:
                continue
            grade = grades.get(record.id)
            max_score = _float((grade.flags or {}).get("max_score")) if grade else None
            student_items.append(
                _item("student_request", record, grade, reasons=[request.reason], review_request=request,
                      max_score=max_score)
            )
        student_items.sort(key=lambda i: i.review_request.created_at if i.review_request else i.submitted_at)
        response.student_requests = student_items
        return response

    async def _ocr_findings(
        self, record: SubmissionRecord, grade: Optional[GradingResultRecord], *, access_token: str
    ) -> Optional[tuple[str, Optional[float], list[str]]]:
        """(live status, mean confidence, reasons). None when the OCR engine could not be reached."""
        status = record.status
        if not record.ocr_job_id:
            if status in ("submitted", "ocr_queued"):
                return status, None, ["No OCR job is linked to this submission; it was never processed."]
            return status, None, []

        suggestion = _suggestion(grade) if grade else None
        stored_confidence = _float(suggestion.get("ocr_confidence")) if suggestion else None
        reasons: list[str] = []
        confidence = stored_confidence

        if stored_confidence is None:
            try:
                result = await self.ocr_client.get_job_result(record.ocr_job_id)
            except OCRJobFailedError as exc:
                detail = getattr(exc, "error_detail", None)
                return "ocr_failed", None, [f"OCR failed: {detail}" if detail else "OCR failed to read this submission."]
            except OCRJobCancelledError:
                return "ocr_cancelled", None, ["OCR processing was cancelled before it finished."]
            except OCRJobNotFoundError:
                return status, None, ["The OCR result is missing on the OCR engine; the student may need to resubmit."]
            except Exception as exc:  # unreachable / timeout: report, don't guess
                logger.warning("Review queue: OCR result unavailable: %s", type(exc).__name__)
                return None
            if not isinstance(result, OCRDocumentResult):
                return f"ocr_{result.status}", None, []  # still queued/processing: nothing to review yet
            status = f"ocr_{result.status}"
            confidence = _mean_confidence(result)
            summary = result.processing_summary
            if summary.failed_pages:
                reasons.append(f"{summary.failed_pages} of {summary.total_pages} page(s) failed OCR.")
            math_flagged = sum(1 for p in result.pages for m in p.math_blocks if m.requires_manual_review)
            if math_flagged:
                reasons.append(f"{math_flagged} math expression(s) flagged for manual review.")
            if result.status == "completed_with_warnings":
                first = (result.warnings or [None])[0]
                reasons.append(f"OCR finished with warnings{': ' + first if first else '.'}")
            await self._sync_status(record, status, access_token=access_token)

        if status == "ocr_failed":
            reasons.insert(0, "OCR failed to read this submission.")
        elif status == "ocr_cancelled":
            reasons.insert(0, "OCR processing was cancelled before it finished.")
        elif status == "ocr_degraded":
            reasons.insert(0, "OCR quality is degraded; the extracted text may be unreliable.")
        elif status == "ocr_completed_with_warnings" and not any("warnings" in r for r in reasons):
            reasons.append("OCR finished with warnings.")
        if confidence is not None and confidence < self.ocr_threshold:
            reasons.insert(
                0, f"Mean OCR confidence {_pct(confidence)} is below the {_pct(self.ocr_threshold)} threshold."
            )
        elif confidence is None and status.startswith("ocr_completed"):
            reasons.append("The OCR engine reported no confidence for any text region.")
        return status, confidence, _dedupe(reasons)

    async def _sync_status(self, record: SubmissionRecord, status: str, *, access_token: str) -> None:
        """Persist a newer OCR status (best-effort), as the status endpoint does while polling."""
        if not record.status.startswith("ocr_") or status == record.status:
            return
        try:
            await asyncio.to_thread(
                self.submissions.repo.update_status,
                submission_id=record.id, status=status, ocr_job_id=record.ocr_job_id, access_token=access_token,
            )
        except Exception as exc:  # noqa: BLE001 - the queue is still correct without it
            logger.info("Review queue: could not persist OCR status: %s", type(exc).__name__)

    # ------------------------------------------------------------------ review requests

    async def create_request(
        self, student: CurrentUser, submission_id: UUID, reason: str, *, access_token: str
    ) -> ReviewRequestResponse:
        if student.role is not Role.STUDENT:
            raise SubmissionPermissionError("Only students can request a review")
        record = await asyncio.to_thread(self.submissions.repo.get, submission_id, access_token=access_token)
        if record is None or record.student_id != student.id:
            raise SubmissionNotFoundError("Submission not found")
        if record.status != "published":
            raise SubmissionValidationError(
                "grade_not_published", "You can apply for a recheck only after your grade has been published."
            )
        try:
            return await asyncio.to_thread(
                self.review_repo.create, submission_id, student.id, reason, access_token=access_token
            )
        except DuplicateOpenReviewRequestError:
            raise ReviewConflictError(
                "review_already_requested", "You already have an open recheck request for this submission."
            ) from None

    async def list_requests(self, user: CurrentUser, *, access_token: str) -> list[ReviewRequestResponse]:
        if user.role is Role.STUDENT:
            rows = await asyncio.to_thread(self.review_repo.list_by_student, user.id, access_token=access_token)
            return [r for r in rows if r.student_id == user.id]
        if user.role is Role.TEACHER:
            records = await asyncio.to_thread(self.submissions.list_submissions, user, access_token=access_token)
            ids = [r.id for r in records]
            rows = await asyncio.to_thread(self.review_repo.list_by_submission_ids, ids, access_token=access_token)
            owned = set(ids)
            return [r for r in rows if r.submission_id in owned]
        raise SubmissionPermissionError("Invalid role")

    async def resolve_request(
        self,
        teacher: CurrentUser,
        request_id: UUID,
        status: str,
        teacher_response: Optional[str],
        *,
        access_token: str,
    ) -> ReviewRequestResponse:
        if teacher.role is not Role.TEACHER:
            raise SubmissionPermissionError("Only teachers can resolve review requests")
        request = await asyncio.to_thread(self.review_repo.get, request_id, access_token=access_token)
        if request is None:
            raise SubmissionNotFoundError("Review request not found")
        record = await asyncio.to_thread(self.submissions.repo.get, request.submission_id, access_token=access_token)
        if record is None:
            raise SubmissionNotFoundError("Review request not found")
        # Raises AssignmentNotFoundError (404) unless the teacher owns the assignment.
        await asyncio.to_thread(
            self.submissions.assignment_service.require_owned, teacher, record.assignment_id,
            access_token=access_token,
        )
        if request.status is not ReviewRequestStatus.OPEN:
            raise ReviewConflictError("review_request_closed", f"This request was already {request.status.value}.")
        response = (teacher_response or "").strip() or None
        updated = await asyncio.to_thread(
            self.review_repo.resolve, request_id, ReviewRequestStatus(status), response, teacher.id,
            access_token=access_token,
        )
        if updated is None:
            raise ReviewConflictError("review_request_closed", "This request was closed in the meantime.")
        return updated


# ---------------------------------------------------------------------- helpers


def _item(
    category: str,
    record: SubmissionRecord,
    grade: Optional[GradingResultRecord],
    *,
    reasons: list[str],
    status: Optional[str] = None,
    ocr_confidence: Optional[float] = None,
    trust_score: Optional[float] = None,
    max_score: Optional[float] = None,
    review_request: Optional[ReviewRequestResponse] = None,
) -> ReviewQueueItem:
    return ReviewQueueItem(
        category=category,  # type: ignore[arg-type]
        submission_id=record.id,
        assignment_id=record.assignment_id,
        student_id=record.student_id,
        submission_status=status or record.status,
        submitted_at=record.created_at,
        reasons=reasons[:_MAX_REASONS],
        ocr_confidence=ocr_confidence,
        trust_score=trust_score,
        ai_score=float(grade.ai_score) if grade else None,
        final_score=float(grade.final_score) if grade else None,
        max_score=max_score,
        grading_status=grade.status.value if grade else None,
        review_request=review_request,
    )


def _suggestion(grade: Optional[GradingResultRecord]) -> Optional[dict[str, Any]]:
    evidence = grade.evidence if grade else None
    if not isinstance(evidence, dict) or evidence.get("kind") != "ai_answer_check":
        return None
    suggestion = evidence.get("suggestion")
    return suggestion if isinstance(suggestion, dict) else {}


def _trust_score(grade: GradingResultRecord, suggestion: dict[str, Any]) -> Optional[float]:
    """Mean per-question AI confidence; None when the AI reported none (stored confidence is then 0)."""
    confidences = [
        c for q in suggestion.get("questions") or [] if isinstance(q, dict)
        for c in [_float(q.get("confidence"))] if c is not None
    ]
    if confidences:
        return round(sum(confidences) / len(confidences), 4)
    if suggestion.get("questions"):
        return None
    return float(grade.confidence)


def _mean_confidence(result: OCRDocumentResult) -> Optional[float]:
    values = [b.confidence for p in result.pages for b in p.text_blocks if b.confidence is not None]
    return round(sum(values) / len(values), 4) if values else None


def _float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i.strip() for i in items if i and i.strip()))
