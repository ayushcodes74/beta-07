"""AI-assisted assignment drafting: mapping, HTTP client, and endpoint (no AI Engine or Gemini calls)."""

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from uuid import uuid4

from app.api.v1.endpoints import ai_generation
from app.core.dependencies import get_token_verifier
from app.schemas.ai_generation import AssignmentGenerationRequest, GeneratedAssignmentDraft, GeneratedQuestion
from app.services.ai_generation_service import (
    AIGenerationService,
    AIRateLimitedError,
    AIServiceUnavailableError,
    get_ai_generation_service,
    map_engine_draft,
    whole_marks,
)
from app.services.user_service import get_profile_repository
from conftest import bearer

URL = "/api/v1/assignments/generate-ai"


def engine_draft(**overrides):
    draft = {
        "title": "Newton's Laws Quiz",
        "instructions": "Answer all questions.",
        "questions": [
            {
                "question_type": "MCQ",
                "question_text": "Which law describes inertia?",
                "marks": 6.67,
                "mcq_options": [
                    {"id": "A", "text": "First law", "is_correct": True, "explanation": "Objects keep their state."},
                    {"id": "B", "text": "Second law", "is_correct": False},
                    {"id": "C", "text": "Third law", "is_correct": False},
                ],
            },
            {
                "question_type": "SUBJECTIVE",
                "question_text": "Explain F = ma with an example.",
                "marks": 6.67,
                "model_answer": {"text": "Force equals mass times acceleration.", "key_points": ["F = ma"]},
                "rubric": {"criteria": [{"description": "States the law", "max_marks": 3.0}], "total_marks": 6.67},
            },
            {"question_type": "SUBJECTIVE", "question_text": "Describe action and reaction.", "marks": 6.66},
        ],
    }
    draft.update(overrides)
    return draft


# --------------------------------------------------------------------------
# Mark splitting and draft mapping
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("weights", "total"),
    [([6.67, 6.67, 6.66], 20), ([1, 1, 1], 3), ([5, 1], 7), ([0, 0], 4), ([3.3] * 7, 10)],
)
def test_whole_marks_are_integers_at_least_one_and_sum_to_total(weights, total):
    marks = whole_marks(weights, total)
    assert sum(marks) == total
    assert all(isinstance(m, int) and m >= 1 for m in marks)


def test_whole_marks_keeps_proportions():
    assert whole_marks([6.0, 2.0], 8) == [6, 2]


def test_map_engine_draft_builds_editor_questions():
    draft = map_engine_draft(engine_draft(), total_marks=20)

    assert draft.title == "Newton's Laws Quiz"
    assert draft.grounded_in_course_materials is False
    assert [q.marks for q in draft.questions] and sum(q.marks for q in draft.questions) == 20
    mcq, explain, describe = draft.questions
    assert mcq.type == "mcq"
    assert mcq.options == ["First law", "Second law", "Third law"]
    assert mcq.correct_option_index == 0
    assert "Correct answer: First law" in mcq.expected_answer
    assert explain.type == "subjective"
    assert "Force equals mass times acceleration." in explain.expected_answer
    assert "- F = ma" in explain.expected_answer
    assert "States the law (3 marks)" in explain.expected_answer
    assert describe.expected_answer == ""


def test_map_engine_draft_drops_malformed_mcq_and_rebalances_marks():
    bad = {"question_type": "MCQ", "question_text": "Broken MCQ?", "marks": 5,
           "mcq_options": [{"id": "A", "text": "Only one", "is_correct": False}]}
    draft = map_engine_draft(engine_draft(questions=[bad, *engine_draft()["questions"][1:]]), total_marks=10)

    assert [q.type for q in draft.questions] == ["subjective", "subjective"]
    assert sum(q.marks for q in draft.questions) == 10


def test_map_engine_draft_rejects_empty_result():
    with pytest.raises(ValueError):
        map_engine_draft(engine_draft(questions=[{"question_type": "SUBJECTIVE", "question_text": "  "}]), 10)


def test_request_requires_a_whole_mark_per_question():
    with pytest.raises(ValueError):
        AssignmentGenerationRequest(topic="Optics", question_count=5, total_marks=3)


