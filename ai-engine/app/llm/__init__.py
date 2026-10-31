"""LLM integration: OpenRouter (primary) and Gemini behind one fallback client."""

from app.llm.gemini_client import (
    GeminiClient,
    get_gemini_client,
    LLMError,
    LLMConfigError,
    LLMAPIError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMResponseValidationError,
)
from app.llm.openai_compatible_client import LLMConnectionError, OpenAICompatibleClient
from app.llm.fallback_client import (
    AllProvidersFailedError,
    FallbackLLMClient,
    ProviderEntry,
    get_llm_client,
)
from app.llm import prompts

__all__ = [
    "OpenAICompatibleClient",
    "LLMConnectionError",
    "FallbackLLMClient",
    "ProviderEntry",
    "AllProvidersFailedError",
    "get_llm_client",
    "GeminiClient",
    "get_gemini_client",
    "LLMError",
    "LLMConfigError",
    "LLMAPIError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMResponseValidationError",
    "prompts",
]

