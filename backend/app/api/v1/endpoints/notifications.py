"""Dashboard notifications (bell icon) for students and teachers.

  - GET  /notifications        latest notifications addressed to the caller + unread count
  - POST /notifications/read   mark some (``ids``) or all (no ``ids``) of them as read

Notifications are created by the other endpoints (assignments, submissions, grading,
reviews) as background tasks; see app/services/notification_service.py.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.v1.endpoints.auth import AUTH_ERROR_RESPONSES
from app.core.dependencies import api_error, get_bearer_token, require_authenticated_user
from app.database.notification_repository import NotificationRepository, NotificationRepositoryError
from app.schemas.auth import ErrorResponse
from app.schemas.notification import NotificationListResponse, NotificationMarkReadRequest
from app.services.auth_service import CurrentUser
from app.services.notification_service import MAX_LIST, NotificationService, get_notification_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

AnyUser = Annotated[CurrentUser, Depends(require_authenticated_user)]
AccessToken = Annotated[str, Depends(get_bearer_token)]


def get_notification_service(
    repository: Annotated[NotificationRepository, Depends(get_notification_repository)],
) -> NotificationService:
    return NotificationService(repository)


Notifications = Annotated[NotificationService, Depends(get_notification_service)]

ERROR_RESPONSES: dict[int | str, dict] = {
    **AUTH_ERROR_RESPONSES,
    503: {"model": ErrorResponse, "description": "Notification storage is unavailable."},
}


def _unavailable(exc: Exception):
    logger.error("Notification storage error: %s", exc)
    return api_error(
        status.HTTP_503_SERVICE_UNAVAILABLE, "notifications_unavailable", "Notifications are temporarily unavailable."
    )


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="My notifications",
    description="Newest first (at most 50), plus the total number of unread notifications.",
    responses=ERROR_RESPONSES,
)
def list_notifications(
    user: AnyUser,
    token: AccessToken,
    notifications: Notifications,
    limit: int = Query(default=30, ge=1, le=MAX_LIST),
) -> NotificationListResponse:
    try:
        return notifications.list_for(user, access_token=token, limit=limit)
    except NotificationRepositoryError as exc:
        raise _unavailable(exc) from None


@router.post(
    "/read",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Mark notifications as read",
    description="Marks the given `ids` as read, or every unread notification when `ids` is omitted.",
    responses=ERROR_RESPONSES,
)
def mark_notifications_read(
    body: NotificationMarkReadRequest, user: AnyUser, token: AccessToken, notifications: Notifications
) -> Response:
    try:
        notifications.mark_read(user, body.ids, access_token=token)
    except NotificationRepositoryError as exc:
        raise _unavailable(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
