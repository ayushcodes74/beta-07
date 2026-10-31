"""Teacher review queue (OCR / low trust / student requests) and student review requests.

All repositories and the OCR engine are in-memory fakes; no database or network calls are made.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.database.grading_repository import GradingResultRecord, GradingStatus
from app.database.review_request_repository import DuplicateOpenReviewRequestError
from app.schemas.assignment import AssignmentContent, AssignmentStatus
from app.schemas.ocr import JobStatusResponse, OCRDocumentResult
from app.schemas.review import ReviewRequestResponse, ReviewRequestStatus
from app.schemas.user import Role
from app.services.assignment_service import AssignmentNotFoundError, AssignmentRecord, AssignmentService
from app.services.auth_service import CurrentUser
from app.services.ocr_client import OCRJobFailedError, OCRServiceUnavailableError
from app.services.review_service import ReviewConflictError, ReviewService
from app.services.submission_service import (
    SubmissionNotFoundError,
    SubmissionRecord,
    SubmissionService,
    SubmissionValidationError,
)

TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
OTHER_TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
STUDENT = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)
TOKEN = "token"


def _assignment(teacher_id=TEACHER.id):
    content = AssignmentContent.model_validate(
        {
            "title": "Number systems",
            "due_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
            "total_marks": 5,
            "questions": [{"type": "subjective", "text": "Convert 5 to binary.", "marks": 5,
                           "expected_answer": "101"}],
        }
    )
    return AssignmentRecord(id=uuid4(), teacher_id=teacher_id, status=AssignmentStatus.PUBLISHED, content=content)


class AssignmentRepo:
    def __init__(self, record):
        self.record = record

    def list_by_teacher(self, teacher_id, *, access_token):
        return [self.record] if self.record.teacher_id == teacher_id else []

    def is_owned_by(self, assignment_id, teacher_id, *, access_token):
        return self.record.id == assignment_id and self.record.teacher_id == teacher_id

    def get(self, assignment_id, *, access_token):
        return self.record if self.record.id == assignment_id else None


class SubmissionRepo:
    def __init__(self, records):
        self.records = {r.id: r for r in records}
        self.status_updates = []

    def get(self, submission_id, *, access_token):
        return self.records.get(submission_id)

    def list_by_assignment(self, assignment_id, *, access_token):
        return [r for r in self.records.values() if r.assignment_id == assignment_id]

    def list_by_student(self, student_id, *, access_token):
        return [r for r in self.records.values() if r.student_id == student_id]

    def update_status(self, submission_id, status, ocr_job_id=None, *, access_token):
        self.status_updates.append((submission_id, status))
        return self.records.get(submission_id)


class GradingRepo:
    def __init__(self, records=(), fail=False):
        self.records = list(records)
        self.fail = fail

    def list_by_submission_ids(self, submission_ids, *, access_token):
        if self.fail:
            raise RuntimeError("RLS denied")
        return [r for r in self.records if r.submission_id in set(submission_ids)]


class ReviewRepo:
    def __init__(self, requests=(), fail=False):
        self.requests = {r.id: r for r in requests}
        self.fail = fail

    def list_by_submission_ids(self, submission_ids, *, access_token):
        if self.fail:
            raise RuntimeError("relation review_requests does not exist")
        return [r for r in self.requests.values() if r.submission_id in set(submission_ids)]

    def list_by_student(self, student_id, *, access_token):
        return [r for r in self.requests.values() if r.student_id == student_id]

    def get(self, request_id, *, access_token):
        return self.requests.get(request_id)

    def create(self, submission_id, student_id, reason, *, access_token):
        if any(r.submission_id == submission_id and r.status is ReviewRequestStatus.OPEN
               for r in self.requests.values()):
            raise DuplicateOpenReviewRequestError("dup")
        req = _request(submission_id, student_id, reason=reason)
        self.requests[req.id] = req
        return req

    def resolve(self, request_id, status, teacher_response, resolved_by, *, access_token):
        req = self.requests.get(request_id)
        if req is None or req.status is not ReviewRequestStatus.OPEN:
            return None
        updated = req.model_copy(update={"status": status, "teacher_response": teacher_response,
                                         "resolved_by": resolved_by, "resolved_at": datetime.now(UTC)})
        self.requests[request_id] = updated
        return updated


class FakeOCR:
    """job id -> OCRDocumentResult | JobStatusResponse | Exception."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    async def get_job_result(self, job_id):
        self.calls.append(job_id)
        result = self.results[job_id]
        if isinstance(result, Exception):
            raise result
        return result


