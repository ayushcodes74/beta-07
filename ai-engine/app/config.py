"""Configuration management for the AI Engine."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Automatically load .env file from ai-engine directory or parents if present
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")


def _csv(value: Optional[str]) -> List[str]:
    """Split a comma-separated env value into a list of non-empty, stripped items."""
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    # Gemini API settings
    gemini_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY")
    )
    gemini_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    )
    gemini_embedding_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004")
    )

    # Extra Gemini models tried (in order) when the primary model fails. Free-tier quotas are
    # tracked per model, so another Gemini model often still works when the primary is exhausted.
    gemini_fallback_models: List[str] = field(
        default_factory=lambda: _csv(os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-3.5-flash"))
    )

    # OpenRouter (OpenAI-compatible API) — primary provider
    openrouter_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY"))
    openrouter_model: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
    )
    # Extra OpenRouter models tried (in order) before moving on to Gemini. Free (":free") models
    # have shared, fairly tight rate limits, so a couple of alternates help a lot.
    openrouter_fallback_models: List[str] = field(
        default_factory=lambda: _csv(os.getenv(
            "OPENROUTER_FALLBACK_MODELS", "nvidia/nemotron-3.5-super-vl:free,google/gemma-4-26b-a4b-it:free"
        ))
    )
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    # Reasoning ("thinking") for OpenRouter models: off | low | medium | high | default.
    # "off" is much faster for this workload (measured: 66s -> 13s for question generation on
    # nemotron) with no loss of validity; "default" leaves it to each model.
    openrouter_reasoning: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_REASONING", "off").strip().lower()
    )

    # Order in which providers are tried. Providers without an API key are skipped.
    llm_provider_order: List[str] = field(
        default_factory=lambda: [
            p.lower() for p in _csv(os.getenv("LLM_PROVIDER_ORDER", "openrouter,gemini"))
        ]
    )
    # Retries on the *same* model before failing over to the next one. Kept low because
    # switching models is usually faster than backing off on a rate-limited one.
    llm_retries_per_provider: int = field(
        default_factory=lambda: int(os.getenv("LLM_RETRIES_PER_PROVIDER", "1"))
    )
    # Per-request timeout (seconds) for every provider, so a hung call fails over instead of
    # stalling generation. Generating many questions can legitimately take tens of seconds.
    llm_request_timeout: float = field(
        default_factory=lambda: float(os.getenv("LLM_REQUEST_TIMEOUT", "90"))
    )
    # After a provider is rate limited (or unreachable), skip it (try it last) for this many seconds
    # so every call doesn't waste a round-trip on it. Daily-quota exhaustion uses the longer cooldown.
    llm_rate_limit_cooldown: float = field(
        default_factory=lambda: float(os.getenv("LLM_RATE_LIMIT_COOLDOWN_SECONDS", "300"))
    )
    llm_quota_exhausted_cooldown: float = field(
        default_factory=lambda: float(os.getenv("LLM_QUOTA_EXHAUSTED_COOLDOWN_SECONDS", "1800"))
    )

    # Execution & reliability parameters
    temperature: float = field(
        default_factory=lambda: float(os.getenv("GEMINI_TEMPERATURE", "0.2"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("GEMINI_MAX_RETRIES", "3"))
    )
    request_timeout: float = field(
        default_factory=lambda: float(os.getenv("GEMINI_REQUEST_TIMEOUT", "30.0"))
    )

    # Answer checking (POST /v1/grading/grade-submission)
    # "lenient": credit ideas expressed in the student's own words and partial answers;
    # "standard": the evaluator's default strictness.
    grading_leniency: str = field(
        default_factory=lambda: os.getenv("GRADING_LENIENCY", "lenient").strip().lower()
    )
    # Share of a marking point's marks awarded when the point is only partly present (the LLM found
    # related evidence). Enforced after grading as a minimum; 0 disables it.
    grading_partial_credit: float = field(
        default_factory=lambda: min(1.0, max(0.0, float(os.getenv("GRADING_PARTIAL_CREDIT", "0.5"))))
    )

    # Course-material RAG for grading (persistent local index, real sentence-transformer embeddings)
    rag_top_k: int = field(default_factory=lambda: int(os.getenv("RAG_TOP_K", "4")))
    # Minimum cosine similarity for a course passage to count as evidence (all-MiniLM-L6-v2 scale).
    rag_min_similarity: float = field(default_factory=lambda: float(os.getenv("RAG_MIN_SIMILARITY", "0.3")))

    # Application environment
    environment: str = field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "development")
    )

    def validate_api_key(self) -> str:
        """Validate that the Gemini API key is configured.

        Raises:
            ValueError: If GEMINI_API_KEY is not set or empty.
        """
        if not self.gemini_api_key or not self.gemini_api_key.strip():
            raise ValueError(
                "GEMINI_API_KEY environment variable is missing or empty. "
                "Please configure GEMINI_API_KEY in your .env file or environment."
            )
        return self.gemini_api_key


_SETTINGS_INSTANCE: Optional[Settings] = None


def get_settings(reload: bool = False) -> Settings:
    """Retrieve or create the cached application settings.

    Args:
        reload: Force reloading of settings from the environment.
    """
    global _SETTINGS_INSTANCE
    if reload or _SETTINGS_INSTANCE is None:
        load_dotenv(_BASE_DIR / ".env", override=False)
        _SETTINGS_INSTANCE = Settings()
    return _SETTINGS_INSTANCE

