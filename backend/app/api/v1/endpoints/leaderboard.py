"""Course leaderboard endpoint.

  - GET /courses/{course_id}/leaderboard  (owning teacher or actively enrolled student)

Ranks the course's active students by total marks from teacher-published grades. Students see
classmates' names and totals (no emails, feedback, or per-assignment detail).
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.endpoints.courses import ERROR_RESPONSES, _HANDLED_ERRORS, _raise_http, get_course_service
from app.core.dependencies import api_error, get_bearer_token, require_authenticated_user
from app.database.leaderboard_repository import LeaderboardUnavailableError, SupabaseLeaderboardRepository
from app.schemas.leaderboard import LeaderboardResponse
from app.services.auth_service import CurrentUser
from app.services.course_service import CourseService
from app.services.leaderboard_service import LeaderboardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["leaderboard"])

AnyUser = Annotated[CurrentUser, Depends(require_authenticated_user)]
AccessToken = Annotated[str, Depends(get_bearer_token)]


def get_leaderboard_service(
    courses: Annotated[CourseService, Depends(get_course_service)],
) -> LeaderboardService:
    return LeaderboardService(courses, SupabaseLeaderboardRepository())


Leaderboards = Annotated[LeaderboardService, Depends(get_leaderboard_service)]


@router.get(
    "/{course_id}/leaderboard",
    response_model=LeaderboardResponse,
    summary="Course leaderboard by total published marks",
    description=(
        "Owning teacher or actively enrolled student. Active students ranked by the sum of their "
        "teacher-published final scores in this course (ties share a rank). Unpublished grades never count."
    ),
    responses=ERROR_RESPONSES,
)
def get_course_leaderboard(
    course_id: UUID, user: AnyUser, token: AccessToken, leaderboards: Leaderboards
) -> LeaderboardResponse:
    try:
        return leaderboards.course_leaderboard(user, course_id, access_token=token)
    except _HANDLED_ERRORS as exc:
        _raise_http(exc)
    except LeaderboardUnavailableError:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "leaderboard_unavailable",
            "The leaderboard is not available yet. Ask the administrator to apply phase3b_course_leaderboard.sql.",
        ) from None