def _submission(assignment_id, status="ocr_completed", job="job", student_id=None):
    now = datetime.now(UTC).isoformat()
    return SubmissionRecord(
        id=uuid4(), assignment_id=assignment_id, student_id=student_id or uuid4(), filename="a.pdf",
        ocr_job_id=job, status=status, created_at=now, updated_at=now,
    )


def _ocr(job_id, confidences, status="completed", failed_pages=0, math_review=False, warnings=()):
    blocks = [
        {"block_id": f"b{i}", "sequence": i, "type": "handwritten", "text": "x", "confidence": c,
         "bounding_box": {"x1": 0, "y1": 0, "x2": 5, "y2": 5}}
        for i, c in enumerate(confidences, start=1)
    ]
    math = [{"region_id": "m1", "bounding_box": {"x1": 0, "y1": 0, "x2": 5, "y2": 5},
             "requires_manual_review": True}] if math_review else []
    return OCRDocumentResult.model_validate(
        {
            "job_id": job_id, "submission_id": "s", "status": status, "warnings": list(warnings),
            "processing_summary": {"total_pages": 2, "processed_pages": 2 - failed_pages,
                                   "failed_pages": failed_pages, "total_processing_time_ms": 1.0},
            "pages": [{"page_id": "p1", "page_number": 1, "width": 10, "height": 10, "full_text": "x",
                       "text_blocks": blocks, "math_blocks": math}],
        }
    )


def _grade(submission_id, *, status=GradingStatus.PENDING_REVIEW, question_confidences=(0.9,),
           review_required=False, review_reasons=(), ocr_confidence=0.9, kind="ai_answer_check", flags=None):
    suggestion = {
        "ocr_confidence": ocr_confidence,
        "total_max_marks": 5.0,
        "review_required": review_required,
        "review_reasons": list(review_reasons),
        "questions": [{"confidence": c} for c in question_confidences],
    }
    return GradingResultRecord(
        submission_id=submission_id, ai_score=Decimal("3"), final_score=Decimal("3"), ai_feedback="",
        final_feedback="", evidence={"kind": kind, "suggestion": suggestion},
        flags=flags if flags is not None else {"review_required": review_required,
                                               "review_reasons": list(review_reasons)},
        confidence=Decimal("0.5"), status=status,
    )


def _request(submission_id, student_id, *, reason="The marks for Q1 look wrong.", status=ReviewRequestStatus.OPEN):
    now = datetime.now(UTC)
    return ReviewRequestResponse(
        id=uuid4(), submission_id=submission_id, student_id=student_id, reason=reason, status=status,
        created_at=now, updated_at=now,
    )


def _service(assignment, submissions, *, grades=(), requests=(), ocr=None, grading_fail=False, review_fail=False):
    sub_repo = SubmissionRepo(submissions)
    sub_service = SubmissionService(sub_repo, AssignmentService(AssignmentRepo(assignment)), None)
    return ReviewService(
        sub_service, GradingRepo(grades, fail=grading_fail), ReviewRepo(requests, fail=review_fail),
        FakeOCR(ocr or {}), ocr_threshold=0.65, trust_threshold=0.70,
    ), sub_repo


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- OCR review


