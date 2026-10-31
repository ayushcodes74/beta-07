"""Student <-> teacher chat schemas (see phase3c_course_messages.sql).

A conversation ("thread") is identified by (course_id, student_id): one private thread per
student per course, with that course's teacher.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

MAX_MESSAGE_CHARS = 4000


class MessageCreate(BaseModel):
    """Send a message. Teachers must say which student's thread; students always write to their own."""

    body: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    student_id: Optional[UUID] = Field(
        default=None, description="Teacher only: the student whose conversation this is."
    )

    @field_validator("body")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty.")
        return value


class MarkReadRequest(BaseModel):
    student_id: Optional[UUID] = Field(
        default=None, description="Teacher only: the student whose conversation to mark as read."
    )


class MarkReadResponse(BaseModel):
    updated: int = Field(description="How many messages were newly marked as read.")


class MessageResponse(BaseModel):
    id: UUID
    course_id: UUID
    student_id: UUID
    sender_id: UUID
    body: str
    read_at: Optional[datetime] = None
    created_at: datetime
    is_mine: bool = Field(default=False, description="Sent by the signed-in user.")


class MessageThread(BaseModel):
    """One conversation in the signed-in user's inbox."""

    course_id: UUID
    course_name: str
    student_id: UUID
    student_name: str
    teacher_id: UUID
    teacher_name: str
    last_message: str
    last_message_is_mine: bool
    last_message_at: datetime
    unread_count: int = 0
