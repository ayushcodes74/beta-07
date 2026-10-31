"""Course leaderboard: rank a course's active students by total marks from published grades."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.database.leaderboard_repository import LeaderboardRepository
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse
from app.services.auth_service import CurrentUser
from app.services.course_service import CourseService


class LeaderboardService:
    def __init__(self, courses: CourseService, repository: LeaderboardRepository) -> None:
        self.courses = courses
        self.repository = repository

    def course_leaderboard(self, user: CurrentUser, course_id: UUID, *, access_token: str) -> LeaderboardResponse:
        # Owning teacher or actively enrolled student; anyone else gets CourseNotFoundError (404).
        course = self.courses.get_for(user, course_id, access_token=access_token)
        rows = self.repository.course_leaderboard(course_id, access_token=access_token)

        total_possible = _number(rows[0].get("total_possible")) if rows else 0.0
        counted = int(rows[0].get("assignments_counted") or 0) if rows else 0
        entries = [
            LeaderboardEntry(
                rank=int(row["leaderboard_rank"]),
                student_id=UUID(str(row["student_id"])),
                name=(row.get("display_name") or "").strip() or "Student",
                total_score=round(_number(row.get("total_score")), 2),
                percentage=(
                    round(_number(row.get("total_score")) / total_possible * 100, 1) if total_possible > 0 else None
                ),
                assignments_graded=int(row.get("assignments_graded") or 0),
                last_published_at=_datetime(row.get("last_published_at")),
                is_you=str(row["student_id"]) == str(user.id),
            )
            for row in rows
        ]
        entries.sort(key=lambda e: (e.rank, e.name.lower()))
        return LeaderboardResponse(
            course_id=course.id,
            course_name=course.name,
            total_possible=round(total_possible, 2),
            assignments_counted=counted,
            entries=entries,
        )


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
