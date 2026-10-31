"""Security validation, path traversal defense, and safe temporary storage management."""

import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Optional

from app.api.config import APIConfig, DEFAULT_API_CONFIG
from app.ingestion.exceptions import (
    EmptyPDFError,
    FileTooLargeError,
    InvalidPDFError,
    PathTraversalError,
)

logger = logging.getLogger(__name__)

# Pattern restricting submission IDs to safe alphanumeric strings and hyphens/underscores
SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


class SecurityValidator:
    """Enforces strict security checks on uploaded files and temporary paths."""

    def __init__(self, config: Optional[APIConfig] = None) -> None:
        self.config = config or DEFAULT_API_CONFIG

    def sanitize_submission_id(self, submission_id: Optional[str]) -> str:
        """Validate or generate a safe submission identifier avoiding directory traversal."""
        if not submission_id:
            return f"sub-{uuid.uuid4().hex[:12]}"

        clean_id = submission_id.strip()
        if not SAFE_ID_REGEX.match(clean_id) or ".." in clean_id or "/" in clean_id or "\\" in clean_id:
            raise PathTraversalError(f"Invalid or unsafe submission_id '{submission_id}'")

        return clean_id

    def validate_file_content(self, file_bytes: bytes, filename: str) -> None:
        """Enforce file size and magic-byte validation on incoming uploaded bytes."""
        # 1. Size check
        if not file_bytes:
            raise EmptyPDFError("Uploaded file is empty (0 bytes)")

        if len(file_bytes) > self.config.max_file_size_bytes:
            raise FileTooLargeError(
                f"File size ({len(file_bytes)} bytes) exceeds maximum limit ({self.config.max_file_size_bytes} bytes)"
            )

        # 2. Extension check
        ext = Path(filename).suffix.lower()
        if ext not in self.config.allowed_extensions:
            raise InvalidPDFError(f"Unsupported file extension '{ext}'. Only {self.config.allowed_extensions} are accepted.")

        # 3. Magic bytes check
        if not file_bytes.startswith(b"%PDF-"):
            raise InvalidPDFError("File does not start with standard PDF header magic bytes ('%PDF-')")

    def create_job_storage(self, job_id: str) -> Path:
        """Create a dedicated, isolated temporary workspace for an OCR job."""
        root = Path(self.config.storage_root).resolve()
        job_dir = root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    @classmethod
    def cleanup_directory(cls, path: Path) -> None:
        """Safely delete temporary directory and its contents."""
        try:
            if path and path.exists() and path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                logger.info("Cleaned up temporary workspace '%s'", path)
        except Exception as e:
            logger.warning("Failed to clean up temporary directory '%s': %s", path, e)

