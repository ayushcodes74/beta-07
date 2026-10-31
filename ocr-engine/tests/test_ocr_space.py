"""OCR.space (OCREngine 3) integration: request/response handling, pipeline use, and PaddleOCR fallback.

All HTTP calls are mocked; tests never contact api.ocr.space.
"""

from pathlib import Path
from unittest.mock import MagicMock

import cv2
import httpx
import numpy as np
import pytest

import app.recognition.recognition_pipeline as pipeline
from app.recognition.config import RecognitionConfig
from app.recognition.model_manager import ModelManager
from app.recognition.ocr_space import OCRSpaceClient, OCRSpaceError, _encode_under_limit
from app.recognition.recognition_pipeline import recognize_page


def _ok_response(lines):
    """OCR.space success payload; lines = [(text, [(word, left, top, width, height), ...]), ...]."""
    return {
        "ParsedResults": [
            {
                "TextOverlay": {
                    "Lines": [
                        {
                            "LineText": text,
                            "Words": [
                                {"WordText": w, "Left": l, "Top": t, "Width": wd, "Height": h}
                                for w, l, t, wd, h in words
                            ],
                            "MaxHeight": max(h for *_, h in words),
                            "MinTop": min(t for _, _, t, _, _ in words),
                        }
                        for text, words in lines
                    ],
                    "HasOverlay": True,
                },
                "FileParseExitCode": 1,
                "ParsedText": "\n".join(text for text, _ in lines),
                "ErrorMessage": "",
            }
        ],
        "OCRExitCode": 1,
        "IsErroredOnProcessing": False,
        "ProcessingTimeInMilliseconds": "1234",
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
    pipeline._ocr_space_disabled_until = 0.0
    yield
    ModelManager.reset_instance()
    pipeline._ocr_space_disabled_until = 0.0


def test_client_sends_engine3_request_and_parses_lines(monkeypatch):
    captured = {}

    def fake_post(url, headers, data, files, timeout):
        captured.update(url=url, headers=headers, data=data, files=files)
        return _Resp(payload=_ok_response([
            ("Question 1: convert", [("Question", 10, 20, 80, 18), ("1:", 95, 20, 15, 18), ("convert", 115, 21, 60, 17)]),
            ("53.625", [("53.625", 30, 60, 70, 20)]),
        ]))

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OCRSpaceClient(api_key="k-123", engine=3)
    lines = client.recognize_lines(np.full((200, 300, 3), 255, dtype=np.uint8))

    assert captured["url"] == "https://api.ocr.space/parse/image"
    assert captured["headers"] == {"apikey": "k-123"}
    assert captured["data"]["OCREngine"] == "3"
    assert captured["data"]["isOverlayRequired"] == "true"
    assert captured["files"]["file"][2] == "image/jpeg"
    assert lines == [
        {"text": "Question 1: convert", "score": None, "box": (10, 20, 175, 38)},
        {"text": "53.625", "score": None, "box": (30, 60, 100, 80)},
    ]


def test_boxes_are_scaled_back_when_image_is_shrunk(monkeypatch):
    # Noise compresses badly, forcing a downscale to fit the tiny upload limit.
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (800, 1000, 3), dtype=np.uint8)
    payload, scale = _encode_under_limit(img, 60_000)
    assert len(payload) <= 60_000 and scale < 1.0

    def fake_post(url, headers, data, files, timeout):
        enc = cv2.imdecode(np.frombuffer(files["file"][1], np.uint8), cv2.IMREAD_COLOR)
        w = enc.shape[1]
        # One word covering the full encoded width
        return _Resp(payload=_ok_response([("wide", [("wide", 0, 0, w, 10)])]))

    monkeypatch.setattr(httpx, "post", fake_post)
    lines = OCRSpaceClient(api_key="k", max_upload_bytes=60_000).recognize_lines(img)
    assert abs(lines[0]["box"][2] - 1000) <= 3  # mapped back to original page width


@pytest.mark.parametrize(
    "resp, match",
    [
        (_Resp(403, None, "The API key is invalid"), "HTTP 403"),
        (_Resp(200, {"IsErroredOnProcessing": True, "ErrorMessage": ["Daily limit exceeded"], "OCRExitCode": 99}),
         "Daily limit exceeded"),
        (_Resp(200, {"ParsedResults": [{"FileParseExitCode": -10, "ErrorMessage": "parse fail"}],
                     "IsErroredOnProcessing": False}), "parse error"),
        (_Resp(200, None, "<html>"), "non-JSON"),
    ],
)
def test_client_errors_raise(monkeypatch, resp, match):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: resp)
    with pytest.raises(OCRSpaceError, match=match):
        OCRSpaceClient(api_key="k").recognize_lines(np.full((50, 50, 3), 255, dtype=np.uint8))


