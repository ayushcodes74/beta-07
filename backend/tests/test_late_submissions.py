"""Belated submissions: the owning teacher accepts (with a mark deduction), rejects or re-opens late work.

Lateness itself is decided by the database trigger in phase3b_late_submissions.sql; these tests
cover the service rules on top of it. No database or network.
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.schemas.grading import LateDecisionRequest
from app.schemas.user import Role
from app.services.assignment_service import AssignmentService
from app.services.auth_service import CurrentUser
from app.services.submission_service import (
    SubmissionNotFoundError,
    SubmissionPermissionError,
    SubmissionRecord,
    SubmissionService,
    SubmissionValidationError,
)

TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
OTHER_TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
ASSIGNMENT_ID = uuid4()


class AssignmentRepo:
    def is_owned_by(self, assignment_id, teacher_id, *, access_token):
        return assignment_id == ASSIGNMENT_ID and teacher_id == TEACHER.id


class SubmissionRepo:
    def __init__(self, record):
        self.record = record
        self.decisions = []

    def get(self, submission_id, *, access_token):
        return self.record if self.record.id == submission_id else None

    def set_late_decision(self, submission_id, late_status, penalty_percent, note, *, access_token):
        self.decisions.append((late_status, penalty_percent, note))
        self.record = self.record.model_copy(
            update={"late_status": late_status, "late_penalty_percent": penalty_percent, "late_decision_note": note}
        )
        return self.record


def _submission(late_status="pending", status="ocr_completed"):
    now = datetime.now(UTC).isoformat()
    return SubmissionRecord(
        id=uuid4(), assignment_id=ASSIGNMENT_ID, student_id=uuid4(), filename="a.pdf", ocr_job_id="job-1",
        status=status, created_at=now, updated_at=now, submitted_at=now, late_status=late_status,
    )


def _service(record):
    repo = SubmissionRepo(record)
    return SubmissionService(repo, AssignmentService(AssignmentRepo()), ocr_client=None), repo


def decide(service, user, record, decision, penalty=0, note=""):
    return asyncio.run(service.decide_late_submission(user, record.id, decision, penalty, note, access_token="t"))


def test_accept_with_half_marks():
    record = _submission()
    service, repo = _service(record)
    result = decide(service, TEACHER, record, "accepted", 50, "  Medical note received.  ")
    assert (result.late_status, result.late_penalty_percent) == ("accepted", 50)
    assert repo.decisions == [("accepted", 50, "Medical note received.")]


def test_reject_drops_penalty_and_pending_clears_note():
    record = _submission()
    service, repo = _service(record)
    decide(service, TEACHER, record, "rejected", 80, "Two weeks late.")
    decide(service, TEACHER, record, "pending", 0, "ignored")
    assert repo.decisions == [("rejected", None, "Two weeks late."), ("pending", None, None)]


def test_on_time_submission_cannot_get_a_late_decision():
    record = _submission(late_status=None)
    service, repo = _service(record)
    with pytest.raises(SubmissionValidationError) as caught:
        decide(service, TEACHER, record, "accepted")
    assert caught.value.code == "not_late" and repo.decisions == []


def test_decision_locked_after_grade_published():
    record = _submission(late_status="accepted", status="published")
    service, repo = _service(record)
    with pytest.raises(SubmissionValidationError) as caught:
        decide(service, TEACHER, record, "rejected")
    assert caught.value.code == "grade_already_published" and repo.decisions == []


def test_only_the_owning_teacher_decides():
    record = _submission()
    service, repo = _service(record)
    with pytest.raises(SubmissionNotFoundError):
        decide(service, OTHER_TEACHER, record, "accepted")
    student = CurrentUser(id=record.student_id, email=None, role=Role.STUDENT)
    with pytest.raises(SubmissionPermissionError):
        decide(service, student, record, "accepted")
    assert repo.decisions == []


@pytest.mark.parametrize("body", [{"decision": "accepted", "penalty_percent": 101}, {"decision": "maybe"}])
def test_request_validation(body):
    with pytest.raises(ValueError):
        LateDecisionRequest.model_validate(body)