# --------------------------------------------------------------------------
# HTTP client against a mocked AI Engine
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_service_translates_request_and_maps_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=engine_draft())

    service = AIGenerationService(base_url="http://ai.test", transport=httpx.MockTransport(handler))
    draft = await service.generate(
        AssignmentGenerationRequest(topic="Newton's laws", question_count=3, question_format="mixed",
                                    difficulty="mixed", total_marks=20, instructions="Use SI units.")
    )

    assert seen["path"] == "/v1/assignments/generate"
    body = seen["body"]
    assert body["question_type"] == "MIXED" and body["difficulty"] == "MEDIUM"
    assert body["total_marks"] == 20.0 and body["question_count"] == 3
    assert "Use SI units." in body["teacher_instructions"]
    assert "Vary the difficulty" in body["teacher_instructions"]
    assert body["course_id"] == "unscoped"
    assert sum(q.marks for q in draft.questions) == 20


@pytest.mark.anyio
@pytest.mark.parametrize(("status_code", "error"), [(503, AIServiceUnavailableError), (429, AIRateLimitedError)])
async def test_service_maps_engine_status_codes(status_code, error):
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json={"detail": "x"}))
    service = AIGenerationService(base_url="http://ai.test", transport=transport)

    with pytest.raises(error):
        await service.generate(AssignmentGenerationRequest(topic="Optics"))


@pytest.mark.anyio
async def test_service_reports_unreachable_engine():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    service = AIGenerationService(base_url="http://ai.test", transport=httpx.MockTransport(handler))

    with pytest.raises(AIServiceUnavailableError):
        await service.generate(AssignmentGenerationRequest(topic="Optics"))


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------


class FakeAIService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.requests: list[AssignmentGenerationRequest] = []

    async def generate(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return GeneratedAssignmentDraft(
            title="Draft",
            questions=[GeneratedQuestion(type="subjective", text="Explain inertia.", marks=request.total_marks,
                                         expected_answer="Objects resist changes in motion.")],
            grounded_in_course_materials=False,
        )


@pytest.fixture
def fake_ai() -> FakeAIService:
    return FakeAIService()


@pytest.fixture
def api(verifier, profiles, fake_ai) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(ai_generation.router, prefix="/api/v1")
    test_app.dependency_overrides[get_token_verifier] = lambda: verifier
    test_app.dependency_overrides[get_profile_repository] = lambda: profiles
    test_app.dependency_overrides[get_ai_generation_service] = lambda: fake_ai
    return TestClient(test_app)


@pytest.fixture
def make_user(make_token, profiles):
    def _make(role: str) -> dict[str, str]:
        user_id = uuid4()
        profiles.add(user_id, role)
        return bearer(make_token(user_id))

    return _make


BODY = {"topic": "Newton's laws", "question_count": 2, "question_format": "subjective", "total_marks": 10}


def test_teacher_gets_draft(api, make_user, fake_ai):
    response = api.post(URL, json=BODY, headers=make_user("teacher"))

    assert response.status_code == 200, response.text
    assert response.json()["questions"][0]["text"] == "Explain inertia."
    assert fake_ai.requests[0].topic == "Newton's laws"


def test_student_is_forbidden(api, make_user, fake_ai):
    response = api.post(URL, json=BODY, headers=make_user("student"))

    assert response.status_code == 403
    assert fake_ai.requests == []


def test_requires_authentication(api, fake_ai):
    assert api.post(URL, json=BODY).status_code == 401
    assert fake_ai.requests == []


def test_invalid_request_is_rejected_before_calling_ai(api, make_user, fake_ai):
    response = api.post(URL, json={**BODY, "question_count": 5, "total_marks": 3}, headers=make_user("teacher"))

    assert response.status_code == 422
    assert fake_ai.requests == []


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [(AIServiceUnavailableError("down"), 503, "ai_unavailable"), (AIRateLimitedError("busy"), 429, "ai_rate_limited")],
)
def test_ai_errors_map_to_http(api, make_user, fake_ai, error, status_code, code):
    fake_ai.error = error

    response = api.post(URL, json=BODY, headers=make_user("teacher"))

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
