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
from app.schemas.grading import GradingCorrectionIn
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

    def list_ids_by_teacher(self, teacher_id, *, access_token):
        return [self.record.id] if self.record.teacher_id == teacher_id else []


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


def _late_publish_service(repo, late_status, penalty=None):
    service, submission, assignment = _publish_service(repo)
    late = submission.model_copy(update={"late_status": late_status, "late_penalty_percent": penalty})
    service.submissions = StatusRepo(late)
    return service, late


@pytest.mark.parametrize(
    ("late_status", "code"), [("pending", "late_decision_required"), ("rejected", "late_submission_rejected")]
)
def test_publish_blocked_for_undecided_or_rejected_late_work(late_status, code):
    repo = StatefulGradingRepo()
    service, submission = _late_publish_service(repo, late_status)
    with pytest.raises(SubmissionValidationError) as caught:
        run(service.publish_grade(TEACHER, submission.id, 4, "", access_token="t"))
    assert caught.value.code == code
    assert repo.row is None and service.submissions.statuses == []


def test_publish_applies_late_penalty_and_republish_without_penalty_clears_it():
    repo = StatefulGradingRepo()
    service, submission = _late_publish_service(repo, "accepted", penalty=50.0)
    result = run(service.publish_grade(TEACHER, submission.id, 4, "Late, half marks", access_token="t"))
    assert result.final_score == 2.0
    assert result.late_penalty_percent == 50.0 and result.score_before_late_penalty == 4.0

    service.submissions = StatusRepo(submission.model_copy(update={"late_penalty_percent": 0.0}))
    result = run(service.publish_grade(TEACHER, submission.id, 4, "", access_token="t"))
    assert result.final_score == 4.0 and result.late_penalty_percent is None
    assert "late_penalty_percent" not in repo.row.flags


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


# --------------------------------------------------------------------------- teacher corrections


class MultiGradingRepo:
    """grading_results keyed by submission, with list_by_assignment returning every row."""

    def __init__(self):
        self.rows: dict = {}

    def get_by_submission_id(self, submission_id, *, access_token):
        return self.rows.get(submission_id)

    def list_by_assignment(self, assignment_id, *, access_token):
        return list(self.rows.values())

    def insert(self, data, *, access_token):
        self.rows[data.submission_id] = GradingResultRecord(
            submission_id=data.submission_id, ai_score=data.ai_score, final_score=data.ai_score,
            ai_feedback=data.ai_feedback, final_feedback=data.ai_feedback, evidence=data.evidence,
            flags=data.flags, confidence=data.confidence, status=data.status,
        )
        return self.rows[data.submission_id]

    def update_flags(self, submission_id, flags, *, access_token):
        self.rows[submission_id] = self.rows[submission_id].model_copy(update={"flags": flags})
        return self.rows[submission_id]


def _correction(number=2, marks=1.0, note="Lowercase 'nand' is the NAND gate; accept it."):
    return GradingCorrectionIn(question_number=number, teacher_marks=marks, note=note)


def test_correction_is_stored_and_followed_by_later_checks():
    captured: list = []
    repo = MultiGradingRepo()
    service, submission, _ = _service(grading_repo=repo, captured=captured)

    first = run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    assert "teacher_corrections" not in captured[0]["questions"][1]
    assert first.questions[1].teacher_corrections_used == 0

    saved = run(service.save_corrections(TEACHER, submission.id, [_correction()], access_token="t"))
    assert saved[0].ai_marks == 0.0 and saved[0].ai_explanation == "Answer not found."
    assert saved[0].question_text == "Universal gate?" and saved[0].teacher_id == TEACHER.id

    # Another student's submission of the same assignment is checked: the correction goes to the AI.
    other = submission.model_copy(update={"id": uuid4()})
    service.submissions = Repo(other)
    second = run(service.grade_submission(TEACHER, other.id, access_token="t"))
    sent_q2 = captured[1]["questions"][1]["teacher_corrections"]
    assert sent_q2 == [{
        "ai_marks": 0.0, "ai_explanation": "Answer not found.", "teacher_marks": 1.0, "max_marks": 1.0,
        "note": "Lowercase 'nand' is the NAND gate; accept it.",
    }]
    assert "teacher_corrections" not in captured[1]["questions"][0]
    assert second.questions[1].teacher_corrections_used == 1


