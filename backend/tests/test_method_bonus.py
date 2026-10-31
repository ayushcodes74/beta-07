"""Untaught-but-valid methods: web sources for the teacher, suggested and teacher-applied bonus marks."""

import asyncio
import copy

import httpx
import pytest

from app.schemas.grading import MethodSource, QuestionBonusIn
from app.services.method_search import MethodSearchClient, MethodSearchUnavailable
from app.services.submission_service import SubmissionValidationError
from test_grading_service import AI_RESULT, TEACHER, StatefulGradingRepo, _publish_service, run

ALT_METHOD = {
    "approach": "alternative_valid",
    "method_name": "Repeated subtraction of powers of two",
    "taught_method": "Repeated division by 2",
    "explanation": "Subtracting 32, 16, 4, 1 gives the same bits; the fraction part is doubled correctly.",
}


def _ai_result(method=ALT_METHOD):
    body = copy.deepcopy(AI_RESULT)
    body["question_results"][0]["method_assessment"] = method  # q1: 4/4 marks
    return body


class FakeSearch:
    def __init__(self, sources=None, error=None, configured=True):
        self.sources = sources if sources is not None else [
            MethodSource(title="Decimal to binary by subtraction", url="https://example.edu/binary", snippet="...")
        ]
        self.error = error
        self.configured = configured
        self.calls = []

    async def find_sources(self, method_name, question_text):
        self.calls.append((method_name, question_text))
        if self.error:
            raise self.error
        return self.sources


def _service_with(method=ALT_METHOD, search=None):
    repo = StatefulGradingRepo()
    service, submission, assignment = _publish_service(repo)
    service.method_search = search or FakeSearch()

    def handler(request):
        return httpx.Response(200, json=_ai_result(method))

    service._transport = httpx.MockTransport(handler)
    return service, submission, repo


# --------------------------------------------------------------------------- AI check


def test_valid_untaught_method_gets_sources_and_suggested_bonus():
    search = FakeSearch()
    service, submission, _ = _service_with(search=search)
    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))

    q1 = result.questions[0]
    assert q1.awarded_marks == 4.0  # marks unchanged: graded on correctness
    alt = q1.alternative_method
    assert alt.approach == "alternative_valid"
    assert alt.method_name == ALT_METHOD["method_name"] and alt.taught_method == "Repeated division by 2"
    assert alt.search_status == "found" and alt.sources[0].url == "https://example.edu/binary"
    assert alt.suggested_bonus == 1.0  # 20% of 4 marks, rounded to the half mark
    assert alt.max_bonus == 2.0  # 50% cap
    assert result.questions[1].alternative_method is None
    # Privacy: only the method name and the question text are searched, never the student's answer
    assert search.calls == [(ALT_METHOD["method_name"], "Convert 53.625 to binary.")]


def test_low_scoring_valid_method_has_no_suggested_bonus():
    body_method = dict(ALT_METHOD)
    service, submission, _ = _service_with(method=body_method)
    original = _ai_result(body_method)
    original["question_results"][0]["awarded_marks"] = 2
    original["question_results"][0]["criterion_evaluations"][0]["awarded_marks"] = 2
    service._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=original))
    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    assert result.questions[0].alternative_method.suggested_bonus == 0.0


@pytest.mark.parametrize(
    "search, status",
    [
        (FakeSearch(sources=[]), "no_results"),
        (FakeSearch(error=MethodSearchUnavailable("down")), "unavailable"),
        (FakeSearch(configured=False), "not_configured"),
    ],
)
def test_search_problems_never_block_the_check(search, status):
    service, submission, _ = _service_with(search=search)
    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    alt = result.questions[0].alternative_method
    assert alt.search_status == status and alt.sources == []
    assert alt.suggested_bonus == 1.0  # the AI's step check still stands


def test_invalid_alternative_is_shown_but_not_searched_or_rewarded():
    search = FakeSearch()
    method = dict(ALT_METHOD, approach="alternative_invalid")
    service, submission, _ = _service_with(method=method, search=search)
    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    alt = result.questions[0].alternative_method
    assert alt.approach == "alternative_invalid" and alt.suggested_bonus == 0.0
    assert alt.search_status == "not_searched" and search.calls == []


def test_taught_method_has_no_card():
    service, submission, _ = _service_with(method={"approach": "taught"})
    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    assert result.questions[0].alternative_method is None


def test_alternative_method_survives_save_and_reload():
    service, submission, repo = _service_with()
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))
    loaded = run(service.get_saved_suggestion(TEACHER, submission.id, access_token="t"))
    assert loaded.questions[0].alternative_method.sources[0].title == "Decimal to binary by subtraction"


# --------------------------------------------------------------------------- publishing with bonuses


