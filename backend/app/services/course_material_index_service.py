"""Course-material RAG ingestion: extract pages, OCR scans, and index them in the AI Engine.

The backend authorizes the teacher (course owner) and extracts text; the AI Engine (internal,
unauthenticated, localhost-only) chunks, embeds and persists it per course for grading evidence.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.ai_generation_service import AIGenerationError, AIServiceUnavailableError, AITimeoutError
from app.services.course_material_service import (
    MaterialExtractionError,
    extract_course_material_pages,
)
from app.services.ocr_client import OCRServiceClient

logger = logging.getLogger(__name__)


class MaterialNotFoundError(Exception):
    """The material does not exist in this course's index."""


class CourseMaterialIndexService:
    def __init__(
        self,
        ocr_client: Optional[OCRServiceClient] = None,
        *,
        ai_base_url: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.ocr_client = ocr_client
        self.base_url = (ai_base_url or settings.AI_SERVICE_URL).rstrip("/")
        self._transport = transport
        # Embedding a large document on CPU can take a while.
        self._timeout = httpx.Timeout(settings.AI_READ_TIMEOUT_SECONDS, connect=settings.AI_CONNECT_TIMEOUT_SECONDS)

    async def upload(self, course_id: str, filename: str, data: bytes) -> dict[str, Any]:
        """Extract (PDF/DOCX/PPTX/TXT; scanned PDFs via OCR) and index one file for a course."""
        extracted = await run_in_threadpool(extract_course_material_pages, filename, data)
        pages = extracted.pages
        source = "text_layer"
        if extracted.needs_ocr:
            pages = await self._ocr_pages(data, extracted.filename)
            source = "ocr"
            if not pages:
                raise MaterialExtractionError("no_text", "No readable text was found in this PDF, even with OCR.")

        result = await self._request(
            "POST",
            "/v1/materials/index",
            json={"course_id": course_id, "filename": extracted.filename, "pages": pages},
        )
        return {**result, "pages_indexed": len(pages), "page_count": extracted.page_count, "extraction": source}

    async def list(self, course_id: str) -> dict[str, Any]:
        return await self._request("GET", "/v1/materials", params={"course_id": course_id})

    async def delete(self, course_id: str, material_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/v1/materials/{material_id}", params={"course_id": course_id})

    # ------------------------------------------------------------------ helpers

    async def _ocr_pages(self, data: bytes, filename: str) -> list[dict]:
        if self.ocr_client is None:
            raise MaterialExtractionError(
                "no_text", "This PDF has no selectable text and OCR is not available. Upload a text-based file."
            )
        job = await self.ocr_client.submit_pdf(data, filename=filename)
        document = await self.ocr_client.poll_until_complete(job.job_id)
        return [
            {"page_number": p.page_number, "text": p.full_text}
            for p in sorted(document.pages, key=lambda p: p.page_number)
            if p.full_text and len(p.full_text.strip()) >= 20
        ]

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.request(method, path, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise AIServiceUnavailableError("AI Engine is unreachable") from exc
        except httpx.TimeoutException as exc:
            raise AITimeoutError("AI Engine timed out while indexing") from exc
        except httpx.HTTPError as exc:
            raise AIServiceUnavailableError("AI Engine request failed") from exc

        if response.status_code == 404:
            raise MaterialNotFoundError("Material not found for this course")
        if response.status_code == 503:
            raise AIServiceUnavailableError("Semantic embeddings are unavailable in the AI Engine")
        if response.status_code == 422:
            raise MaterialExtractionError("no_text", "The file has no text that can be indexed.")
        if response.status_code != 200:
            raise AIGenerationError(f"AI Engine returned status {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise AIGenerationError("AI Engine returned invalid JSON") from exc
        if not isinstance(body, dict):
            raise AIGenerationError("AI Engine returned an unexpected payload")
        return body
