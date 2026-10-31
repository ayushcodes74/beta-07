"""Tests for the internal HTTP wrapper (app/server.py). No Gemini calls are made."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import server
from app.llm.gemini_client import LLMConfigError, LLMRateLimitError, LLMResponseValidationError
from app.schemas.assignment import AssignmentDraft, DifficultyLevel, QuestionDraft, QuestionType


class FakeGenerator:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple] = []

    def generate_assignment(self, request, course_materials=None):
        self.calls.append((request, course_materials))
        if self.error:
            raise self.error
        return AssignmentDraft(
            assignment_id="asgn_test",
            course_id=request.course_id,
            topic=request.topic,
            title=f"{request.topic} quiz",
            total_marks=request.total_marks,
            questions=[
                QuestionDraft(
                    question_id="q_1",
                    question_type=QuestionType.SUBJECTIVE,
                    question_text="Explain Newton's first law.",
                    marks=request.total_marks,
                    difficulty=DifficultyLevel.MEDIUM,
                )
            ],
        )


@pytest.fixture
def fake(monkeypatch):
    generator = FakeGenerator()
    monkeypatch.setattr(server, "get_generator", lambda: generator)
    return generator


@pytest.fixture
def client():
    return TestClient(server.app)


BODY = {"course_id": "c1", "topic": "Newton's laws", "question_count": 3, "total_marks": 10}


def test_generate_returns_draft_and_passes_request_through(client, fake):
    response = client.post("/v1/assignments/generate", json={**BODY, "course_materials": "Inertia notes"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["questions"][0]["question_text"] == "Explain Newton's first law."
    request, materials = fake.calls[0]
    assert request.topic == "Newton's laws" and request.question_count == 3
    assert materials == "Inertia notes"


def test_generate_validates_request(client, fake):
    response = client.post("/v1/assignments/generate", json={**BODY, "question_count": 0})

    assert response.status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (LLMConfigError("no key"), 503),
        (LLMRateLimitError("slow down"), 429),
        (LLMResponseValidationError("bad json", raw_response="{}"), 502),
    ],
)
def test_generate_maps_llm_errors(client, monkeypatch, error, expected_status):
    monkeypatch.setattr(server, "get_generator", lambda: FakeGenerator(error))

    response = client.post("/v1/assignments/generate", json=BODY)

    assert response.status_code == expected_status
    assert "no key" not in response.text  # internal error details are not leaked


def test_health_reports_configuration(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert set(response.json()) == {"status", "gemini_configured", "model"}
