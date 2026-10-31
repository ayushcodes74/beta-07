"""Splitting the OCR transcript by question number so each question is graded only on its own answer.

Regression: a blank Q3 was credited with Q1/Q2 content because every question saw the whole transcript.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import server
from app.grading.evaluator import AnswerEvaluator
from app.rag.course_index import CourseMaterialIndex
from app.server import _segment_answers
from tests.test_grading_endpoint import FakeEvaluator

TRANSCRIPT = """[Page 1]
1.Describe the physical structure of the stupa as outlined in the course notes.
vAns- A massive hemispherical dome o 16.46 meters
and 36.6 metres in diameter having relics of Buddha.
2. Explain the features of the Toranas.
Ans. The Toranas are the four beautifully carved gatewaye placed at the cardinal dirlctions."""


def test_segments_by_question_number():
    segments = _segment_answers(TRANSCRIPT, 3)
    assert set(segments) == {1, 2}
    assert "hemispherical dome" in segments[1] and "Toranas" not in segments[1]
    assert segments[2].startswith("2. Explain") and "gatewaye" in segments[2]


@pytest.mark.parametrize(
    "text",
    [
        "2 53 0.25x2=0.5\n1.25 x 2 = 2.5\n16.46 metres",  # numbers/decimals are not question markers
        "1. only one numbered answer on a three-question paper",
        "no numbering at all",
    ],
)
def test_unreliable_numbering_falls_back(text):
    assert _segment_answers(text, 3) is None


def test_prefixed_markers_and_out_of_order_numbers():
    segments = _segment_answers("Q1. dome\nQ.2 gateways\n1. stray list item\nQuestion 3: UNESCO 1989", 3)
    assert segments == {1: "Q1. dome", 2: "Q.2 gateways\n1. stray list item", 3: "Question 3: UNESCO 1989"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    index = CourseMaterialIndex(root=tmp_path / "rag")
    monkeypatch.setattr(server, "get_course_index", lambda: index)
    return TestClient(server.app)


def _body():
    return {
        "submission_id": "s", "assignment_id": "a", "student_text": TRANSCRIPT, "ocr_confidence": 0.95,
        "questions": [
            {"question_id": f"q{i}", "type": "subjective", "marks": 6, "text": f"Question {i}",
             "expected_answer": "Key points:\n- Point A (3 marks)\n- Point B (3 marks)"}
            for i in (1, 2, 3)
        ],
    }


def test_each_question_gets_only_its_own_answer(client, monkeypatch):
    fake = FakeEvaluator()
    monkeypatch.setattr(server, "get_evaluator", lambda: fake)

    result = client.post("/v1/grading/grade-submission", json=_body()).json()

    q1, q2, q3 = fake.calls[0][2]
    assert "hemispherical dome" in q1.student_answer and "Toranas" not in q1.student_answer
    assert "gatewaye" in q2.student_answer and "hemispherical" not in q2.student_answer
    assert q3.student_answer == ""  # blank: never sees Q1/Q2 content
    assert "under question 1" in q1.instructions
    flagged = {q["question_id"]: q["review_reasons"] for q in result["question_results"]}
    assert any("No answer was found under question 3" in r for r in flagged["q3"])
    assert not any("No answer was found" in r for r in flagged["q1"])
    assert result["review_required"] is True


def test_blank_question_scores_zero_without_llm_call():
    class NoLLM:
        def generate_structured(self, *args, **kwargs):
            raise AssertionError("blank answers must not reach the LLM")

    body = server.GradeSubmissionRequest.model_validate(_body())
    request = server._to_grading_request(body, body.questions[2], 3, "")  # Q3: no answer found

    grade = AnswerEvaluator(gemini_client=NoLLM()).evaluate_question(
        request, retrieved_evidence=[], source_references=[], skip_evidence_retrieval=True
    )

    assert grade.awarded_marks == 0.0
    assert grade.overall_explanation == "No answer was submitted for this question."