def test_bonus_is_added_on_top_and_shown_on_its_question():
    service, submission, repo = _service_with()
    run(service.grade_submission(TEACHER, submission.id, access_token="t"))  # AI: 4/5
    bonus = QuestionBonusIn(question_number=1, marks=1.5, reason="  Used a method beyond the course.  ")

    result = run(service.publish_grade(TEACHER, submission.id, 4.0, "Well done.", access_token="t", bonuses=[bonus]))

    assert result.final_score == 5.5 and result.max_score == 5.0  # may exceed the maximum
    assert result.bonus_marks == 1.5
    q1 = result.questions[0]
    assert q1.awarded_marks == 4.0  # per-question marks stay consistent with the 4/5 base score
    assert q1.bonus_marks == 1.5 and q1.bonus_reason == "Used a method beyond the course."
    assert result.questions[1].bonus_marks is None

    # Re-publishing without bonuses removes them
    again = run(service.publish_grade(TEACHER, submission.id, 4.0, "Well done.", access_token="t"))
    assert again.final_score == 4.0 and again.bonus_marks is None and again.questions[0].bonus_marks is None


def test_bonus_without_ai_check_still_reaches_the_student():
    service, submission, repo = _service_with()
    result = run(service.publish_grade(
        TEACHER, submission.id, 3.0, "", access_token="t", show_solutions=False,
        bonuses=[QuestionBonusIn(question_number=1, marks=1)],
    ))
    assert result.final_score == 4.0
    assert [(q.number, q.bonus_marks, q.awarded_marks) for q in result.questions] == [(1, 1.0, None)]


def test_late_penalty_applies_to_the_total_including_bonus():
    service, submission, repo = _service_with()
    service.submissions.record = submission.model_copy(update={"late_status": "accepted", "late_penalty_percent": 50})
    result = run(service.publish_grade(
        TEACHER, submission.id, 4.0, "", access_token="t", bonuses=[QuestionBonusIn(question_number=1, marks=2)]
    ))
    assert result.score_before_late_penalty == 6.0 and result.final_score == 3.0 and result.bonus_marks == 2.0


@pytest.mark.parametrize(
    "bonuses, code",
    [
        ([QuestionBonusIn(question_number=1, marks=2.5)], "bonus_out_of_range"),  # cap is 50% of 4
        ([QuestionBonusIn(question_number=3, marks=0.5)], "invalid_question"),
        ([QuestionBonusIn(question_number=1, marks=1), QuestionBonusIn(question_number=1, marks=1)], "duplicate_bonus"),
    ],
)
def test_bonus_validation(bonuses, code):
    service, submission, _ = _service_with()
    with pytest.raises(SubmissionValidationError) as err:
        run(service.publish_grade(TEACHER, submission.id, 4.0, "", access_token="t", bonuses=bonuses))
    assert err.value.code == code


def test_base_score_still_cannot_exceed_the_maximum():
    service, submission, _ = _service_with()
    with pytest.raises(SubmissionValidationError) as err:
        run(service.publish_grade(TEACHER, submission.id, 5.5, "", access_token="t"))
    assert err.value.code == "score_out_of_range"


# --------------------------------------------------------------------------- TinyFish client


def test_tinyfish_request_and_parsing():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-API-Key")
        return httpx.Response(200, json={"results": [
            {"title": "Tabular integration", "url": "https://a.edu/di", "snippet": "DI method", "site_name": "a.edu"},
            {"title": "dup", "url": "https://a.edu/di"},
            {"title": "", "url": "https://no-title.example"},
            {"title": "bad scheme", "url": "javascript:alert(1)"},
            {"title": "B", "url": "https://b.org"},
            {"title": "C", "url": "https://c.org"},
            {"title": "D", "url": "https://d.org"},
        ]})

    client = MethodSearchClient("key-123", base_url="https://search.test", transport=httpx.MockTransport(handler))
    sources = asyncio.run(client.find_sources("tabular integration", "Integrate x cos x"))
    assert [s.url for s in sources] == ["https://a.edu/di", "https://b.org", "https://c.org"]  # max 3, deduped, safe
    assert seen["key"] == "key-123"
    assert "query=tabular+integration+Integrate+x+cos+x" in seen["url"]


@pytest.mark.parametrize("response", [httpx.Response(401, json={}), httpx.Response(200, text="not json")])
def test_tinyfish_errors_raise_unavailable(response):
    client = MethodSearchClient("k", base_url="https://s.test", transport=httpx.MockTransport(lambda r: response))
    with pytest.raises(MethodSearchUnavailable):
        asyncio.run(client.find_sources("m", "q"))


def test_tinyfish_without_key_is_not_configured():
    client = MethodSearchClient("", base_url="https://s.test")
    assert client.configured is False
    with pytest.raises(MethodSearchUnavailable):
        asyncio.run(client.find_sources("m", "q"))