def test_recheck_keeps_corrections_and_saved_check_returns_them():
    repo = MultiGradingRepo()
    service, submission, _ = _service(grading_repo=repo)
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    run(service.save_corrections(TEACHER, submission.id, [_correction()], access_token="t"))

    run(service.grade_submission(TEACHER, submission.id, access_token="t"))  # re-check overwrites the suggestion
    loaded = run(service.get_saved_suggestion(TEACHER, submission.id, access_token="t"))
    assert [c.note for c in loaded.teacher_corrections] == ["Lowercase 'nand' is the NAND gate; accept it."]

    run(service.save_corrections(TEACHER, submission.id, [], access_token="t"))  # empty list removes them
    assert run(service.get_saved_suggestion(TEACHER, submission.id, access_token="t")).teacher_corrections == []


def test_correction_for_an_edited_question_is_not_applied():
    captured: list = []
    repo = MultiGradingRepo()
    service, submission, _ = _service(grading_repo=repo, captured=captured)
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    run(service.save_corrections(TEACHER, submission.id, [_correction()], access_token="t"))
    row = repo.rows[submission.id]
    stale = [dict(c, question_text="An older wording of Q2") for c in row.flags["teacher_corrections"]]
    repo.rows[submission.id] = row.model_copy(update={"flags": {**row.flags, "teacher_corrections": stale}})

    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    assert "teacher_corrections" not in captured[-1]["questions"][1]


def test_correction_validation():
    repo = MultiGradingRepo()
    service, submission, _ = _service(grading_repo=repo)
    with pytest.raises(SubmissionValidationError) as no_check:
        run(service.save_corrections(TEACHER, submission.id, [_correction()], access_token="t"))
    assert no_check.value.code == "no_answer_check"

    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    for bad in ([_correction(number=3)], [_correction(marks=1.5)], [_correction(), _correction()]):
        with pytest.raises(SubmissionValidationError):
            run(service.save_corrections(TEACHER, submission.id, bad, access_token="t"))
    with pytest.raises(AssignmentNotFoundError):
        run(service.save_corrections(OTHER_TEACHER, submission.id, [_correction()], access_token="t"))
    assert "teacher_corrections" not in repo.rows[submission.id].flags


# --------------------------------------------------------------------------- student breakdown


class BreakdownRepo(StatefulGradingRepo):
    def list_by_assignment(self, assignment_id, *, access_token):
        return [self.row] if self.row else []

    def update_flags(self, submission_id, flags, *, access_token):
        self.row = self.row.model_copy(update={"flags": flags})
        return self.row


def test_student_sees_why_each_question_got_its_mark():
    repo = BreakdownRepo()
    service, submission, _ = _publish_service(repo)
    student = CurrentUser(id=submission.student_id, email=None, role=Role.STUDENT)
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    run(service.save_corrections(TEACHER, submission.id, [_correction()], access_token="t"))
    run(service.publish_grade(TEACHER, submission.id, 5, "Well done", access_token="t"))

    seen = run(service.get_published_grade(student, submission.id, access_token="t"))
    q1, q2 = seen.questions
    assert (q1.number, q1.awarded_marks, q1.max_marks) == (1, 4.0, 4.0)
    assert q1.explanation == "Correct binary." and q1.strengths == ["Accurate"] and q1.teacher_comment is None
    # The teacher changed Q2: the student sees the teacher's mark and note, not the AI's "not found".
    assert (q2.awarded_marks, q2.explanation) == (1.0, "")
    assert q2.teacher_comment == "Lowercase 'nand' is the NAND gate; accept it."
    # Answer-key-derived details never reach the student.
    dumped = seen.model_dump()
    assert "missing_concepts" not in str(dumped) and "matched_concepts" not in str(dumped)


