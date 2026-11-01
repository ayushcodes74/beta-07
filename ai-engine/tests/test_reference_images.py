"""Pictures attached to a question are shown to the (multimodal) grader, not only their OCR text."""

import base64
import json
from unittest.mock import MagicMock

import httpx

from app.grading.evaluator import AnswerEvaluator
from app.llm.gemini_client import GeminiClient
from app.llm.openai_compatible_client import OpenAICompatibleClient
from app.schemas.grading import GradingRequest, ReferenceImage
from app.server import GradeSubmissionRequest, _to_grading_request

PNG = b"\x89PNG\r\n\x1a\nfake-graph"
GRADE = {
    "awarded_marks": 4.0,
    "criterion_evaluations": [
        {"criterion_id": "holistic_eval", "awarded_marks": 4.0, "max_marks": 5.0, "explanation": "Parabola named.",
         "matched_concepts": ["parabola"], "missing_concepts": [], "confidence": 0.9}
    ],
    "overall_explanation": "Correct shape.",
    "confidence": 0.9,
}


def _gemini():
    sdk = MagicMock()
    response = MagicMock(parsed=None, text=json.dumps(GRADE))
    sdk.models.generate_content.return_value = response
    return GeminiClient(api_key="test-key", client=sdk), sdk


def _request(images=()):
    return GradingRequest(
        course_id="c", assignment_id="a", submission_id="s", question_id="q1",
        question_text="Describe the graph in the figure.", question_max_marks=5.0,
        student_answer="It is a parabola opening upwards.", expected_answer="Parabola y = x^2",
        reference_images=[ReferenceImage(mime_type="image/png", data_base64=base64.b64encode(PNG).decode()) for _ in images],
    )


def test_gemini_receives_the_picture_as_an_inline_part():
    client, sdk = _gemini()
    AnswerEvaluator(gemini_client=client).evaluate_question(_request(images=[1]), retrieved_evidence=["x"])

    contents = sdk.models.generate_content.call_args.kwargs["contents"]
    assert isinstance(contents, list) and len(contents) == 2
    assert "QUESTION FIGURES" in contents[0] and "NOT an answer key" in contents[0]
    part = contents[1]
    assert part.inline_data.mime_type == "image/png" and part.inline_data.data == PNG


def test_without_pictures_the_prompt_is_sent_as_plain_text():
    client, sdk = _gemini()
    AnswerEvaluator(gemini_client=client).evaluate_question(_request(), retrieved_evidence=["x"])

    contents = sdk.models.generate_content.call_args.kwargs["contents"]
    assert isinstance(contents, str) and "QUESTION FIGURES" not in contents


def test_openai_compatible_providers_get_image_url_parts():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GRADE)}}]})

    client = OpenAICompatibleClient(
        provider="openrouter", api_key="k", base_url="https://router.invalid/api/v1", default_model="vision-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    from app.grading.evaluator import _LLMQuestionGradeResponse

    client.generate_structured("Grade this.", _LLMQuestionGradeResponse, images=[("image/png", PNG)], max_retries=0)

    user = seen["body"]["messages"][-1]
    assert user["role"] == "user" and user["content"][0] == {"type": "text", "text": "Grade this."}
    assert user["content"][1]["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(PNG).decode()


def test_endpoint_request_carries_question_pictures_to_the_grader():
    body = GradeSubmissionRequest.model_validate({
        "submission_id": "s", "assignment_id": "a", "student_text": "1. parabola",
        "questions": [{"question_id": "q1", "type": "subjective", "text": "Describe the graph.", "marks": 5,
                       "expected_answer": "parabola",
                       "reference_images": [{"mime_type": "image/png", "data_base64": base64.b64encode(PNG).decode()}]}],
    })
    request = _to_grading_request(body, body.questions[0], 1, None)
    assert [image.mime_type for image in request.reference_images] == ["image/png"]
