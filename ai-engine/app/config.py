"""Configuration management for the AI Engine."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Automatically load .env file from ai-engine directory or parents if present
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")


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

