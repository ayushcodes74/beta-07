"""Answer-check scoring policy: full marks at a configurable share of key-point coverage."""

from app.core.config import settings
from app.schemas.grading import QuestionGradeSuggestion
from app.services.grading_service import _apply_full_marks_policy
from test_grading_service import AI_RESULT, TEACHER, _service, run


def _q(number, awarded, max_marks):
    return QuestionGradeSuggestion(
        number=number, question_text="q", question_type="subjective",
        max_marks=max_marks, awarded_marks=awarded, explanation="",
    )


def test_seventy_percent_coverage_earns_full_marks():
    questions = [_q(1, 2.8, 7), _q(2, 4.9, 7), _q(3, 7, 7), _q(4, 0, 6)]
    feedback = "### Overall Assignment Feedback (Score: 14.7/27.0 — 54.4%)\nKeep going."

    total, percentage, new_feedback = _apply_full_marks_policy(questions, 0.7, 27.0, feedback)

    assert [q.awarded_marks for q in questions] == [4.0, 7.0, 7.0, 0.0]  # 2.8/0.7=4; 4.9 = 70% -> full; capped
    assert [q.raw_awarded_marks for q in questions] == [2.8, 4.9, 7, 0]
    assert total == 18.0 and percentage == 66.67
    assert "(Score: 18.0/27.0 — 66.7%)" in new_feedback and "Keep going." in new_feedback


def test_policy_applied_in_answer_check(monkeypatch):
    monkeypatch.setattr(settings, "GRADING_FULL_MARKS_AT", 0.5)
    service, submission, _ = _service()  # AI result: q1 4/4, q2 0/1

    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))

    assert result.scoring == {"full_marks_at": 0.5, "raw_total": AI_RESULT["total_awarded_marks"]}
    assert [q.awarded_marks for q in result.questions] == [4.0, 0.0]
    assert [q.raw_awarded_marks for q in result.questions] == [4.0, 0.0]


def test_policy_off_at_one(monkeypatch):
    monkeypatch.setattr(settings, "GRADING_FULL_MARKS_AT", 1.0)
    service, submission, _ = _service()

    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))

    assert result.scoring is None
    assert all(q.raw_awarded_marks is None for q in result.questions)
    assert result.total_awarded_marks == AI_RESULT["total_awarded_marks"]
