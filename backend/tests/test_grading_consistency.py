"""Grades a student can trust: no AI check of unreadable scans, no published results that contradict themselves."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.database.grading_repository import GradingResultRecord, GradingStatus
from app.schemas.grading import PublishedQuestionResult
from app.schemas.ocr import OCRDocumentResult
from app.schemas.user import Role
from app.services.auth_service import CurrentUser
from app.services.grading_service import _clean_feedback, _published_response
from app.services.submission_service import SubmissionValidationError
from tests.test_grading_service import (
    TEACHER,
    BreakdownRepo,
    _publish_service,
    _service,
    run,
)


def _blank_ocr():
    """What OCR returns when the provider rejected its key: pages, but no text."""
    return OCRDocumentResult.model_validate(
        {
            "job_id": "job-1",
            "submission_id": "s",
            "pages": [
                {"page_id": "p1", "page_number": 1, "width": 10, "height": 10, "full_text": "  ", "text_blocks": [],
                 "warnings": ["OCR.space unavailable (E555: API key not valid)"]},
            ],
        }
    )


def test_unreadable_submission_is_not_sent_to_the_ai():
    calls = []
    service, submission, _ = _service(ocr=_blank_ocr(), captured=calls)
    with pytest.raises(SubmissionValidationError) as caught:
        run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    assert caught.value.code == "no_readable_text"
    assert calls == []  # the AI never saw empty text, so it cannot claim "no answer was submitted"


def test_teacher_score_that_differs_from_ai_marks_hides_the_ai_breakdown():
    repo = BreakdownRepo()
    service, submission, _ = _publish_service(repo)
    student = CurrentUser(id=submission.student_id, email=None, role=Role.STUDENT)
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))  # AI: 4 + 0 = 4/5
    published = run(service.publish_grade(TEACHER, submission.id, 5, "Q2 was right after all.", access_token="t"))
    # Solutions stay (students get them after the due date; the teacher's view shows them now).
    assert [q.expected_solution for q in published.questions] == ["(110101.101)2", "B) NAND"]

    seen = run(service.get_published_grade(student, submission.id, access_token="t"))
    assert seen.final_score == 5
    assert [q.awarded_marks for q in seen.questions] == [None, None]
    assert all(q.explanation == "" and not q.strengths for q in seen.questions)


def test_teacher_score_matching_ai_marks_keeps_the_breakdown():
    repo = BreakdownRepo()
    service, submission, _ = _publish_service(repo)
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    result = run(service.publish_grade(TEACHER, submission.id, 4, "", access_token="t"))
    assert [q.awarded_marks for q in result.questions] == [4.0, 0.0]


def _record(score, questions, feedback="", **flags):
    return GradingResultRecord(
        submission_id=uuid4(), ai_score=Decimal("0"), final_score=Decimal(str(score)), ai_feedback="",
        final_feedback=feedback, evidence={}, confidence=Decimal("1"), status=GradingStatus.PUBLISHED,
        published_at=datetime.now(UTC),
        flags={"max_score": 10, "student_breakdown": [q.model_dump(mode="json") for q in questions], **flags},
    )


def _q(number, marks, explanation="No answer was submitted for this question."):
    return PublishedQuestionResult(
        number=number, question_text=f"Q{number}", awarded_marks=marks, max_marks=5, explanation=explanation
    )


def test_already_published_contradiction_is_fixed_when_read():
    """Grades published before this fix: final 7/10 but every question frozen at 0/5."""
    seen = _published_response(_record(7, [_q(1, 0), _q(2, 0)]), for_student=True)
    assert [q.awarded_marks for q in seen.questions] == [None, None]
    assert all("No answer" not in q.explanation for q in seen.questions)


def test_late_penalty_compares_marks_with_the_score_before_the_deduction():
    seen = _published_response(
        _record(4, [_q(1, 5, "Good"), _q(2, 3, "Ok")], late_penalty_percent=50, score_before_late_penalty=8)
    )
    assert [q.awarded_marks for q in seen.questions] == [5.0, 3.0]


def test_ai_score_heading_disagreeing_with_final_score_is_removed():
    feedback = (
        "### Overall Assignment Feedback (Score: 3.0/20.0 — 15.0%)\n\n"
        "**Key Strengths:**\n- Clear description of the stupa\n\nScore: 3.0/20"
    )
    seen = _published_response(_record(10, [], feedback), for_student=True)
    assert "3.0" not in seen.final_feedback
    assert "Overall Assignment Feedback" not in seen.final_feedback
    assert "**Key Strengths:**\n- Clear description of the stupa" in seen.final_feedback


def test_score_mention_matching_final_score_is_kept():
    assert _clean_feedback("Well argued. Score: 10/20", 10) == "Well argued. Score: 10/20"
