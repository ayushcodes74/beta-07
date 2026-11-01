"""Files a teacher attaches to assignment questions (see phase3e_assignment_attachments.sql)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

ExtractionStatus = Literal["pending", "ready", "no_text", "failed"]


class AttachmentRecord(BaseModel):
    id: UUID
    assignment_id: UUID
    question_number: int
    storage_path: str
    filename: str
    content_type: str
    size_bytes: int
    extraction_status: ExtractionStatus = "pending"
    extracted_text: Optional[str] = None
    extraction_error: Optional[str] = None
    uploaded_by: UUID
    created_at: datetime


class AttachmentResponse(BaseModel):
    id: UUID
    assignment_id: UUID
    question_number: int = Field(ge=1, description="1-based question the file belongs to")
    filename: str
    content_type: str
    size_bytes: int
    url: Optional[str] = Field(default=None, description="Short-lived signed URL to view/download the file")
    extraction_status: ExtractionStatus = Field(
        description="Text extraction for AI grading: pending, ready, no_text (nothing readable) or failed"
    )
    text_preview: Optional[str] = Field(
        default=None, description="Teacher only: start of the text the AI will see for this file"
    )
    created_at: datetime
