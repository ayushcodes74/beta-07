"""Tests for POST /v1/grading/grade-submission. No LLM calls are made."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import server
from app.llm.gemini_client import LLMConfigError, LLMRateLimitError, LLMResponseValidationError, LLMTimeoutError
from app.schemas.grading import CriterionEvaluation, GradingResult, QuestionGrade


class FakeEvaluator:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple] = []

    def grade_submission(self, submission_id, assignment_id, requests, evidence=None):
        self.calls.append((submission_id, assignment_id, requests))
        if self.error:
            raise self.error
        grades = [
            QuestionGrade(
                question_id=r.question_id,
                max_marks=r.question_max_marks,
                awarded_marks=r.question_max_marks / 2,
                criterion_evaluations=[
                    CriterionEvaluation(
                        criterion_id="c1",
                        max_marks=r.question_max_marks,
                        awarded_marks=r.question_max_marks / 2,
                        explanation="Partially correct.",
                    )
                ],
                overall_explanation="Half marks.",
            )
            for r in requests
        ]
        return GradingResult(
            submission_id=submission_id,
            assignment_id=assignment_id,
            total_awarded_marks=sum(g.awarded_marks for g in grades),
            total_max_marks=sum(g.max_marks for g in grades),
            question_results=grades,
            overall_feedback="Keep going.",
        )


@pytest.fixture(autouse=True)
def isolated_index(tmp_path, monkeypatch):
    """Never touch the real persistent course index from these tests."""
    from app.rag.course_index import CourseMaterialIndex

    index = CourseMaterialIndex(root=tmp_path / "rag")
    monkeypatch.setattr(server, "get_course_index", lambda: index)
    return index


@pytest.fixture
def fake(monkeypatch):
    evaluator = FakeEvaluator()
    monkeypatch.setattr(server, "get_evaluator", lambda: evaluator)
    return evaluator


@pytest.fixture
def client():
    return TestClient(server.app)


BODY = {
    "submission_id": "sub-1",
    "assignment_id": "asg-1",
    "course_id": "course-1",
    "student_text": "Q1: 53.625 = (110101.101)2\nQ2: B",
    "ocr_confidence": 0.9,
    "questions": [
        {
            "question_id": "q1",
            "type": "subjective",
            "text": "Convert 53.625 to binary.",
            "marks": 4,
            "expected_answer": "110101.101",
            "instructions": "Show the division table.",
        },
        {
            "question_id": "q2",
            "type": "mcq",
            "text": "Which gate is universal?",
            "marks": 1,
            "options": [{"id": "A", "text": "XOR"}, {"id": "B", "text": "NAND"}],
            "correct_option_id": "B",
        },
    ],
}


def test_grades_each_question_against_answer_key(client, fake):
    response = client.post("/v1/grading/grade-submission", json=BODY)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_awarded_marks"] == 2.5
    assert body["total_max_marks"] == 5
    assert [q["question_id"] for q in body["question_results"]] == ["q1", "q2"]

    _, _, requests = fake.calls[0]
    q1, q2 = requests
    # Whole transcript goes to every question, with a hint to grade only that question's part
    assert q1.student_answer == BODY["student_text"]
    assert "question 1" in q1.instructions and "Show the division table." in q1.instructions
    assert q1.expected_answer == "110101.101"
    assert q1.ocr_confidence == 0.9
    # Handwritten MCQ: graded as text against the correct option, not by option id
    assert q2.correct_option_id is None
    assert q2.expected_answer == "Correct option: B) NAND"
    assert "B) NAND" in q2.question_text and "question 2" in q2.instructions


def test_validates_request(client, fake):
    assert client.post("/v1/grading/grade-submission", json={**BODY, "questions": []}).status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize(
    "error, expected_status",
    [
        (LLMConfigError("no key"), 503),
        (LLMRateLimitError("429"), 429),
        (LLMTimeoutError("slow"), 504),
        (LLMResponseValidationError("bad json", raw_response="{}"), 502),
    ],
)
def test_maps_llm_errors(client, monkeypatch, error, expected_status):
    monkeypatch.setattr(server, "get_evaluator", lambda: FakeEvaluator(error))
    assert client.post("/v1/grading/grade-submission", json=BODY).status_code == expected_status


Q1_KEY = """The stupa consists of a large hemispherical brick dome, later enlarged and covered in stone.

Key points:
- Large hemispherical brick dome (1 mark)
- Later enlarged and covered in stone (1 mark)
- Built over sacred relics of the Buddha (1 mark)
- Topped by a harmika (1 mark)
- Triple-tiered umbrella (chatra) (1 mark)

