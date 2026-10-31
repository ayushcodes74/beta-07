"""Web lookup for untaught answer methods (TinyFish Search API).

When the AI answer check finds that a student solved a question with a valid method the course did not
teach, the teacher is shown a few web sources describing that method, so they can confirm it is a
recognised technique before deciding on bonus marks.

Privacy: only the question text and the method's name are sent. The student's answer, name and any
other personal data never leave the backend. Results are review evidence for the teacher, not proof
that the student's answer is correct (the AI's step-by-step check covers that).

API: GET https://api.search.tinyfish.ai?query=... with header X-API-Key (docs.tinyfish.ai/search-api).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings
from app.schemas.grading import MethodSource

logger = logging.getLogger(__name__)

MAX_SOURCES = 3
_QUESTION_CHARS = 160  # enough context to disambiguate the method; keeps the query short


class MethodSearchUnavailable(Exception):
    """The search provider could not be reached or rejected the request."""


class MethodSearchClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        if api_key is None and settings.TINYFISH_API_KEY is not None:
            api_key = settings.TINYFISH_API_KEY.get_secret_value()
        self.api_key = (api_key or "").strip() or None
        self.base_url = base_url or settings.TINYFISH_SEARCH_URL
        self.timeout = timeout or settings.TINYFISH_TIMEOUT_SECONDS
        self._transport = transport

    @property
    def configured(self) -> bool:
        return self.api_key is not None

    async def find_sources(self, method_name: str, question_text: str) -> list[MethodSource]:
        """Web pages describing ``method_name`` in the context of the question (may be empty).

        Raises MethodSearchUnavailable on network/provider errors so the caller can tell
        "nothing found" apart from "could not search".
        """
        if not self.configured:
            raise MethodSearchUnavailable("TinyFish API key is not configured")
        question = " ".join(question_text.split())[:_QUESTION_CHARS]
        params = {
            "query": f"{method_name.strip()} {question}".strip(),
            "purpose": (
                f"Check whether '{method_name.strip()}' is a recognised, valid method for answering this "
                "academic question, using explanations from textbooks, universities or reference sites."
            ),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
                response = await client.get(self.base_url, params=params, headers={"X-API-Key": self.api_key})
        except httpx.HTTPError as exc:
            logger.warning("TinyFish search failed: %s", type(exc).__name__)
            raise MethodSearchUnavailable("TinyFish search could not be reached") from exc
        if response.status_code != 200:
            logger.warning("TinyFish search returned HTTP %s", response.status_code)
            raise MethodSearchUnavailable(f"TinyFish search returned HTTP {response.status_code}")
        try:
            results = response.json().get("results") or []
        except (ValueError, AttributeError) as exc:
            raise MethodSearchUnavailable("TinyFish search returned an unexpected payload") from exc

        sources: list[MethodSource] = []
        seen: set[str] = set()
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if not url.startswith(("https://", "http://")) or not title or url in seen:
                continue
            seen.add(url)
            sources.append(
                MethodSource(
                    title=title[:300],
                    url=url[:1000],
                    snippet=str(item.get("snippet") or "").strip()[:500],
                    site_name=(str(item["site_name"])[:120] if item.get("site_name") else None),
                )
            )
            if len(sources) >= MAX_SOURCES:
                break
        return sources