def test_client_network_error_raises(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(OCRSpaceError, match="ConnectTimeout"):
        OCRSpaceClient(api_key="k").recognize_lines(np.full((50, 50, 3), 255, dtype=np.uint8))


def _manager_with(client=None, paddle_lines=None):
    mgr = ModelManager.get_instance(RecognitionConfig(backend="ocrspace", ocr_space_api_key="k"))
    mgr.ocr_space_client = client
    mgr.ocr_space_status = "loaded" if client else "unavailable"
    if paddle_lines is not None:
        paddle = MagicMock()
        paddle.predict.return_value = [{
            "rec_texts": [t for t, _, _ in paddle_lines],
            "rec_scores": np.array([s for _, s, _ in paddle_lines]),
            "rec_boxes": np.array([b for _, _, b in paddle_lines]).reshape(-1, 4),
            "rec_polys": [],
        }]
        mgr.printed_engine = paddle
        mgr.printed_engine_status = "loaded"
        mgr.printed_model_version = "PP-OCRv6_small_det+PP-OCRv6_small_rec"
    mgr._initialized = True
    return mgr


def test_pipeline_uses_ocr_space(mixed_assignment_page: Path):
    client = MagicMock(spec=OCRSpaceClient)
    client.model_version = "ocr.space-engine3"
    client.recognize_lines.return_value = [
        {"text": "Question 1: What is the capital of France?", "score": None, "box": (50, 50, 520, 82)},
        {"text": "The capital of France is Paris.", "score": None, "box": (60, 200, 500, 240)},
    ]
    _manager_with(client=client, paddle_lines=[("should not be used", 0.99, (0, 0, 10, 10))])

    result = recognize_page(str(mixed_assignment_page), "sub-ocrspace", 1)

    assert result.status == "completed"
    assert result.full_text == "Question 1: What is the capital of France?\nThe capital of France is Paris."
    assert result.metadata["engine_used"] == ["ocrspace"]
    assert result.metadata["model_version"]["handwriting"] == "ocr.space-engine3"
    for block in result.text_blocks:
        assert block.confidence is None
        assert block.metadata["engine_used"] == "ocrspace"
        assert not any("degraded" in w.lower() for w in block.warnings)


def test_pipeline_falls_back_to_paddle_on_ocr_space_error(mixed_assignment_page: Path):
    client = MagicMock(spec=OCRSpaceClient)
    client.recognize_lines.side_effect = OCRSpaceError("OCR.space request failed: ConnectTimeout")
    _manager_with(client=client, paddle_lines=[("Paddle text", 0.95, (50, 50, 300, 80))])

    result = recognize_page(str(mixed_assignment_page), "sub-fallback", 1)

    assert result.full_text == "Paddle text"
    assert result.metadata["engine_used"] == ["paddleocr"]
    assert "ConnectTimeout" in result.metadata["ocr_space_error"]
    assert any("OCR.space unavailable" in w for w in result.warnings)
    # Transient error: next page tries OCR.space again
    recognize_page(str(mixed_assignment_page), "sub-fallback", 2)
    assert client.recognize_lines.call_count == 2


def test_quota_error_pauses_ocr_space(mixed_assignment_page: Path):
    client = MagicMock(spec=OCRSpaceClient)
    client.recognize_lines.side_effect = OCRSpaceError("OCR.space HTTP 403: daily limit exceeded")
    _manager_with(client=client, paddle_lines=[("Paddle text", 0.95, (50, 50, 300, 80))])

    for page in (1, 2, 3):
        result = recognize_page(str(mixed_assignment_page), "sub-quota", page)
        assert result.full_text == "Paddle text"
    assert client.recognize_lines.call_count == 1  # pages 2-3 skip the API during the cool-down


def test_no_api_key_uses_paddle_without_network(monkeypatch, mixed_assignment_page: Path):
    def no_network(*a, **k):
        raise AssertionError("must not call OCR.space without a key")

    monkeypatch.setattr(httpx, "post", no_network)
    mgr = ModelManager.get_instance(RecognitionConfig(backend="ocrspace", ocr_space_api_key=""))
    mgr._init_ocr_space()
    assert mgr.ocr_space_status == "unavailable"
    assert not mgr.uses_ocr_space
