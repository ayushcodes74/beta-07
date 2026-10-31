"""Course leaderboard: active students ranked by total marks from teacher-published grades."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LeaderboardEntry(BaseModel):
    rank: int = Field(ge=1, description="Standard competition rank; ties share a rank (1, 2, 2, 4)")
    student_id: UUID
    name: str
    total_score: float = Field(description="Sum of published final scores in this course")
    percentage: Optional[float] = Field(
        default=None, description="total_score / total_possible * 100; null while nothing is published"
    )
    assignments_graded: int = Field(ge=0, description="Counted assignments this student has a published grade for")
    last_published_at: Optional[datetime] = None
    is_you: bool = Field(default=False, description="True for the signed-in student's own row")


class LeaderboardResponse(BaseModel):
    course_id: UUID
    course_name: str
    total_possible: float = Field(description="Sum of total marks over assignments with a published grade")
    assignments_counted: int = Field(ge=0, description="Assignments with at least one published grade")
    entries: List[LeaderboardEntry] = Field(default_factory=list)