def test_teacher_only_grade_lists_solutions_without_marks():
    repo = BreakdownRepo()
    service, submission, _ = _publish_service(repo)
    result = run(service.publish_grade(TEACHER, submission.id, 3, "", access_token="t"))
    assert [(q.number, q.awarded_marks) for q in result.questions] == [(1, None), (2, None)]
    assert [q.expected_solution for q in result.questions] == ["(110101.101)2", "B) NAND"]

    hidden = run(service.publish_grade(TEACHER, submission.id, 3, "", access_token="t", show_solutions=False))
    assert hidden.questions == []


def _past_release(repo):
    flags = dict(repo.row.flags)
    flags["solutions_visible_from"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    repo.row = repo.row.model_copy(update={"flags": flags})


def test_expected_solutions_reach_students_only_after_the_due_date():
    repo = BreakdownRepo()
    service, submission, _ = _publish_service(repo)
    student = CurrentUser(id=submission.student_id, email=None, role=Role.STUDENT)
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    run(service.publish_grade(TEACHER, submission.id, 4, "", access_token="t"))

    # Due date is 3 days away: the student sees marks and reasons, but not the solutions yet.
    early = run(service.get_published_grade(student, submission.id, access_token="t"))
    assert [q.expected_solution for q in early.questions] == [None, None]
    assert early.questions[0].explanation == "Correct binary."
    assert early.solutions_available_at is not None and early.solutions_available_at > datetime.now(UTC)
    # The teacher always sees what will be released.
    teacher_view = run(service.get_published_grade(TEACHER, submission.id, access_token="t"))
    assert teacher_view.questions[1].expected_solution == "B) NAND" and teacher_view.solutions_available_at is None

    _past_release(repo)
    later = run(service.get_published_grade(student, submission.id, access_token="t"))
    assert [q.expected_solution for q in later.questions] == ["(110101.101)2", "B) NAND"]
    assert later.solutions_available_at is None


def test_teacher_can_withhold_expected_solutions():
    repo = BreakdownRepo()
    service, submission, _ = _publish_service(repo)
    student = CurrentUser(id=submission.student_id, email=None, role=Role.STUDENT)
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    run(service.publish_grade(TEACHER, submission.id, 4, "", access_token="t", show_solutions=False))
    _past_release(repo)  # even past the due date
    seen = run(service.get_published_grade(student, submission.id, access_token="t"))
    assert [q.expected_solution for q in seen.questions] == [None, None]
    assert seen.questions[0].explanation == "Correct binary."


def test_list_published_grades_in_one_call():
    repo = BreakdownRepo()
    service, submission, _ = _publish_service(repo)
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    run(service.publish_grade(TEACHER, submission.id, 4, "ok", access_token="t"))
    published = submission.model_copy(update={"status": "published"})
    pending = submission.model_copy(update={"id": uuid4(), "status": "ocr_completed"})

    class Listing(StatusRepo):
        def list_by_student(self, student_id, *, access_token):
            return [published, pending]

        def list_by_assignment(self, assignment_id, *, access_token):
            return [published, pending]

    service.submissions = Listing(published)
    student = CurrentUser(id=submission.student_id, email=None, role=Role.STUDENT)
    mine = run(service.list_published_grades(student, access_token="t"))
    assert [g.submission_id for g in mine] == [submission.id]
    assert mine[0].final_score == 4.0
    assert mine[0].solutions_available_at is not None  # students: solutions still withheld before due date
    teacher_view = run(service.list_published_grades(TEACHER, access_token="t"))
    assert [g.submission_id for g in teacher_view] == [submission.id]
    assert teacher_view[0].questions[0].expected_solution == "(110101.101)2"
    assert run(service.list_published_grades(OTHER_TEACHER, access_token="t")) == []
