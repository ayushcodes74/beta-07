"""Multi-provider LLM client with automatic failover.

Tries each configured provider/model in order (default: OpenRouter primary model ->
OpenRouter fallback models -> Gemini primary -> Gemini fallback models). If a call fails for any provider-side reason — rate limit,
quota exhaustion, timeout, outage, missing key, or an unusable/invalid response — the next
provider is tried. Callers use the same ``generate_text`` / ``generate_structured`` interface
as GeminiClient, so this is a drop-in replacement.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

from app.config import Settings, get_settings
from app.llm.gemini_client import (
    GeminiClient,
    LLMAPIError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.llm.openai_compatible_client import LLMConnectionError, OpenAICompatibleClient

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class ProviderEntry:
    """One link in the fallback chain: a client plus the model to call on it."""

    provider: str  # "openrouter" | "gemini" | custom
    model: str
    client: Any  # anything exposing generate_text / generate_structured(model=...)

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


class AllProvidersFailedError(LLMAPIError):
    """Raised when every provider in the chain failed. ``errors`` holds (label, exception) pairs."""

    def __init__(self, message: str, errors: List[tuple], status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code)
        self.errors = errors


class FallbackLLMClient:
    """Drop-in LLM client that fails over across providers and models."""

    def __init__(self, providers: List[ProviderEntry], settings: Optional[Settings] = None):
        # An empty chain is allowed so services can start unconfigured; calls then raise LLMConfigError.
        self.providers = providers
        self.settings = settings or get_settings()
        self._cooldown_until: Dict[str, float] = {}

    @property
    def default_model(self) -> Optional[str]:
        return self.providers[0].model if self.providers else None

    def describe(self) -> List[str]:
        return [p.label for p in self.providers]

    # ------------------------------------------------------------------

    def _run(self, op_name: str, call: Callable[[ProviderEntry, Optional[int]], Any], max_retries: Optional[int]) -> Any:
        if not self.providers:
            raise LLMConfigError(
                "No LLM provider is configured. Set OPENROUTER_API_KEY and/or GEMINI_API_KEY."
            )
        retries = max_retries if max_retries is not None else self.settings.llm_retries_per_provider
        errors: List[tuple] = []
        for entry in self._ordered_providers():
            # Only LLMError triggers failover; caller errors (ValueError/TypeError for an empty
            # prompt or bad schema) propagate because another provider wouldn't help.
            try:
                result = call(entry, retries)
                self._cooldown_until.pop(entry.label, None)
                if errors:
                    logger.info("LLM %s succeeded on fallback provider %s", op_name, entry.label)
                return result
            except LLMError as exc:
                logger.warning(
                    "LLM provider %s failed for %s (%s): %s",
                    entry.label, op_name, type(exc).__name__, str(exc)[:200],
                )
                errors.append((entry.label, exc))
                if isinstance(exc, (LLMRateLimitError, LLMConnectionError)):
                    quota = "perday" in str(exc).lower().replace(" ", "")
                    seconds = (
                        self.settings.llm_quota_exhausted_cooldown if quota else self.settings.llm_rate_limit_cooldown
                    )
                    self._cooldown_until[entry.label] = time.monotonic() + seconds
        raise self._combine_errors(errors)

    def _ordered_providers(self) -> List[ProviderEntry]:
        """Configured order, but providers still cooling down after a rate limit go last.

        Cooling-down providers are still tried as a last resort rather than skipped entirely.
        """
        now = time.monotonic()
        ready = [p for p in self.providers if self._cooldown_until.get(p.label, 0) <= now]
        cooling = [p for p in self.providers if self._cooldown_until.get(p.label, 0) > now]
        return ready + cooling

    @staticmethod
    def _combine_errors(errors: List[tuple]) -> LLMError:
        """Choose the most meaningful error type so the HTTP layer maps it sensibly."""
        summary = "; ".join(f"{label}: {type(exc).__name__}" for label, exc in errors)
        excs = [exc for _, exc in errors]

        if all(isinstance(e, LLMConfigError) for e in excs):
            return LLMConfigError(f"No usable LLM provider configured ({summary})")
        real = [e for e in excs if not isinstance(e, LLMConfigError)]
        if all(isinstance(e, LLMRateLimitError) for e in real):
            err: LLMError = LLMRateLimitError(f"All LLM providers are rate limited ({summary})", status_code=429)
        elif all(isinstance(e, LLMTimeoutError) for e in real):
            err = LLMTimeoutError(f"All LLM providers timed out ({summary})", status_code=504)
        elif all(isinstance(e, LLMResponseValidationError) for e in real):
            last = real[-1]
            err = LLMResponseValidationError(
                f"All LLM providers returned unusable output ({summary})",
                raw_response=getattr(last, "raw_response", ""),
                validation_error=getattr(last, "validation_error", None),
            )
        else:
            err = AllProvidersFailedError(f"All LLM providers failed ({summary})", errors=errors)
        err.__cause__ = excs[-1]
        return err

    # ------------------------------------------------------------------
    # Public interface (mirrors GeminiClient)
    # ------------------------------------------------------------------

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,  # ignored: each provider uses its own configured model
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> str:
        return self._run(
            "generate_text",
            lambda e, r: e.client.generate_text(
                prompt=prompt, system_instruction=system_instruction, model=e.model,
                temperature=temperature, max_retries=r,
            ),
            max_retries,
        )

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,  # ignored: each provider uses its own configured model
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> T:
        return self._run(
            f"generate_structured[{getattr(response_schema, '__name__', 'schema')}]",
            lambda e, r: e.client.generate_structured(
                prompt=prompt, response_schema=response_schema, system_instruction=system_instruction,
                model=e.model, temperature=temperature, max_retries=r,
            ),
            max_retries,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _has_key(key: Optional[str]) -> bool:
    return bool(key and key.strip() and not key.strip().startswith("your_"))


def _openrouter_reasoning(mode: str) -> dict:
    """Map OPENROUTER_REASONING to OpenRouter's unified ``reasoning`` request field."""
    if mode in ("off", "none", "false", "disabled"):
        return {"reasoning": {"enabled": False}}
    if mode in ("low", "medium", "high"):
        return {"reasoning": {"effort": mode}}
    if mode not in ("", "default"):
        logger.warning("Unknown OPENROUTER_REASONING=%r; using the model default", mode)
    return {}


