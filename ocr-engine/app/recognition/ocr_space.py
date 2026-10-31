"""OCR.space cloud OCR client (OCREngine 3: handwriting, tables, 200+ languages).

Docs: https://ocr.space/ocrapi
- Free tier: 1 MB per file, 1000 Engine-3 conversions/month, 500 requests/day/IP.
- Each page image is sent separately (re-encoded as JPEG to fit the size limit); word boxes are
  mapped back to the original page's pixel coordinates.
- The API returns no confidence scores, so lines carry ``score=None``.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import cv2
import httpx
import numpy as np

logger = logging.getLogger(__name__)


class OCRSpaceError(Exception):
    """OCR.space request failed or returned an error (network, quota, invalid key, parse error)."""


def _encode_under_limit(image: np.ndarray, max_bytes: int) -> Tuple[bytes, float]:
    """JPEG-encode ``image`` to at most ``max_bytes``, shrinking quality then size.

    Returns:
        (jpeg_bytes, scale) where scale = encoded_width / original_width.
    """
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

    scale = 1.0
    work = image
    for _ in range(8):
        for quality in (90, 80, 70, 60):
            ok, buf = cv2.imencode(".jpg", work, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if ok and len(buf) <= max_bytes:
                return buf.tobytes(), scale
        scale *= 0.8
        h, w = image.shape[:2]
        work = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    raise OCRSpaceError(f"Could not compress page image under {max_bytes} bytes")


class OCRSpaceClient:
    """Minimal synchronous client for the OCR.space ``parse/image`` endpoint."""

    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://api.ocr.space/parse/image",
        engine: int = 3,
        timeout_seconds: float = 120.0,
        max_upload_bytes: int = 1_000_000,
    ) -> None:
        if not api_key:
            raise ValueError("OCR.space API key is required")
        self.api_key = api_key
        self.endpoint = endpoint
        self.engine = engine
        self.timeout_seconds = timeout_seconds
        self.max_upload_bytes = max_upload_bytes

    @property
    def model_version(self) -> str:
        return f"ocr.space-engine{self.engine}"

    def recognize_lines(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """OCR a page image; return ``[{"text", "score": None, "box": (x1, y1, x2, y2)}]`` per line.

        Raises:
            OCRSpaceError: On transport errors, HTTP errors, API errors, or an unusable response.
        """
        if image is None or image.size == 0:
            return []
        page_h, page_w = image.shape[:2]
        payload, scale = _encode_under_limit(image, self.max_upload_bytes)

        try:
            resp = httpx.post(
                self.endpoint,
                headers={"apikey": self.api_key},
                data={
                    "OCREngine": str(self.engine),
                    "isOverlayRequired": "true",
                    "scale": "true",
                    "detectOrientation": "false",
                    "filetype": "JPG",
                },
                files={"file": ("page.jpg", payload, "image/jpeg")},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as e:
            raise OCRSpaceError(f"OCR.space request failed: {type(e).__name__}: {e}") from e

        if resp.status_code != 200:
            # 403 = invalid key / quota; message body is a short string or JSON
            raise OCRSpaceError(f"OCR.space HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            body = resp.json()
        except ValueError as e:
            raise OCRSpaceError(f"OCR.space returned non-JSON: {resp.text[:200]}") from e
        if not isinstance(body, dict):
            raise OCRSpaceError(f"OCR.space returned unexpected payload: {str(body)[:200]}")

        results = body.get("ParsedResults") or []
        if body.get("IsErroredOnProcessing") or not results:
            message = body.get("ErrorMessage") or body.get("ErrorDetails") or "no parsed results"
            if isinstance(message, list):
                message = "; ".join(str(m) for m in message)
            raise OCRSpaceError(f"OCR.space error (exit {body.get('OCRExitCode')}): {message}")

        result = results[0]
        if str(result.get("FileParseExitCode")) != "1":
            raise OCRSpaceError(
                f"OCR.space parse error (exit {result.get('FileParseExitCode')}): {result.get('ErrorMessage')}"
            )

        overlay = result.get("TextOverlay") or {}
        lines: List[Dict[str, Any]] = []
        inv = 1.0 / scale
        for line in overlay.get("Lines") or []:
            words = [w for w in (line.get("Words") or []) if str(w.get("WordText", "")).strip()]
            if not words:
                continue
            x1 = min(float(w["Left"]) for w in words) * inv
            y1 = min(float(w["Top"]) for w in words) * inv
            x2 = max(float(w["Left"]) + float(w["Width"]) for w in words) * inv
            y2 = max(float(w["Top"]) + float(w["Height"]) for w in words) * inv
            box = (
                max(0, min(int(round(x1)), page_w)),
                max(0, min(int(round(y1)), page_h)),
                max(0, min(int(round(x2)), page_w)),
                max(0, min(int(round(y2)), page_h)),
            )
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            text = str(line.get("LineText") or " ".join(str(w["WordText"]) for w in words)).strip()
            lines.append({"text": text, "score": None, "box": box})

        if not lines and (result.get("ParsedText") or "").strip():
            # Overlay missing but text present: keep the text as one full-page block rather than lose it.
            lines.append({"text": result["ParsedText"].strip(), "score": None, "box": (0, 0, page_w, page_h)})

        logger.info(
            "OCR.space engine %s: %d lines in %s ms", self.engine, len(lines), body.get("ProcessingTimeInMilliseconds")
        )
        return lines
