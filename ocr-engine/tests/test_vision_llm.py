"""Vision-LLM page reader: math (LaTeX), tables, diagrams, graphs and multilingual text.

All HTTP calls are mocked; tests never contact the Gemini API.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import numpy as np
import pytest

import app.recognition.recognition_pipeline as pipeline
from app.math_recognition.model_manager import MathModelManager
from app.math_recognition.recognition_pipeline import process_math_page
from app.recognition.config import RecognitionConfig
from app.recognition.model_manager import ModelManager
from app.recognition.ocr_space import OCRSpaceClient
from app.recognition.recognition_pipeline import recognize_page
from app.recognition.vision_llm import (
    RESPONSE_SCHEMA,
    GeminiVisionClient,
    VisionBlock,
    VisionLLMError,
    VisionPageAnalysis,
    parse_page_response,
)

PAGE_W, PAGE_H = 1000, 900

MIXED_PAGE = {
    "languages": ["en", "hi"],
    "blocks": [
        {"type": "text", "content": "Q1. Solve $x^2 - 5x + 6 = 0$", "handwritten": False, "language": "en",
         "box_2d": [50, 50, 100, 600]},
        {"type": "math", "content": "x = \\frac{5 \\pm \\sqrt{1}}{2}", "latex": "x = \\frac{5 \\pm \\sqrt{1}}{2}",
         "handwritten": True, "language": "und", "box_2d": [120, 60, 200, 500]},
        {"type": "table", "content": "", "rows": [["x", "y"], ["1", "2"], ["2", "4"]], "handwritten": True,
         "language": "en", "box_2d": [220, 60, 400, 400]},
        {"type": "graph", "content": "Line graph of y against x; straight line through (0,0) and (2,4).",
         "handwritten": True, "language": "en", "box_2d": [420, 60, 700, 600]},
        {"type": "diagram", "content": "Circuit: battery connected in series with resistor R1 = 4 ohm.",
         "handwritten": True, "language": "en", "box_2d": [420, 620, 700, 950]},
        {"type": "text", "content": "उत्तर: प्रकाश संश्लेषण", "handwritten": True, "language": "hi",
         "uncertain": True, "box_2d": [720, 60, 780, 700]},
    ],
}


def _gemini_body(payload, finish="STOP"):
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]},
             "finishReason": finish}
        ]
    }


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture(autouse=True)
def _reset():
    ModelManager.reset_instance()
    MathModelManager.reset_instance()
    pipeline._vision_disabled_until = 0.0
    pipeline._ocr_space_disabled_until = 0.0
    yield
    ModelManager.reset_instance()
    MathModelManager.reset_instance()
    pipeline._vision_disabled_until = 0.0
    pipeline._ocr_space_disabled_until = 0.0


def _page():
    return np.full((PAGE_H, PAGE_W, 3), 255, dtype=np.uint8)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
def test_client_request_and_typed_blocks(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, body=json)
        return _Resp(payload=_gemini_body(MIXED_PAGE))

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GeminiVisionClient(api_key="g-key", model="gemini-2.5-flash")
    analysis = client.analyze_page(_page())

    assert captured["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert captured["headers"]["x-goog-api-key"] == "g-key"
    gen = captured["body"]["generationConfig"]
    assert gen["responseMimeType"] == "application/json"
    assert gen["responseSchema"] == RESPONSE_SCHEMA
    parts = captured["body"]["contents"][0]["parts"]
    assert parts[0]["inline_data"]["mime_type"] == "image/jpeg"
    assert "Never translate" in parts[1]["text"]

    kinds = [b.kind for b in analysis.blocks]
    assert kinds == ["text", "math", "table", "graph", "diagram", "text"]
    assert analysis.languages == ["en", "hi"]
    assert analysis.model_version == "gemini-vision:gemini-2.5-flash"

    math = analysis.blocks[1]
    assert math.latex == "x = \\frac{5 \\pm \\sqrt{1}}{2}"
    # box_2d [ymin, xmin, ymax, xmax] in 0-1000 -> pixels on the 1000x900 page
    assert math.box == (60, 108, 500, 180)

    table = analysis.blocks[2]
    assert table.rows == [["x", "y"], ["1", "2"], ["2", "4"]]
    assert table.content.splitlines()[0] == "| x | y |"

    hindi = analysis.blocks[5]
    assert hindi.content == "उत्तर: प्रकाश संश्लेषण"  # original script, not translated
    assert hindi.language == "hi" and hindi.uncertain


@pytest.mark.parametrize(
    "resp, match",
    [
        (_Resp(429, None, "RESOURCE_EXHAUSTED"), "HTTP 429"),
        (_Resp(200, _gemini_body(MIXED_PAGE, finish="MAX_TOKENS")), "MAX_TOKENS"),
        (_Resp(200, {"promptFeedback": {"blockReason": "SAFETY"}}), "blocked"),
        (_Resp(200, {"candidates": [{"content": {"parts": [{"text": "{not json"}]}, "finishReason": "STOP"}]}),
         "invalid JSON"),
        (_Resp(200, {"candidates": [{"content": {"parts": [{"text": "[]"}]}, "finishReason": "STOP"}]}),
         "unexpected payload"),
        (_Resp(200, None, "<html>"), "non-JSON"),
    ],
)
def test_client_errors_raise(monkeypatch, resp, match):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: resp)
    with pytest.raises(VisionLLMError, match=match):
        GeminiVisionClient(api_key="k").analyze_page(_page())


def test_client_network_error_raises(monkeypatch):
    def boom(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(VisionLLMError, match="ReadTimeout"):
        GeminiVisionClient(api_key="k").analyze_page(_page())


def test_client_falls_back_to_next_model_on_quota(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(url)
        if "primary" in url:
            return _Resp(429, None, '{"error": {"status": "RESOURCE_EXHAUSTED"}}')
        return _Resp(payload=_gemini_body(MIXED_PAGE))

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GeminiVisionClient(api_key="k", model="primary", fallback_models=["backup"])

    first = client.analyze_page(_page())
    assert first.model_version == "gemini-vision:backup" and len(first.blocks) == 6
    client.analyze_page(_page())  # exhausted primary is skipped while cooling down
    assert ["primary" in u for u in calls] == [True, False, False]


def test_client_does_not_fall_back_on_bad_request(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(url)
        return _Resp(400, None, "API key not valid")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(VisionLLMError, match="HTTP 400"):
        GeminiVisionClient(api_key="k", model="primary", fallback_models=["backup"]).analyze_page(_page())
    assert len(calls) == 1


def test_parse_tolerates_bad_boxes_and_types():
    blocks, langs = parse_page_response(
        {
            "blocks": [
                {"type": "chart", "content": "odd type", "box_2d": [10, 10, 20, 20]},
                {"type": "text", "content": "no box", "box_2d": [5, 5]},
                {"type": "math", "content": "", "latex": "a^2+b^2=c^2", "box_2d": [500, 500, 400, 400]},
                {"type": "text", "content": "the word [illegible] here", "box_2d": [0, 0, 100, 100]},
                {"type": "text", "content": "   ", "box_2d": [0, 0, 100, 100]},
            ]
        },
        PAGE_W,
        PAGE_H,
    )
    assert [b.kind for b in blocks] == ["text", "text", "math", "text"]
    assert blocks[1].box == (0, 0, PAGE_W, PAGE_H) and blocks[1].box_estimated
    assert blocks[2].content == "a^2+b^2=c^2" and blocks[2].box == (400, 360, 500, 450)  # swapped corners
    assert blocks[3].uncertain
    assert langs == []


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------
def _manager(vision_client=None, ocr_space_client=None):
    mgr = ModelManager.get_instance(RecognitionConfig(backend="ocrspace", ocr_space_api_key="k"))
    mgr.vision_client = vision_client
    mgr.vision_status = "loaded" if vision_client else "disabled"
    mgr.ocr_space_client = ocr_space_client
    mgr.ocr_space_status = "loaded" if ocr_space_client else "unavailable"
    mgr._initialized = True
    return mgr


def _vision_client_returning(payload):
    blocks, langs = parse_page_response(payload, PAGE_W, PAGE_H)
    client = MagicMock(spec=GeminiVisionClient)
    client.analyze_page.return_value = VisionPageAnalysis(
        blocks=blocks, languages=langs, model_version="gemini-vision:test"
    )
    return client


def _write_page(tmp_path: Path) -> Path:
    import cv2

    path = tmp_path / "page.png"
    img = _page()
    # Real ink inside the math block's box (x 60-500, y 108-180) so its quality check sees legible strokes
    cv2.putText(img, "x = (5 +- 1) / 2", (80, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 2)
    cv2.imwrite(str(path), img)
    return path


def test_pipeline_uses_vision_reader_first(tmp_path: Path):
    ocr_space = MagicMock(spec=OCRSpaceClient)
    _manager(vision_client=_vision_client_returning(MIXED_PAGE), ocr_space_client=ocr_space)

    result = recognize_page(str(_write_page(tmp_path)), "sub-vision", 1)

    ocr_space.recognize_lines.assert_not_called()
    assert result.status == "completed"
    assert result.metadata["engine_used"] == ["gemini-vision"]
    assert result.metadata["languages"] == ["en", "hi"]
    assert result.metadata["content_types"] == {"text": 2, "math": 1, "table": 1, "diagram": 1, "graph": 1}

    by_type = {b.metadata["content_type"]: b for b in result.text_blocks}
    assert by_type["math"].text == "$$x = \\frac{5 \\pm \\sqrt{1}}{2}$$"
    assert by_type["math"].metadata["latex"] == "x = \\frac{5 \\pm \\sqrt{1}}{2}"
    assert by_type["table"].metadata["table_rows"][1] == ["1", "2"]
    assert by_type["table"].text.count("\n") == 3  # header, separator, two rows
    assert by_type["graph"].text.startswith("[Graph] Line graph")
    assert by_type["diagram"].text.startswith("[Diagram] Circuit")
    assert result.text_blocks[0].type == "printed" and result.text_blocks[1].type == "handwritten"

    # Everything reaches full_text, which is what the grader reads
    for fragment in ("$x^2 - 5x + 6 = 0$", "\\frac{5", "| 2 | 4 |", "[Graph]", "[Diagram]", "प्रकाश संश्लेषण"):
        assert fragment in result.full_text

    hindi = result.text_blocks[-1]
    assert hindi.metadata["language"] == "hi"
    assert any("uncertain" in w for w in hindi.warnings)
    assert any("1 of 6 regions" in w for w in result.warnings)


def test_pipeline_falls_back_to_ocr_space_when_vision_fails(tmp_path: Path):
    vision = MagicMock(spec=GeminiVisionClient)
    vision.analyze_page.side_effect = VisionLLMError("Vision request failed: ReadTimeout")
    ocr_space = MagicMock(spec=OCRSpaceClient)
    ocr_space.model_version = "ocr.space-engine3"
    ocr_space.recognize_lines.return_value = [{"text": "x = 2", "score": None, "box": (50, 50, 300, 80)}]
    _manager(vision_client=vision, ocr_space_client=ocr_space)

    page = str(_write_page(tmp_path))
    result = recognize_page(page, "sub-fb", 1)

    assert result.full_text == "x = 2"
    assert result.metadata["engine_used"] == ["ocrspace"]
    assert "ReadTimeout" in result.metadata["vision_error"]
    assert any("Vision reader unavailable" in w for w in result.warnings)
    # Transient error: the next page tries the vision reader again
    recognize_page(page, "sub-fb", 2)
    assert vision.analyze_page.call_count == 2


def test_quota_error_pauses_vision_reader(tmp_path: Path):
    vision = MagicMock(spec=GeminiVisionClient)
    vision.analyze_page.side_effect = VisionLLMError("Vision HTTP 429: RESOURCE_EXHAUSTED")
    ocr_space = MagicMock(spec=OCRSpaceClient)
    ocr_space.model_version = "ocr.space-engine3"
    ocr_space.recognize_lines.return_value = [{"text": "hello", "score": None, "box": (50, 50, 300, 80)}]
    _manager(vision_client=vision, ocr_space_client=ocr_space)

    page = str(_write_page(tmp_path))
    recognize_page(page, "sub-q", 1)
    recognize_page(page, "sub-q", 2)
    assert vision.analyze_page.call_count == 1


def test_vision_disabled_without_key():
    mgr = ModelManager(RecognitionConfig(backend="degraded", vision_api_key=""))
    mgr.initialize_models()
    assert mgr.vision_status == "disabled" and not mgr.uses_vision

    mgr = ModelManager(RecognitionConfig(backend="ocrspace", ocr_space_api_key="", vision_api_key=""))
    mgr._init_vision()
    assert mgr.vision_status == "disabled" and not mgr.uses_vision

    mgr = ModelManager(RecognitionConfig(backend="ocrspace", vision_api_key="g", vision_enabled=False))
    mgr._init_vision()
    assert not mgr.uses_vision

    mgr = ModelManager(RecognitionConfig(backend="ocrspace", vision_api_key="g", vision_model="gemini-x"))
    mgr._init_vision()
    assert mgr.uses_vision and mgr.vision_client.model == "gemini-x"


# ---------------------------------------------------------------------------
# Module 4 consumes the vision reader's LaTeX
# ---------------------------------------------------------------------------
def test_math_stage_keeps_vision_latex_and_skips_prose(tmp_path: Path):
    _manager(vision_client=_vision_client_returning(MIXED_PAGE))
    page = str(_write_page(tmp_path))
    rec = recognize_page(page, "sub-math", 1)

    math_res = process_math_page(page, "sub-math", 1, page_recognition_result=rec)

    # Only the math block is harvested: prose with '-' / ':' and tables/figures are not sent to math OCR
    assert len(math_res.math_regions) == 1
    region = math_res.math_regions[0]
    assert region.region_id == f"math-{rec.text_blocks[1].block_id}"
    assert region.latex == "x = \\frac{5 \\pm \\sqrt{1}}{2}"  # verbatim, not rewritten by the heuristic converter
    assert region.engine_used == "gemini-vision"
    assert region.recognition_status == "completed"
    assert math_res.status == "completed"
    assert math_res.combined_latex == region.latex
    assert any(s.structure_type == "fraction" for s in region.structures)
