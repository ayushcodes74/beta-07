"""Configuration settings for Module 5 OCR API and job processing."""

import os
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field


class APIConfig(BaseModel):
    """Configuration parameters for the OCR API service and background workers."""

    # Server settings
    host: str = Field(default="127.0.0.1", description="Service host binding")
    port: int = Field(default=8001, description="Service port (defaults to 8001 to avoid colliding with backend on 8000)")
    debug: bool = Field(default=False, description="Debug mode")

    # Upload and security limits
    max_file_size_bytes: int = Field(
        default=20 * 1024 * 1024,
        description="Maximum allowed PDF upload size in bytes (20 MB)",
    )
    max_pages: int = Field(
        default=100,
        description="Maximum allowed page count per assignment PDF",
    )
    allowed_extensions: List[str] = Field(
        default_factory=lambda: [".pdf"],
        description="Allowed file extensions",
    )

    # Storage and Job settings
    storage_root: str = Field(
        default="ocr-engine/storage",
        description="Base directory for temporary job artifacts and page crops",
    )
    concurrency_limit: int = Field(
        default=4,
        description="Maximum concurrent asynchronous background worker threads",
    )
    job_timeout_seconds: float = Field(
        default=300.0,
        description="Maximum allowed processing timeout per job (5 minutes)",
    )


DEFAULT_API_CONFIG = APIConfig()