def build_providers(settings: Settings) -> List[ProviderEntry]:
    """Build the provider chain from settings, skipping providers without an API key."""
    providers: List[ProviderEntry] = []
    for name in settings.llm_provider_order:
        if name == "gemini" and _has_key(settings.gemini_api_key):
            client = GeminiClient(settings=settings)
            models = [settings.gemini_model] + [
                m for m in settings.gemini_fallback_models if m != settings.gemini_model
            ]
            providers.extend(ProviderEntry("gemini", m, client) for m in models)
        elif name == "openrouter" and _has_key(settings.openrouter_api_key):
            client = OpenAICompatibleClient(
                "openrouter", settings.openrouter_api_key, settings.openrouter_base_url,
                settings.openrouter_model, settings=settings,
                extra_headers={"X-Title": "TrustGrade AI Engine"},
                extra_body=_openrouter_reasoning(settings.openrouter_reasoning),
            )
            models = [settings.openrouter_model] + [
                m for m in settings.openrouter_fallback_models if m != settings.openrouter_model
            ]
            providers.extend(ProviderEntry("openrouter", m, client) for m in models)
        elif name not in ("gemini", "openrouter"):
            logger.warning("Unknown LLM provider '%s' in LLM_PROVIDER_ORDER; ignoring", name)
    return providers


_CLIENT_INSTANCE: Optional[FallbackLLMClient] = None


def get_llm_client(reload: bool = False, settings: Optional[Settings] = None) -> FallbackLLMClient:
    """Return the shared multi-provider client (built lazily from settings)."""
    global _CLIENT_INSTANCE
    if reload or _CLIENT_INSTANCE is None:
        settings = settings or get_settings()
        _CLIENT_INSTANCE = FallbackLLMClient(build_providers(settings), settings=settings)
        logger.info("LLM fallback chain: %s", " -> ".join(_CLIENT_INSTANCE.describe()))
    return _CLIENT_INSTANCE