def test_ocr_queue_flags_low_confidence_failures_and_warnings_but_not_clean_results():
    a = _assignment()
    clean = _submission(a.id, job="clean")
    low = _submission(a.id, job="low")
    failed = _submission(a.id, status="ocr_failed", job="failed")
    pages = _submission(a.id, job="pages")
    service, repo = _service(a, [clean, low, failed, pages], ocr={
        "clean": _ocr("clean", [0.95, 0.9]),
        "low": _ocr("low", [0.5, 0.6]),
        "failed": OCRJobFailedError("boom", job_id="failed", error_detail="unreadable scan"),
        "pages": _ocr("pages", [0.9], status="completed_with_warnings", failed_pages=1, math_review=True,
                      warnings=["Page 2 blurry"]),
    })

    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))

    by_id = {i.submission_id: i for i in queue.ocr}
    assert set(by_id) == {low.id, failed.id, pages.id}
    assert by_id[failed.id].reasons == ["OCR failed: unreadable scan"]
    assert by_id[low.id].ocr_confidence == 0.55
    assert "Mean OCR confidence 55% is below the 65% threshold." in by_id[low.id].reasons
    assert any("1 of 2 page(s) failed" in r for r in by_id[pages.id].reasons)
    assert any("math expression" in r for r in by_id[pages.id].reasons)
    assert any("Page 2 blurry" in r for r in by_id[pages.id].reasons)
    # Failures (no confidence) are listed first.
    assert queue.ocr[0].submission_id == failed.id
    # The newer OCR status is persisted for a stale submission row.
    assert (pages.id, "ocr_completed_with_warnings") in repo.status_updates


def test_ocr_queue_skips_published_and_processing_and_uses_stored_confidence():
    a = _assignment()
    published = _submission(a.id, status="published", job="pub")
    processing = _submission(a.id, status="ocr_processing", job="proc")
    graded = _submission(a.id, job="graded")
    service, _ = _service(
        a, [published, processing, graded],
        grades=[_grade(graded.id, ocr_confidence=0.4)],
        ocr={"proc": JobStatusResponse(job_id="proc", status="processing", stage="ocr", progress=40,
                                       created_at="", updated_at="")},
    )
    ocr = service.ocr_client

    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))

    assert [i.submission_id for i in queue.ocr] == [graded.id]
    assert queue.ocr[0].ocr_confidence == 0.4
    assert ocr.calls == ["proc"]  # published skipped; graded used its stored confidence


def test_unreachable_ocr_engine_is_reported_not_guessed():
    a = _assignment()
    sub = _submission(a.id, job="x")
    service, _ = _service(a, [sub], ocr={"x": OCRServiceUnavailableError("down")})

    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))

    assert queue.ocr == []
    assert any("could not be reached for 1 submission" in n for n in queue.notes)


# ---------------------------------------------------------------- low trust


def test_low_trust_includes_low_confidence_and_flagged_unpublished_ai_grades_only():
    a = _assignment()
    low, flagged, fine, published, manual = (_submission(a.id, job=None, status="under_review") for _ in range(5))
    service, _ = _service(a, [low, flagged, fine, published, manual], grades=[
        _grade(low.id, question_confidences=(0.5, 0.6)),
        _grade(flagged.id, review_required=True, review_reasons=["Q1: answer not found"]),
        _grade(fine.id),
        _grade(published.id, status=GradingStatus.PUBLISHED, question_confidences=(0.1,)),
        _grade(manual.id, kind="teacher_manual_grade", question_confidences=(0.1,)),
    ])

    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))

    by_id = {i.submission_id: i for i in queue.low_trust}
    assert set(by_id) == {low.id, flagged.id}
    assert by_id[low.id].trust_score == 0.55
    assert by_id[low.id].reasons == ["AI confidence 55% is below the 70% trust threshold."]
    assert by_id[flagged.id].reasons == ["Q1: answer not found"]
    assert by_id[flagged.id].max_score == 5.0
    assert queue.low_trust[0].submission_id == low.id  # lowest trust first


