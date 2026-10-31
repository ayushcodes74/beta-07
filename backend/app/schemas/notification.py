"""Dashboard notification API schemas (see phase3d_notifications.sql)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationType(StrEnum):
    # teacher -> student
    ASSIGNMENT_PUBLISHED = "assignment_published"
    ASSIGNMENT_UPDATED = "assignment_updated"
    RESULT_PUBLISHED = "result_published"
    RESULT_UPDATED = "result_updated"
    LATE_DECISION = "late_decision"
    REVIEW_RESOLVED = "review_resolved"
    # student -> teacher
    SUBMISSION_RECEIVED = "submission_received"
    REVIEW_REQUESTED = "review_requested"


class NotificationResponse(BaseModel):
    id: UUID
    type: NotificationType
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    actor_id: Optional[UUID] = None
    assignment_id: Optional[UUID] = None
    submission_id: Optional[UUID] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    unread_count: int


class NotificationMarkReadRequest(BaseModel):
    """Mark the given notifications as read; omit ``ids`` to mark all of them read."""

    ids: Optional[List[UUID]] = Field(default=None, max_length=200)
