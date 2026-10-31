"""Tests for multi-provider LLM failover (OpenRouter primary, Gemini backup) and the OpenRouter client.

No network calls: providers are mocks and HTTP goes through httpx.MockTransport.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import List
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import BaseModel

from app.assignment.generator import AssignmentGenerator, _GeneratedAssignmentResponse, _GeneratedQuestion
from app.assignment.rubric_generator import RubricGenerator
from app.config import Settings
from app.llm.fallback_client import (
    AllProvidersFailedError,
    FallbackLLMClient,
    ProviderEntry,
    build_providers,
)
from app.llm.gemini_client import (
    GeminiClient,
    LLMAPIError,
    LLMConfigError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.llm.openai_compatible_client import LLMConnectionError, OpenAICompatibleClient
from app.schemas.assignment import (
    AssignmentGenerationRequest,
    DifficultyLevel,
    MCQOption,
    QuestionType,
    Rubric,
    RubricCriterion,
)


class _Out(BaseModel):
    answer: str
    score: float


def _settings(**overrides) -> Settings:
    base = Settings(
        gemini_api_key=None, openrouter_api_key=None,
        gemini_fallback_models=[], openrouter_fallback_models=[], llm_provider_order=["openrouter", "gemini"],
        llm_retries_per_provider=0, max_retries=0,
    )
    return replace(base, **overrides)


def _entry(name: str, side_effect=None, return_value=None) -> ProviderEntry:
    client = MagicMock()
    client.generate_structured.side_effect = side_effect
    client.generate_structured.return_value = return_value
    client.generate_text.side_effect = side_effect
    client.generate_text.return_value = return_value
    return ProviderEntry(name, f"{name}-model", client)


# ---------------------------------------------------------------------------
# FallbackLLMClient
# ---------------------------------------------------------------------------

def test_primary_success_does_not_touch_fallbacks():
    primary = _entry("openrouter", return_value=_Out(answer="a", score=1))
    backup = _entry("gemini")
    client = FallbackLLMClient([primary, backup], settings=_settings())

    assert client.generate_structured("p", _Out).answer == "a"
    backup.client.generate_structured.assert_not_called()


@pytest.mark.parametrize("error", [
    LLMRateLimitError("quota", status_code=429),
    LLMTimeoutError("slow", status_code=504),
    LLMAPIError("500", status_code=500),
    LLMConfigError("no key"),
    LLMResponseValidationError("bad json", raw_response="{"),
])
def test_falls_back_to_next_provider_on_any_llm_error(error):
    primary = _entry("openrouter", side_effect=error)
    backup = _entry("gemini", return_value=_Out(answer="from gemini", score=2))
    client = FallbackLLMClient([primary, backup], settings=_settings())

    result = client.generate_structured("p", _Out, system_instruction="sys")

    assert result.answer == "from gemini"
    kwargs = backup.client.generate_structured.call_args.kwargs
    assert kwargs["model"] == "gemini-model"  # each provider gets its own model name
    assert kwargs["system_instruction"] == "sys"


def test_generate_text_also_fails_over():
    client = FallbackLLMClient(
        [_entry("openrouter", side_effect=LLMRateLimitError("x")), _entry("gemini", return_value="hello")],
        settings=_settings(),
    )
    assert client.generate_text("p") == "hello"


def test_caller_errors_are_not_retried_on_other_providers():
    primary = _entry("openrouter", side_effect=ValueError("Prompt cannot be empty."))
    backup = _entry("gemini")
    with pytest.raises(ValueError):
        FallbackLLMClient([primary, backup], settings=_settings()).generate_structured("", _Out)
    backup.client.generate_structured.assert_not_called()


def test_all_rate_limited_raises_rate_limit_error():
    client = FallbackLLMClient(
        [_entry("openrouter", side_effect=LLMRateLimitError("a")), _entry("gemini", side_effect=LLMRateLimitError("b"))],
        settings=_settings(),
    )
    with pytest.raises(LLMRateLimitError, match="openrouter:openrouter-model.*gemini:gemini-model"):
        client.generate_structured("p", _Out)


def test_mixed_failures_raise_all_providers_failed():
    client = FallbackLLMClient(
        [_entry("openrouter", side_effect=LLMRateLimitError("a")), _entry("gemini", side_effect=LLMAPIError("b", 500))],
        settings=_settings(),
    )
    with pytest.raises(AllProvidersFailedError) as info:
        client.generate_structured("p", _Out)
    assert len(info.value.errors) == 2


def test_rate_limit_plus_missing_key_is_still_rate_limit():
    client = FallbackLLMClient(
        [_entry("openrouter", side_effect=LLMRateLimitError("a")), _entry("gemini", side_effect=LLMConfigError("no key"))],
        settings=_settings(),
    )
    with pytest.raises(LLMRateLimitError):
        client.generate_structured("p", _Out)


def test_empty_chain_raises_config_error_on_call():
    client = FallbackLLMClient([], settings=_settings())
    with pytest.raises(LLMConfigError):
        client.generate_structured("p", _Out)


def test_per_provider_retries_come_from_settings():
    primary = _entry("openrouter", return_value=_Out(answer="a", score=1))
    FallbackLLMClient([primary], settings=_settings(llm_retries_per_provider=2)).generate_structured("p", _Out)
    assert primary.client.generate_structured.call_args.kwargs["max_retries"] == 2


# ---------------------------------------------------------------------------
# build_providers
# ---------------------------------------------------------------------------

def test_default_order_is_openrouter_models_then_gemini_models():
    settings = _settings(
        gemini_api_key="g", gemini_model="gemini-2.5-flash",
        gemini_fallback_models=["gemini-3.5-flash-lite", "gemini-2.5-flash"],  # duplicate of primary dropped
        openrouter_api_key="or", openrouter_model="google/gemma-4-31b-it:free",
        openrouter_fallback_models=["nvidia/nemotron-3.5-super-vl:free"],
    )
    providers = build_providers(settings)
    assert [p.label for p in providers] == [
        "openrouter:google/gemma-4-31b-it:free",
        "openrouter:nvidia/nemotron-3.5-super-vl:free",
        "gemini:gemini-2.5-flash",
        "gemini:gemini-3.5-flash-lite",
    ]
    assert isinstance(providers[0].client, OpenAICompatibleClient)
    assert providers[0].client is providers[1].client  # one HTTP client shared across OpenRouter models


def test_build_providers_skips_providers_without_key():
    settings = _settings(openrouter_api_key="your_openrouter_key_here", gemini_api_key="g", gemini_model="gemini-2.5-flash")
    assert [p.label for p in build_providers(settings)] == ["gemini:gemini-2.5-flash"]


def test_unknown_provider_in_order_is_ignored():
    settings = _settings(gemini_api_key="g", gemini_model="gemini-2.5-flash", llm_provider_order=["ollama", "gemini"])
    assert [p.label for p in build_providers(settings)] == ["gemini:gemini-2.5-flash"]


# ---------------------------------------------------------------------------
# GeminiClient retry policy
# ---------------------------------------------------------------------------

def test_gemini_daily_quota_is_not_retried():
    exc = Exception("429 RESOURCE_EXHAUSTED. Generate content requests per day limit exceeded on Free Tier.")
    exc.code = 429
    genai_client = MagicMock()
    genai_client.models.generate_content.side_effect = exc
    client = GeminiClient(api_key="k", client=genai_client, settings=_settings(max_retries=3))

    with pytest.raises(LLMRateLimitError):
        client.generate_text("hello")
    assert genai_client.models.generate_content.call_count == 1


# ---------------------------------------------------------------------------
# OpenAICompatibleClient (OpenRouter)
# ---------------------------------------------------------------------------

def _oa_client(handler, **kw) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        "openrouter", "secret", "https://openrouter.test/api/v1", "meta-llama/llama-3.3-70b-instruct:free",
        settings=_settings(), http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kw,
    )


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_openai_structured_success_sends_schema_and_json_mode():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _completion('```json\n{"answer": "x", "score": 3}\n```')

    out = _oa_client(handler).generate_structured("Q?", _Out, system_instruction="Be strict.")

    assert out == _Out(answer="x", score=3)
    assert seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer secret"
    body = seen["body"]
    assert body["model"] == "meta-llama/llama-3.3-70b-instruct:free"
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system"
    assert "Be strict." in body["messages"][0]["content"] and '"score"' in body["messages"][0]["content"]


def test_openai_retries_without_json_mode_when_rejected():
    calls: List[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format is not supported"}})
        return _completion('Sure! {"answer": "y", "score": 1}')

    assert _oa_client(handler).generate_structured("Q?", _Out).answer == "y"
    assert len(calls) == 2


@pytest.mark.parametrize("status,exc_type", [(429, LLMRateLimitError), (500, LLMAPIError), (401, LLMAPIError)])
def test_openai_http_errors_map_to_llm_errors(status, exc_type):
    client = _oa_client(lambda r: httpx.Response(status, text="nope"))
    with pytest.raises(exc_type):
        client.generate_structured("Q?", _Out, max_retries=0)


def test_openai_invalid_json_raises_validation_error():
    client = _oa_client(lambda r: _completion('{"answer": "missing score"}'))
    with pytest.raises(LLMResponseValidationError):
        client.generate_structured("Q?", _Out)


def test_openai_missing_key_is_config_error():
    client = OpenAICompatibleClient("openrouter", None, "https://x", "m", settings=_settings())
    with pytest.raises(LLMConfigError):
        client.generate_text("hi")


def test_openai_timeout_maps_to_timeout_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMTimeoutError):
        _oa_client(handler).generate_text("hi", max_retries=0)


# ---------------------------------------------------------------------------
# AssignmentGenerator robustness
# ---------------------------------------------------------------------------

def _mcq(text: str, correct_flags: List[bool]) -> _GeneratedQuestion:
    return _GeneratedQuestion(
        question_text=text, question_type=QuestionType.MCQ, marks=1, difficulty=DifficultyLevel.EASY,
        mcq_options=[MCQOption(id=chr(65 + i), text=f"opt {i}", is_correct=c) for i, c in enumerate(correct_flags)],
    )


def _subjective(text: str) -> _GeneratedQuestion:
    return _GeneratedQuestion(
        question_text=text, question_type=QuestionType.SUBJECTIVE, marks=1, difficulty=DifficultyLevel.MEDIUM,
        model_answer_text="Answer.", key_points=["Point one", "Point two"],
    )


def test_malformed_mcq_is_dropped_not_fatal():
    client = MagicMock()
    client.generate_structured.return_value = _GeneratedAssignmentResponse(
        title="T", instructions="I",
        questions=[
            _mcq("Which planet is closest to the Sun?", [True, False, False, False]),
            _mcq("Which gas do plants absorb mostly?", [True, True, False, False]),  # 2 correct -> dropped
            _mcq("What is the boiling point of water?", [False, False, False, False]),  # 0 correct -> dropped
        ],
    )
    request = AssignmentGenerationRequest(course_id="c", topic="Science", question_count=3,
                                          question_type=QuestionType.MCQ, total_marks=9)
    draft = AssignmentGenerator(gemini_client=client, rubric_generator=MagicMock()).generate_assignment(request)

    assert len(draft.questions) == 1
    assert draft.questions[0].marks == 9


def test_no_usable_questions_raises_validation_error():
    client = MagicMock()
    client.generate_structured.return_value = _GeneratedAssignmentResponse(
        title="T", instructions="I", questions=[_mcq("Which of these is correct here?", [False, False])],
    )
    request = AssignmentGenerationRequest(course_id="c", topic="X", question_count=1,
                                          question_type=QuestionType.MCQ, total_marks=5)
    with pytest.raises(LLMResponseValidationError):
        AssignmentGenerator(gemini_client=client, rubric_generator=MagicMock()).generate_assignment(request)


def test_rubric_failure_falls_back_to_basic_rubric():
    client = MagicMock()
    client.generate_structured.return_value = _GeneratedAssignmentResponse(
        title="T", instructions="I", questions=[_subjective("Explain the process of photosynthesis.")],
    )
    rubric_gen = MagicMock()
    rubric_gen.generate_rubric.side_effect = LLMRateLimitError("all providers exhausted")
    request = AssignmentGenerationRequest(course_id="c", topic="Bio", question_count=1,
                                          question_type=QuestionType.SUBJECTIVE, total_marks=10)

    draft = AssignmentGenerator(gemini_client=client, rubric_generator=rubric_gen).generate_assignment(request)

    rubric = draft.questions[0].rubric
    assert rubric is not None and rubric.total_marks == 10
    assert [c.expected_concepts for c in rubric.criteria] == [["Point one"], ["Point two"]]
    assert sum(c.max_marks for c in rubric.criteria) == pytest.approx(10)


def test_mark_reconciliation_with_subjective_last_question_does_not_crash():
    """20 marks / 7 questions = 2.86 each -> rounding remainder lands on a subjective question with a rubric."""
    client = MagicMock()
    client.generate_structured.return_value = _GeneratedAssignmentResponse(
        title="T", instructions="I",
        questions=[_subjective(f"Explain concept number {i} in detail.") for i in range(7)],
    )
    request = AssignmentGenerationRequest(course_id="c", topic="Bio", question_count=7,
                                          question_type=QuestionType.SUBJECTIVE, total_marks=20)
    rubric_gen = MagicMock()
    rubric_gen.generate_rubric.side_effect = lambda **kw: Rubric(
        total_marks=kw["max_marks"],
        criteria=[RubricCriterion(criterion_id="c1", description="d", max_marks=kw["max_marks"])],
    )

    draft = AssignmentGenerator(gemini_client=client, rubric_generator=rubric_gen).generate_assignment(request)

    assert sum(q.marks for q in draft.questions) == pytest.approx(20)
    last = draft.questions[-1]
    assert last.rubric.total_marks == pytest.approx(last.marks)


def test_low_mark_rubric_reconciliation_stays_valid():
    criteria = [RubricCriterion(criterion_id=f"c{i}", description="d", max_marks=2) for i in range(3)]
    reconciled = RubricGenerator._reconcile_marks(criteria, 0.67)
    Rubric(criteria=reconciled, total_marks=0.67)  # must not raise


def test_rate_limited_provider_is_tried_last_during_cooldown():
    primary = _entry("openrouter", side_effect=LLMRateLimitError("Quota exceeded: requests per day"))
    backup = _entry("gemini", return_value=_Out(answer="b", score=1))
    client = FallbackLLMClient([primary, backup], settings=_settings())

    client.generate_structured("p1", _Out)
    client.generate_structured("p2", _Out)

    # Second call goes straight to the backup; the exhausted primary isn't hit again.
    assert primary.client.generate_structured.call_count == 1
    assert backup.client.generate_structured.call_count == 2


def test_cooling_provider_is_still_tried_as_last_resort():
    primary = _entry("openrouter", side_effect=[LLMRateLimitError("rpm"), _Out(answer="recovered", score=1)])
    backup = _entry("gemini", side_effect=LLMAPIError("down", 503))
    client = FallbackLLMClient([primary, backup], settings=_settings())

    with pytest.raises(AllProvidersFailedError):
        client.generate_structured("p1", _Out)
    assert client.generate_structured("p2", _Out).answer == "recovered"


def test_marks_total_exactly_matches_request():
    client = MagicMock()
    client.generate_structured.return_value = _GeneratedAssignmentResponse(
        title="T", instructions="I",
        questions=[_mcq(f"Which option is right for item {i}?", [True, False]) for i in range(3)],
    )
    request = AssignmentGenerationRequest(course_id="c", topic="X", question_count=3,
                                          question_type=QuestionType.MCQ, total_marks=10)
    draft = AssignmentGenerator(gemini_client=client, rubric_generator=MagicMock()).generate_assignment(request)
    assert round(sum(q.marks for q in draft.questions), 2) == 10


def test_unreachable_provider_is_put_on_cooldown():
    openrouter = _entry("openrouter", side_effect=LLMConnectionError("connection refused"))
    gemini = _entry("gemini", return_value=_Out(answer="g", score=1))
    client = FallbackLLMClient([openrouter, gemini], settings=_settings())

    client.generate_structured("p1", _Out)
    client.generate_structured("p2", _Out)

    assert openrouter.client.generate_structured.call_count == 1
    assert gemini.client.generate_structured.call_count == 2


def test_rubrics_are_generated_concurrently():
    import threading
    import time as _time

    client = MagicMock()
    client.generate_structured.return_value = _GeneratedAssignmentResponse(
        title="T", instructions="I",
        questions=[_subjective(f"Explain concept number {i} in detail.") for i in range(3)],
    )
    threads = set()

    def slow_rubric(**kw):
        threads.add(threading.get_ident())
        _time.sleep(0.4)
        return Rubric(total_marks=kw["max_marks"],
                      criteria=[RubricCriterion(criterion_id="c1", description="d", max_marks=kw["max_marks"])])

    rubric_gen = MagicMock()
    rubric_gen.generate_rubric.side_effect = slow_rubric
    request = AssignmentGenerationRequest(course_id="c", topic="Bio", question_count=3,
                                          question_type=QuestionType.SUBJECTIVE, total_marks=9)

    started = _time.monotonic()
    draft = AssignmentGenerator(gemini_client=client, rubric_generator=rubric_gen).generate_assignment(request)
    elapsed = _time.monotonic() - started

    assert elapsed < 1.0  # sequential would take >= 1.2s
    assert len(threads) == 3
    # Order is preserved: each question keeps its own rubric.
    assert [q.rubric.total_marks for q in draft.questions] == [q.marks for q in draft.questions]


# ---------------------------------------------------------------------------
# OpenRouter reasoning control (speed)
# ---------------------------------------------------------------------------

def test_openrouter_reasoning_off_by_default_is_sent():
    providers = build_providers(_settings(openrouter_api_key="k", openrouter_model="m", openrouter_reasoning="off"))
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return _completion('{"answer": "x", "score": 1}')

    client = providers[0].client
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    client.generate_structured("Q?", _Out, model="m")
    assert seen["body"]["reasoning"] == {"enabled": False}


@pytest.mark.parametrize(("mode", "expected"), [("low", {"effort": "low"}), ("default", None), ("bogus", None)])
def test_openrouter_reasoning_modes(mode, expected):
    client = build_providers(_settings(openrouter_api_key="k", openrouter_model="m", openrouter_reasoning=mode))[0].client
    payload = client._build_payload("m", [], 0.2, None)
    assert payload.get("reasoning") == expected


def test_model_that_rejects_reasoning_field_is_retried_without_it():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "reasoning" in body:
            return httpx.Response(400, json={"error": {"message": "Reasoning is mandatory for this endpoint"}})
        return _completion('{"answer": "ok", "score": 1}')

    client = OpenAICompatibleClient(
        "openrouter", "k", "https://or.test/api/v1", "m", settings=_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        extra_body={"reasoning": {"enabled": False}},
    )
    assert client.generate_structured("Q?", _Out).answer == "ok"
    assert client.generate_structured("Q?", _Out).answer == "ok"
    # One rejected attempt, then the model is remembered and sent plain.
    assert ["reasoning" in b for b in bodies] == [True, False, False]


def test_unrelated_400_is_not_retried_without_reasoning():
    client = OpenAICompatibleClient(
        "openrouter", "k", "https://or.test/api/v1", "m", settings=_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"error": {"message": "context length exceeded"}}))),
        extra_body={"reasoning": {"enabled": False}},
    )
    with pytest.raises(LLMAPIError):
        client.generate_text("hi", max_retries=0)
