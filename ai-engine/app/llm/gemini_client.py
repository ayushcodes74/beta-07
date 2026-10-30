"""Reusable Gemini Client powered by the google-genai SDK.

Provides robust text and structured JSON generation, automatic retry logic
with exponential backoff, strict Pydantic validation, and rich error handling.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
except ImportError:  # pragma: no cover
    genai = None  # type: ignore
    types = None  # type: ignore
    APIError = Exception  # type: ignore

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Base exception for all LLM client errors."""


class LLMConfigError(LLMError):
    """Raised when client configuration or credentials are missing/invalid."""


class LLMAPIError(LLMError):
    """Raised when the Gemini API returns an error response."""

    def __init__(self, message: str, status_code: Optional[int] = None, raw_error: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw_error = raw_error


class LLMRateLimitError(LLMAPIError):
    """Raised when rate limits (HTTP 429 / RESOURCE_EXHAUSTED) are exceeded."""


class LLMTimeoutError(LLMAPIError):
    """Raised when an API request times out."""


class LLMResponseValidationError(LLMError):
    """Raised when the LLM output fails Pydantic schema validation."""

    def __init__(self, message: str, raw_response: str, validation_error: Optional[ValidationError] = None):
        super().__init__(message)
        self.raw_response = raw_response
        self.validation_error = validation_error


# ---------------------------------------------------------------------------
# Client Implementation
# ---------------------------------------------------------------------------

class GeminiClient:
    """Thread-safe, reusable Gemini API client with retry and validation logic."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        settings: Optional[Settings] = None,
        client: Optional[Any] = None,
    ):
        """Initialize the Gemini client.

        Args:
            api_key: Optional API key override. If not supplied, uses settings.
            default_model: Optional model name override.
            settings: Optional Settings instance.
            client: Optional pre-configured genai.Client instance (useful for testing/mocks).
        """
        self.settings = settings or get_settings()
        self._api_key = api_key or self.settings.gemini_api_key
        self.default_model = default_model or self.settings.gemini_model
        self._client = client

    @property
    def client(self) -> Any:
        """Lazily initialize and return the underlying genai.Client."""
        if self._client is None:
            if not self._api_key or not self._api_key.strip():
                raise LLMConfigError(
                    "Cannot initialize GeminiClient: GEMINI_API_KEY is not set. "
                    "Configure it in your environment or .env file."
                )
            if genai is None:
                raise LLMConfigError(
                    "google-genai package is not installed. Please install requirements."
                )
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _is_retryable_error(self, exc: Exception) -> bool:
        """Determine if an exception should trigger an automatic retry."""
        # Check standard network / timeout exceptions
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True

        # Check status codes if available on APIError
        status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if status_code in (429, 500, 502, 503, 504):
            return True

        err_str = str(exc).lower()
        retryable_keywords = [
            "rate limit",
            "resource_exhausted",
            "quota",
            "deadline exceeded",
            "timeout",
            "service unavailable",
            "try again",
        ]
        return any(kw in err_str for kw in retryable_keywords)

    def _execute_with_retry(
        self,
        call_fn: Any,
        max_retries: Optional[int] = None,
        initial_backoff: float = 1.0,
        backoff_factor: float = 2.0,
    ) -> Any:
        """Execute a callable with exponential backoff on retryable errors."""
        retries = max_retries if max_retries is not None else self.settings.max_retries
        last_exception: Optional[Exception] = None
        delay = initial_backoff

        for attempt in range(retries + 1):
            try:
                return call_fn()
            except Exception as exc:
                last_exception = exc

                # Check if it's an API error or rate limit
                status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                if status_code == 429 or "resource_exhausted" in str(exc).lower():
                    logger.warning("Gemini rate limit encountered on attempt %d/%d", attempt + 1, retries + 1)
                elif "timeout" in str(exc).lower() or isinstance(exc, TimeoutError):
                    logger.warning("Gemini request timeout on attempt %d/%d", attempt + 1, retries + 1)

                if attempt < retries and self._is_retryable_error(exc):
                    logger.info("Retrying Gemini call in %.2f seconds (attempt %d/%d)...", delay, attempt + 1, retries)
                    time.sleep(delay)
                    delay *= backoff_factor
                else:
                    break

        # Map to specific domain exceptions
        if last_exception:
            status_code = getattr(last_exception, "code", None) or getattr(last_exception, "status_code", None)
            err_msg = str(last_exception)
            if status_code == 429 or "resource_exhausted" in err_msg.lower():
                raise LLMRateLimitError(
                    f"Gemini API rate limit exceeded: {err_msg}",
                    status_code=429,
                    raw_error=last_exception,
                ) from last_exception
            if "timeout" in err_msg.lower() or isinstance(last_exception, TimeoutError):
                raise LLMTimeoutError(
                    f"Gemini API call timed out: {err_msg}",
                    status_code=504,
                    raw_error=last_exception,
                ) from last_exception
            raise LLMAPIError(
                f"Gemini API call failed: {err_msg}",
                status_code=status_code,
                raw_error=last_exception,
            ) from last_exception

        raise LLMError("Unexpected error: Retry loop exited without result or exception.")

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> str:
        """Generate plain text from Gemini.

        Args:
            prompt: User prompt content.
            system_instruction: Optional system instruction/guardrails.
            model: Model name override (defaults to configured model).
            temperature: Temperature override (defaults to configured temperature).
            max_retries: Retry count override.

        Returns:
            The generated text string.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        target_model = model or self.default_model
        temp = temperature if temperature is not None else self.settings.temperature

        def _call() -> str:
            config_kwargs: Dict[str, Any] = {"temperature": temp}
            if system_instruction:
                config_kwargs["system_instruction"] = system_instruction

            config = types.GenerateContentConfig(**config_kwargs) if types else None

            response = self.client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config,
            )
            return response.text or ""

        return self._execute_with_retry(_call, max_retries=max_retries)

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> T:
        """Generate structured JSON and validate it against a Pydantic schema.

        Args:
            prompt: User prompt content.
            response_schema: Pydantic model class defining the expected response format.
            system_instruction: Optional system instruction.
            model: Model override.
            temperature: Temperature override.
            max_retries: Retry count override.

        Returns:
            An instance of response_schema populated with the LLM response.

        Raises:
            LLMResponseValidationError: If LLM output fails schema validation.
            LLMAPIError: If API call fails.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")
        if not issubclass(response_schema, BaseModel):
            raise TypeError("response_schema must be a subclass of pydantic.BaseModel")

        target_model = model or self.default_model
        temp = temperature if temperature is not None else self.settings.temperature

        def _call() -> Any:
            config_kwargs: Dict[str, Any] = {
                "temperature": temp,
                "response_mime_type": "application/json",
                "response_schema": response_schema,
            }
            if system_instruction:
                config_kwargs["system_instruction"] = system_instruction

            config = types.GenerateContentConfig(**config_kwargs) if types else None

            return self.client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config,
            )

        response = self._execute_with_retry(_call, max_retries=max_retries)

        # 1. Check if the SDK already parsed the object directly
        if hasattr(response, "parsed") and response.parsed is not None:
            if isinstance(response.parsed, response_schema):
                return response.parsed
            try:
                # In case parsed is a dict
                if isinstance(response.parsed, dict):
                    return response_schema.model_validate(response.parsed)
            except ValidationError as val_err:
                raise LLMResponseValidationError(
                    f"Parsed object validation failed: {val_err}",
                    raw_response=str(response.parsed),
                    validation_error=val_err,
                ) from val_err

        # 2. Extract and clean raw text
        raw_text = getattr(response, "text", None) or ""
        clean_text = self._clean_json_markdown(raw_text)

        # 3. Validate JSON with Pydantic
        try:
            parsed_data = json.loads(clean_text)
            return response_schema.model_validate(parsed_data)
        except ValidationError as val_err:
            raise LLMResponseValidationError(
                f"Failed to validate response against schema {response_schema.__name__}: {val_err}",
                raw_response=raw_text,
                validation_error=val_err,
            ) from val_err
        except (json.JSONDecodeError, ValueError) as json_err:
            raise LLMResponseValidationError(
                f"LLM output could not be decoded as valid JSON: {json_err}",
                raw_response=raw_text,
            ) from json_err

    @staticmethod
    def _clean_json_markdown(text: str) -> str:
        """Clean markdown code block wrappers (```json ... ```) from text."""
        text = text.strip()
        # Match ```json ... ``` or ``` ... ```
        pattern = r"^```(?:json)?\s*([\s\S]*?)\s*```$"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text


# Global singleton cache
_CLIENT_INSTANCE: Optional[GeminiClient] = None


def get_gemini_client(reload: bool = False, **kwargs: Any) -> GeminiClient:
    """Retrieve or create the singleton Gemini client instance.

    Args:
        reload: If True, forces re-instantiation of the client.
        **kwargs: Additional parameters passed to GeminiClient.
    """
    global _CLIENT_INSTANCE
    if reload or _CLIENT_INSTANCE is None:
        _CLIENT_INSTANCE = GeminiClient(**kwargs)
    return _CLIENT_INSTANCE

