"""AI answer check (GradingService): answer keys + OCR text -> AI Engine -> pending-review suggestion.

The AI Engine is mocked with httpx.MockTransport; no LLM or network calls are made.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app.database.grading_repository import GradingResultRecord, GradingStatus
from app.schemas.assignment import AssignmentContent, AssignmentStatus
from app.schemas.ocr import JobStatusResponse, OCRDocumentResult
from app.schemas.user import Role
from app.services.ai_generation_service import AIRateLimitedError
from app.services.assignment_service import AssignmentNotFoundError, AssignmentRecord, AssignmentService
from app.services.auth_service import CurrentUser
from app.services.grading_service import GradingNotReadyError, GradingService
from app.services.submission_service import SubmissionNotFoundError, SubmissionRecord, SubmissionValidationError

TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
OTHER_TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)


class Repo:
    def __init__(self, record):
        self.record = record

    def get(self, _id, *, access_token):
        return self.record if self.record and self.record.id == _id else None


class AssignmentRepo(Repo):
    def is_owned_by(self, assignment_id, teacher_id, *, access_token):
        return self.record.id == assignment_id and self.record.teacher_id == teacher_id


class FakeOCR:
    def __init__(self, result):
        self.result = result

    async def get_job_result(self, job_id):
        return self.result


class FakeGradingRepo:
    def __init__(self, existing=None, fail=False):
        self.existing = existing
        self.fail = fail
        self.inserted = []

    def get_by_submission_id(self, submission_id, *, access_token):
        return self.existing

    def insert(self, data, *, access_token):
        if self.fail:
            raise RuntimeError("RLS denied")
        self.inserted.append(data)
        return data


def _assignment():
    content = AssignmentContent.model_validate(
        {
            "title": "Number systems",
            "due_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
            "total_marks": 5,
            "questions": [
                {"type": "subjective", "text": "Convert 53.625 to binary.", "marks": 4,
                 "expected_answer": "(110101.101)2", "instructions": "Show working."},
                {"type": "mcq", "text": "Universal gate?", "marks": 1,
                 "options": [{"id": "A", "text": "XOR"}, {"id": "B", "text": "NAND"}], "correct_option_id": "B"},
            ],
        }
    )
    return AssignmentRecord(id=uuid4(), teacher_id=TEACHER.id, status=AssignmentStatus.PUBLISHED, content=content)


def _submission(assignment_id):
    now = datetime.now(UTC).isoformat()
    return SubmissionRecord(
        id=uuid4(), assignment_id=assignment_id, student_id=uuid4(), filename="a.pdf",
        ocr_job_id="job-1", status="ocr_completed", created_at=now, updated_at=now,
    )


def _ocr():
    return OCRDocumentResult.model_validate(
        {
            "job_id": "job-1",
            "submission_id": "s",
            "pages": [
                {"page_id": "p2", "page_number": 2, "width": 10, "height": 10, "full_text": "Q2: NAND",
                 "text_blocks": [{"block_id": "b2", "sequence": 1, "type": "handwritten", "text": "Q2: NAND",
                                  "confidence": 0.8, "bounding_box": {"x1": 0, "y1": 0, "x2": 5, "y2": 5}}]},
                {"page_id": "p1", "page_number": 1, "width": 10, "height": 10, "full_text": "53.625 = (110101.101)2",
                 "text_blocks": [{"block_id": "b1", "sequence": 1, "type": "handwritten", "text": "53.625",
                                  "confidence": 1.0, "bounding_box": {"x1": 0, "y1": 0, "x2": 5, "y2": 5}}]},
            ],
        }
    )


AI_RESULT = {
    "submission_id": "s", "assignment_id": "a",
    "total_awarded_marks": 4.0, "total_max_marks": 5.0, "percentage": 80.0,
    "overall_feedback": "Good conversion.", "review_required": True, "review_reasons": ["Q[q2]: low OCR"],
    "question_results": [
        {"question_id": "q1", "max_marks": 4, "awarded_marks": 4, "overall_explanation": "Correct binary.",
         "strengths": ["Accurate"], "areas_for_improvement": [], "confidence": 0.9, "review_required": False,
         "review_reasons": [],
         "criterion_evaluations": [{"criterion_id": "c", "max_marks": 4, "awarded_marks": 4, "explanation": "ok",
                                    "matched_concepts": ["division by 2", "fraction x2"], "missing_concepts": []}]},
        {"question_id": "q2", "max_marks": 1, "awarded_marks": 0, "overall_explanation": "Answer not found.",
         "confidence": 0.4, "review_required": True, "review_reasons": ["low OCR"],
         "criterion_evaluations": [{"criterion_id": "c", "max_marks": 1, "awarded_marks": 0, "explanation": "no",
                                    "matched_concepts": [], "missing_concepts": ["NAND"]}]},
    ],
}


def _service(ai_status=200, ai_body=AI_RESULT, ocr=None, grading_repo=None, captured=None):
    assignment = _assignment()
    submission = _submission(assignment.id)

    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(json.loads(request.content))
        return httpx.Response(ai_status, json=ai_body)

    service = GradingService(
        Repo(submission),
        AssignmentService(AssignmentRepo(assignment)),
        FakeOCR(ocr if ocr is not None else _ocr()),
        grading_repo,
        ai_base_url="http://ai",
        transport=httpx.MockTransport(handler),
    )
    return service, submission, assignment


def run(coro):
    return asyncio.run(coro)


def test_grades_against_answer_keys_and_saves_pending_review():
    captured: list = []
    repo = FakeGradingRepo()
    service, submission, assignment = _service(grading_repo=repo, captured=captured)

    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))

    sent = captured[0]
    # Pages in order, answer keys included, teacher-only data goes to the internal AI Engine only
    assert sent["student_text"] == "[Page 1]\n53.625 = (110101.101)2\n\n[Page 2]\nQ2: NAND"
    assert sent["ocr_confidence"] == 0.9
    assert sent["questions"][0] == {
        "question_id": "q1", "type": "subjective", "text": "Convert 53.625 to binary.", "marks": 4.0,
        "expected_answer": "(110101.101)2", "instructions": "Show working.",
    }
    assert sent["questions"][1]["correct_option_id"] == "B"

    assert result.total_awarded_marks == 4.0 and result.percentage == 80.0
    assert [q.number for q in result.questions] == [1, 2]
    assert result.questions[0].matched_concepts == ["division by 2", "fraction x2"]
    assert result.questions[1].missing_concepts == ["NAND"]
    assert result.review_required is True
    assert result.saved is True and result.status == "pending_review"
    stored = repo.inserted[0]
    assert stored.status is GradingStatus.PENDING_REVIEW and stored.ai_score == Decimal("4.0")
    assert stored.evidence["kind"] == "ai_answer_check"


def test_other_teacher_gets_not_found():
    service, submission, _ = _service()
    with pytest.raises(AssignmentNotFoundError):
        run(service.grade_submission(OTHER_TEACHER, submission.id, access_token="t"))
    with pytest.raises(SubmissionNotFoundError):
        run(service.grade_submission(TEACHER, uuid4(), access_token="t"))


def test_ocr_still_processing_is_not_ready():
    processing = JobStatusResponse.model_validate(
        {"job_id": "job-1", "submission_id": "s", "status": "processing", "stage": "recognition", "progress": 50,
         "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}
    )
    service, submission, _ = _service(ocr=processing)
    with pytest.raises(GradingNotReadyError):
        run(service.grade_submission(TEACHER, submission.id, access_token="t"))


def test_ai_rate_limit_is_mapped():
    service, submission, _ = _service(ai_status=429, ai_body={"detail": "busy"})
    with pytest.raises(AIRateLimitedError):
        run(service.grade_submission(TEACHER, submission.id, access_token="t"))


def test_storage_failure_still_returns_suggestion():
    service, submission, _ = _service(grading_repo=FakeGradingRepo(fail=True))
    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    assert result.saved is False and result.total_awarded_marks == 4.0


def test_never_overwrites_approved_grade():
    approved = GradingResultRecord(
        submission_id=uuid4(), ai_score=Decimal(3), final_score=Decimal(3), ai_feedback="x", final_feedback="x",
        evidence={}, flags={}, confidence=Decimal("0.9"), status=GradingStatus.APPROVED,
    )
    repo = FakeGradingRepo(existing=approved)
    service, submission, _ = _service(grading_repo=repo)
    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    assert result.saved is False and repo.inserted == []


def test_saved_suggestion_round_trip():
    repo = FakeGradingRepo()
    service, submission, _ = _service(grading_repo=repo)
    first = run(service.grade_submission(TEACHER, submission.id, access_token="t"))

    stored = repo.inserted[0]
    repo.existing = GradingResultRecord(
        submission_id=submission.id, ai_score=stored.ai_score, final_score=stored.ai_score,
        ai_feedback=stored.ai_feedback, final_feedback=stored.ai_feedback, evidence=stored.evidence,
        flags=stored.flags, confidence=stored.confidence, status=GradingStatus.PENDING_REVIEW,
    )
    loaded = run(service.get_saved_suggestion(TEACHER, submission.id, access_token="t"))
    assert loaded is not None and loaded.total_awarded_marks == first.total_awarded_marks
    assert loaded.saved is True and loaded.questions[1].explanation == "Answer not found."
    with pytest.raises(AssignmentNotFoundError):
        run(service.get_saved_suggestion(OTHER_TEACHER, submission.id, access_token="t"))


# --------------------------------------------------------------------------- publication


class StatefulGradingRepo:
    """In-memory grading_results with the update_review / publish / student-read semantics."""

    def __init__(self, existing=None):
        self.row = existing

    def get_by_submission_id(self, submission_id, *, access_token):
        return self.row if self.row and self.row.submission_id == submission_id else None

    def get_published_for_student(self, submission_id, student_id, *, access_token):
        row = self.get_by_submission_id(submission_id, access_token=access_token)
        return row if row and row.status is GradingStatus.PUBLISHED else None

    def insert(self, data, *, access_token):
        self.row = GradingResultRecord(
            submission_id=data.submission_id, ai_score=data.ai_score, final_score=data.ai_score,
            ai_feedback=data.ai_feedback, final_feedback=data.ai_feedback, evidence=data.evidence,
            flags=data.flags, confidence=data.confidence, status=data.status,
        )
        return self.row

    def update_review(self, submission_id, final_score, final_feedback, reviewed_by, status, *, access_token, flags=None):
        self.row = self.row.model_copy(update={
            "final_score": final_score, "final_feedback": final_feedback, "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now(UTC), "status": status, "flags": flags if flags is not None else self.row.flags,
        })
        return self.row

    def publish(self, submission_id, published_at=None, *, access_token):
        self.row = self.row.model_copy(update={"status": GradingStatus.PUBLISHED, "published_at": datetime.now(UTC)})
        return self.row


class StatusRepo(Repo):
    def __init__(self, record):
        super().__init__(record)
        self.statuses = []

    def update_status(self, submission_id, status, ocr_job_id=None, *, access_token):
        self.statuses.append(status)
        return self.record


def _publish_service(grading_repo):
    service, submission, assignment = _service(grading_repo=grading_repo)
    service.submissions = StatusRepo(submission)
    return service, submission, assignment


def test_publish_approves_teacher_score_over_ai_suggestion():
    repo = StatefulGradingRepo()
    service, submission, _ = _publish_service(repo)
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))  # AI suggests 4/5
    ai_evidence = repo.row.evidence

    result = run(service.publish_grade(TEACHER, submission.id, 3.5, "  Check Q2.  ", access_token="t"))

    assert result.status == "published" and result.final_score == 3.5 and result.max_score == 5.0
    assert result.final_feedback == "Check Q2." and result.published_at is not None
    assert repo.row.ai_score == Decimal("4.0") and repo.row.reviewed_by == TEACHER.id
    assert repo.row.evidence == ai_evidence  # AI suggestion kept as evidence
    assert service.submissions.statuses == ["published"]


def test_publish_without_ai_check_records_teacher_grade():
    repo = StatefulGradingRepo()
    service, submission, _ = _publish_service(repo)
    result = run(service.publish_grade(TEACHER, submission.id, 5, "Full marks", access_token="t"))
    assert result.final_score == 5.0 and repo.row.evidence == {"kind": "teacher_manual_grade"}


def test_publish_rejects_score_above_total_and_other_teachers():
    repo = StatefulGradingRepo()
    service, submission, _ = _publish_service(repo)
    with pytest.raises(SubmissionValidationError):
        run(service.publish_grade(TEACHER, submission.id, 5.5, "", access_token="t"))
    with pytest.raises(AssignmentNotFoundError):
        run(service.publish_grade(OTHER_TEACHER, submission.id, 1, "", access_token="t"))
    assert repo.row is None and service.submissions.statuses == []


def test_student_sees_only_own_published_grade():
    repo = StatefulGradingRepo()
    service, submission, _ = _publish_service(repo)
    owner = CurrentUser(id=submission.student_id, email=None, role=Role.STUDENT)
    stranger = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)

    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    assert run(service.get_published_grade(owner, submission.id, access_token="t")) is None  # pending review

    run(service.publish_grade(TEACHER, submission.id, 4, "Well done", access_token="t"))
    seen = run(service.get_published_grade(owner, submission.id, access_token="t"))
    assert seen is not None and seen.final_score == 4.0 and seen.final_feedback == "Well done"
    assert "evidence" not in seen.model_dump()
    with pytest.raises(SubmissionNotFoundError):
        run(service.get_published_grade(stranger, submission.id, access_token="t"))
    assert run(service.get_published_grade(TEACHER, submission.id, access_token="t")).final_score == 4.0