Rubric:
- Accurately describes the main dome structure and its contents. (3.34 marks)
- Accurately describes the top structures of the stupa. (3.33 marks)"""


def test_key_points_become_per_point_criteria_scaled_to_question_marks():
    rubric = server._rubric_from_mark_scheme(Q1_KEY, 7)
    assert rubric is not None
    assert [c.description for c in rubric.criteria] == [
        "Large hemispherical brick dome",
        "Later enlarged and covered in stone",
        "Built over sacred relics of the Buddha",
        "Topped by a harmika",
        "Triple-tiered umbrella (chatra)",
    ]
    assert [c.max_marks for c in rubric.criteria] == [1.4, 1.4, 1.4, 1.4, 1.4]  # 5 key-point marks -> 7
    assert abs(sum(c.max_marks for c in rubric.criteria) - 7) < 1e-9


Q2_KEY = "Key points:\n- A (1 mark)\n- B (2 marks)\n- C (1 mark)\n- D (1 mark)\n- E (1 mark)\n- F (1 mark)\n- G (1 mark)"


def test_over_allocated_key_keeps_written_point_marks():
    rubric = server._rubric_from_mark_scheme(Q2_KEY, 7)  # 8 marks of points for a 7-mark question
    # Lenient: 1 written mark stays 1 mark (no scaling down); the total is capped later
    assert [c.max_marks for c in rubric.criteria] == [1, 2, 1, 1, 1, 1, 1]
    assert rubric.total_marks == 8


class FullMarksEvaluator(FakeEvaluator):
    """Awards every question its full (rubric) marks, e.g. 8 on an 8-mark-of-points scheme."""

    def grade_submission(self, submission_id, assignment_id, requests, evidence=None):
        self.calls.append((submission_id, assignment_id, requests))
        grades = [
            QuestionGrade(
                question_id=r.question_id,
                max_marks=r.question_max_marks,
                awarded_marks=r.question_max_marks,
                criterion_evaluations=[
                    CriterionEvaluation(criterion_id="c1", max_marks=r.question_max_marks,
                                        awarded_marks=r.question_max_marks, explanation="All points.")
                ],
                overall_explanation="Complete.",
            )
            for r in requests
        ]
        return GradingResult(
            submission_id=submission_id, assignment_id=assignment_id,
            total_awarded_marks=sum(g.awarded_marks for g in grades),
            total_max_marks=sum(g.max_marks for g in grades),
            question_results=grades, overall_feedback="x",
        )


def test_over_allocated_question_is_capped_at_its_marks(client, monkeypatch):
    evaluator = FullMarksEvaluator()
    monkeypatch.setattr(server, "get_evaluator", lambda: evaluator)
    body = {**BODY, "questions": [{**BODY["questions"][0], "marks": 7, "expected_answer": Q2_KEY}]}

    response = client.post("/v1/grading/grade-submission", json=body)

    assert response.status_code == 200, response.text
    assert evaluator.calls[0][2][0].question_max_marks == 8  # graded on the written scheme
    result = response.json()
    assert result["question_results"][0]["awarded_marks"] == 7
    assert result["question_results"][0]["max_marks"] == 7
    assert result["total_awarded_marks"] == 7 and result["total_max_marks"] == 7
    assert result["percentage"] == 100.0
    assert "7.0/7.0" in result["overall_feedback"]


def test_lenient_marking_instructions_are_sent(client, fake):
    client.post("/v1/grading/grade-submission", json=BODY)
    for request in fake.calls[0][2]:
        assert "LENIENTLY" in request.instructions


def test_rubric_section_used_when_no_key_points_and_none_without_marks():
    rubric = server._rubric_from_mark_scheme("Rubric:\n- Dome described (3 marks)\n- Top described (3 marks)", 6)
    assert [c.max_marks for c in rubric.criteria] == [3, 3]
    assert server._rubric_from_mark_scheme("Just a model answer with no marks.", 5) is None


def test_request_carries_per_point_rubric(client, fake):
    body = {**BODY, "questions": [{**BODY["questions"][0], "marks": 7, "expected_answer": Q1_KEY}]}
    assert client.post("/v1/grading/grade-submission", json=body).status_code == 200
    request = fake.calls[0][2][0]
    assert request.rubric is not None and len(request.rubric.criteria) == 5
    assert "independently" in request.instructions


class PartialEvidenceEvaluator(FakeEvaluator):
    """LLM-style output: evidence found for the 2-mark point but 0 awarded (the inconsistency we saw)."""

    def grade_submission(self, submission_id, assignment_id, requests, evidence=None):
        self.calls.append((submission_id, assignment_id, requests))
        crits = [
            CriterionEvaluation(criterion_id="point_1", max_marks=1, awarded_marks=1, explanation="ok",
                                matched_concepts=["four carved gateways"]),
            CriterionEvaluation(criterion_id="point_4", max_marks=2, awarded_marks=0, explanation="only general",
                                matched_concepts=["intricate carvings"]),
            CriterionEvaluation(criterion_id="point_5", max_marks=5, awarded_marks=0, explanation="absent"),
        ]
        grade = QuestionGrade(question_id=requests[0].question_id, max_marks=8, awarded_marks=1,
                              criterion_evaluations=crits, overall_explanation="x")
        return GradingResult(submission_id=submission_id, assignment_id=assignment_id, total_awarded_marks=1,
                             total_max_marks=8, question_results=[grade], overall_feedback="x")


def test_point_with_evidence_gets_at_least_half_marks(client, monkeypatch):
    monkeypatch.setattr(server, "get_evaluator", lambda: PartialEvidenceEvaluator())
    body = {**BODY, "questions": [{**BODY["questions"][0], "marks": 7, "expected_answer": Q2_KEY}]}

    result = client.post("/v1/grading/grade-submission", json=body).json()

    q = result["question_results"][0]
    by_id = {c["criterion_id"]: c["awarded_marks"] for c in q["criterion_evaluations"]}
    assert by_id == {"point_1": 1, "point_4": 1, "point_5": 0}  # evidence -> half; no evidence -> unchanged
    assert q["awarded_marks"] == 2 and q["max_marks"] == 7
    assert result["total_awarded_marks"] == 2