def test_grading_storage_failure_becomes_a_note():
    a = _assignment()
    service, _ = _service(a, [_submission(a.id, job=None, status="under_review")], grading_fail=True)
    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))
    assert queue.low_trust == []
    assert any("Grading results could not be loaded" in n for n in queue.notes)


# ---------------------------------------------------------------- student requests


def test_student_requests_lists_only_open_requests():
    a = _assignment()
    sub = _submission(a.id, status="published", student_id=STUDENT.id)
    other = _submission(a.id, status="published")
    open_req = _request(sub.id, STUDENT.id)
    closed = _request(other.id, other.student_id, status=ReviewRequestStatus.RESOLVED)
    service, _ = _service(a, [sub, other], requests=[open_req, closed])

    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))

    assert [i.review_request.id for i in queue.student_requests] == [open_req.id]
    assert queue.student_requests[0].reasons == [open_req.reason]


def test_missing_review_requests_table_becomes_a_note():
    a = _assignment()
    service, _ = _service(a, [_submission(a.id, status="published", job=None)], review_fail=True)
    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))
    assert any("phase3a_review_requests.sql" in n for n in queue.notes)


def test_other_teacher_sees_an_empty_queue():
    a = _assignment()
    service, _ = _service(a, [_submission(a.id, status="ocr_failed", job=None)])
    queue = _run(service.build_queue(OTHER_TEACHER, access_token=TOKEN))
    assert (queue.ocr, queue.low_trust, queue.student_requests) == ([], [], [])


def test_student_can_request_review_once_for_own_published_grade():
    a = _assignment()
    sub = _submission(a.id, status="published", student_id=STUDENT.id)
    service, _ = _service(a, [sub])

    created = _run(service.create_request(STUDENT, sub.id, "Q1 deserves more marks.", access_token=TOKEN))
    assert created.status is ReviewRequestStatus.OPEN
    with pytest.raises(ReviewConflictError):
        _run(service.create_request(STUDENT, sub.id, "Asking again please.", access_token=TOKEN))
    assert [r.id for r in _run(service.list_requests(STUDENT, access_token=TOKEN))] == [created.id]


def test_student_cannot_request_review_before_publish_or_for_others():
    a = _assignment()
    unpublished = _submission(a.id, status="under_review", student_id=STUDENT.id)
    someone_else = _submission(a.id, status="published")
    service, _ = _service(a, [unpublished, someone_else])

    with pytest.raises(SubmissionValidationError):
        _run(service.create_request(STUDENT, unpublished.id, "Please re-check my grade.", access_token=TOKEN))
    with pytest.raises(SubmissionNotFoundError):
        _run(service.create_request(STUDENT, someone_else.id, "Please re-check my grade.", access_token=TOKEN))


def test_teacher_resolves_open_request_once_and_other_teacher_gets_404():
    a = _assignment()
    sub = _submission(a.id, status="published", student_id=STUDENT.id)
    req = _request(sub.id, STUDENT.id)
    service, _ = _service(a, [sub], requests=[req])

    with pytest.raises(AssignmentNotFoundError):
        _run(service.resolve_request(OTHER_TEACHER, req.id, "resolved", None, access_token=TOKEN))

    done = _run(service.resolve_request(TEACHER, req.id, "resolved", "  Re-marked Q1, +1.  ", access_token=TOKEN))
    assert done.status is ReviewRequestStatus.RESOLVED
    assert done.teacher_response == "Re-marked Q1, +1."
    assert done.resolved_by == TEACHER.id
    with pytest.raises(ReviewConflictError):
        _run(service.resolve_request(TEACHER, req.id, "dismissed", None, access_token=TOKEN))


def test_resolve_unknown_request_is_404():
    a = _assignment()
    service, _ = _service(a, [])
    with pytest.raises(SubmissionNotFoundError):
        _run(service.resolve_request(TEACHER, UUID(int=1), "dismissed", None, access_token=TOKEN))
