"""Course leaderboard rows from the public.course_leaderboard RPC (phase3b_course_leaderboard.sql).

The RPC runs as SECURITY DEFINER (students cannot read classmates' grades under RLS) and checks
inside that the caller is the course's teacher or an actively enrolled student.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import UUID

from app.database.supabase import get_user_supabase

logger = logging.getLogger(__name__)


class LeaderboardUnavailableError(Exception):
    """The RPC failed, e.g. phase3b_course_leaderboard.sql has not been applied yet."""


class LeaderboardRepository(Protocol):
    def course_leaderboard(self, course_id: UUID, *, access_token: str) -> list[dict[str, Any]]: ...


class SupabaseLeaderboardRepository:
    def course_leaderboard(self, course_id: UUID, *, access_token: str) -> list[dict[str, Any]]:
        try:
            client = get_user_supabase(access_token)
            resp = client.rpc("course_leaderboard", {"target_course_id": str(course_id)}).execute()
        except Exception as exc:
            logger.error("course_leaderboard RPC failed: %s", exc)
            raise LeaderboardUnavailableError("Leaderboard query failed") from exc
        return list(resp.data or [])
