"""Client for OpenAI-compatible chat-completion APIs (used for OpenRouter).

Exposes the same ``generate_text`` / ``generate_structured`` interface as GeminiClient so
it can sit in the same fallback chain. Structured output uses JSON mode plus the Pydantic
JSON schema embedded in the system prompt, then validates the reply with Pydantic.

Subclasses can override the small hook methods to talk to other chat APIs.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.llm.gemini_client import (
    LLMAPIError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMConnectionError(LLMAPIError):
    """The provider could not be reached at all (DNS failure, connection refused, network down)."""


class OpenAICompatibleClient:
    """Minimal chat-completions client with retry, JSON mode and schema validation."""

    #: Whether calls without an API key should fail with LLMConfigError.
    requires_api_key: bool = True
    #: HTTP statuses on which a structured call is retried with the next, looser JSON mode.
    json_mode_rejection_status = {400, 422}

    def __init__(
        self,
        provider: str,
        api_key: Optional[str],
        base_url: str,
        default_model: str,
        settings: Optional[Settings] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        http_client: Optional[httpx.Client] = None,
        timeout: Optional[float] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ):
        self.provider = provider
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.settings = settings or get_settings()
        self._extra_headers = extra_headers or {}
        self._http = http_client
        self._timeout = timeout
        # Optional fields added to every request (e.g. OpenRouter's {"reasoning": {"enabled": false}}).
        self._extra_body = dict(extra_body or {})
        # Models that rejected the extra fields; they are sent plain from then on.
        self._extra_body_unsupported: set = set()

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=self._timeout or self.settings.llm_request_timeout)
        return self._http

    # ------------------------------------------------------------------
    # API-specific hooks (overridden by subclasses)
    # ------------------------------------------------------------------

    def _chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _build_payload(
        self, model: str, messages: List[Dict[str, str]], temperature: float, json_mode: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if self._extra_body and model not in self._extra_body_unsupported:
            payload.update(self._extra_body)
        if json_mode:
            payload.update(json_mode)
        return payload

    def _json_modes(self, schema: Dict[str, Any]) -> List[Optional[Dict[str, Any]]]:
        """JSON-mode payload fragments to try in order, strictest first.

        Some models (notably on OpenRouter) reject ``response_format``; the last entry (None)
        falls back to prompt-only JSON instructions.
        """
        return [{"response_format": {"type": "json_object"}}, None]

    def _extract_content(self, data: Dict[str, Any]) -> str:
        return data["choices"][0]["message"]["content"]

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _post_chat(self, payload: Dict[str, Any]) -> str:
        """POST a chat request and return the message content."""
        has_key = bool(self._api_key and self._api_key.strip())
        if self.requires_api_key and not has_key:
            raise LLMConfigError(f"{self.provider}: API key is not configured.")

        headers = {"Content-Type": "application/json", **self._extra_headers}
        if has_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = self.http.post(self._chat_url(), json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"{self.provider} request timed out", status_code=504, raw_error=exc) from exc
        except httpx.HTTPError as exc:
            raise LLMConnectionError(
                f"{self.provider} unreachable at {self.base_url}: {exc}", raw_error=exc
            ) from exc

        if response.status_code == 429:
            raise LLMRateLimitError(
                f"{self.provider} rate limit exceeded: {response.text[:300]}", status_code=429
            )
        if response.status_code >= 400:
            raise LLMAPIError(
                f"{self.provider} returned HTTP {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )

        try:
            content = self._extract_content(response.json())
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMAPIError(f"{self.provider} returned an unexpected response shape", raw_error=exc) from exc
        if not content:
            raise LLMAPIError(f"{self.provider} returned an empty completion")
        return content

    def _post_with_retry(self, payload: Dict[str, Any], max_retries: Optional[int]) -> str:
        retries = max_retries if max_retries is not None else self.settings.max_retries
        delay = 1.0
        for attempt in range(retries + 1):
            try:
                return self._post_chat(payload)
            except (LLMConfigError, LLMConnectionError):
                raise  # retrying won't help; let the fallback chain move on immediately
            except LLMAPIError as exc:
                if self._rejects_extra_body(exc, payload):
                    # e.g. a model whose reasoning can't be switched off: resend without the extras.
                    model = payload.get("model")
                    logger.info("%s: model %s rejected %s; sending without it", self.provider, model,
                                sorted(self._extra_body))
                    self._extra_body_unsupported.add(model)
                    payload = {k: v for k, v in payload.items() if k not in self._extra_body}
                    return self._post_with_retry(payload, max_retries)
                retryable = isinstance(exc, LLMTimeoutError) or exc.status_code in _RETRYABLE_STATUS
                if attempt < retries and retryable:
                    logger.info("%s call failed (%s); retrying in %.1fs", self.provider, exc.status_code, delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise LLMError("Unexpected error: retry loop exited without result.")  # pragma: no cover

    def _rejects_extra_body(self, exc: LLMAPIError, payload: Dict[str, Any]) -> bool:
        """True if a 400/422 error is about one of the optional extra fields we added."""
        if exc.status_code not in (400, 422):
            return False
        sent = [key for key in self._extra_body if key in payload]
        return bool(sent) and any(key in str(exc).lower() for key in sent)

    @staticmethod
    def _messages(prompt: str, system_instruction: Optional[str]) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        return messages

    # ------------------------------------------------------------------
    # Public interface (mirrors GeminiClient)
    # ------------------------------------------------------------------

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> str:
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")
        payload = self._build_payload(
            model or self.default_model,
            self._messages(prompt, system_instruction),
            temperature if temperature is not None else self.settings.temperature,
            None,
        )
        return self._post_with_retry(payload, max_retries)

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> T:
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")
        if not issubclass(response_schema, BaseModel):
            raise TypeError("response_schema must be a subclass of pydantic.BaseModel")

        schema = response_schema.model_json_schema()
        json_instruction = (
            "Respond with a single valid JSON object only (no markdown, no commentary) that "
            f"conforms to this JSON Schema:\n{json.dumps(schema)}"
        )
        system = f"{system_instruction}\n\n{json_instruction}" if system_instruction else json_instruction
        messages = self._messages(prompt, system)
        target_model = model or self.default_model
        temp = temperature if temperature is not None else self.settings.temperature

        modes = self._json_modes(schema)
        raw_text = ""
        for i, mode in enumerate(modes):
            try:
                raw_text = self._post_with_retry(
                    self._build_payload(target_model, messages, temp, mode), max_retries
                )
                break
            except LLMAPIError as exc:
                if i < len(modes) - 1 and exc.status_code in self.json_mode_rejection_status:
                    logger.info("%s rejected JSON mode %s (HTTP %s); trying a looser mode",
                                self.provider, mode, exc.status_code)
                    continue
                raise

        try:
            return response_schema.model_validate(json.loads(self._extract_json(raw_text)))
        except ValidationError as val_err:
            raise LLMResponseValidationError(
                f"{self.provider} output failed schema {response_schema.__name__}: {val_err}",
                raw_response=raw_text,
                validation_error=val_err,
            ) from val_err
        except ValueError as json_err:
            raise LLMResponseValidationError(
                f"{self.provider} output is not valid JSON: {json_err}", raw_response=raw_text
            ) from json_err

    @staticmethod
    def _extract_json(text: str) -> str:
        """Strip markdown fences / surrounding prose and return the outermost JSON object."""
        text = text.strip()
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        if not text.startswith("{"):
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                text = text[start : end + 1]
        return text
