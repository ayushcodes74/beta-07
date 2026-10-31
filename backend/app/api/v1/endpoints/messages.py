"""Student <-> teacher chat endpoints.

  - GET  /messages/threads                   the signed-in user's conversations (inbox)
  - GET  /courses/{course_id}/messages       one conversation (?student_id= for teachers, ?after= to poll)
  - POST /courses/{course_id}/messages       send a message
  - POST /courses/{course_id}/messages/read  mark the messages you received in a conversation as read

A conversation is private to one student and the course's teacher. Students always use their own
conversation; teachers pass the student's id.
"""

import logging
from datetime import datetime
from typing import Annotated, NoReturn, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.v1.endpoints.courses import ERROR_RESPONSES, _HANDLED_ERRORS, _raise_http, get_course_service
from app.core.dependencies import api_error, get_bearer_token, require_authenticated_user
from app.database.message_repository import MessageRepositoryError, SupabaseMessageRepository
from app.schemas.message import (
    MarkReadRequest,
    MarkReadResponse,
    MessageCreate,
    MessageResponse,
    MessageThread,
)
from app.services.auth_service import CurrentUser
from app.services.course_service import CourseRepository, CourseService, get_course_repository
from app.services.message_service import MessageService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["messages"])

AnyUser = Annotated[CurrentUser, Depends(require_authenticated_user)]
AccessToken = Annotated[str, Depends(get_bearer_token)]


def get_message_service(
    courses: Annotated[CourseService, Depends(get_course_service)],
    course_repo: Annotated[CourseRepository, Depends(get_course_repository)],
) -> MessageService:
    return MessageService(courses, course_repo, SupabaseMessageRepository())


Messages = Annotated[MessageService, Depends(get_message_service)]


def _handle(exc: Exception) -> NoReturn:
    if isinstance(exc, MessageRepositoryError):
        logger.error("Message storage error: %s", exc)
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "messages_unavailable",
            "Messaging is not available yet. Ask the administrator to apply phase3c_course_messages.sql.",
        ) from None
    if isinstance(exc, _HANDLED_ERRORS):
        _raise_http(exc)
    raise exc


@router.get(
    "/messages/threads",
    response_model=list[MessageThread],
    summary="List my conversations",
    description=(
        "Students: their conversations with the teachers of courses they are enrolled in. Teachers: "
        "conversations with students in their own courses. Newest first, with unread counts."
    ),
    responses=ERROR_RESPONSES,
)
def list_threads(user: AnyUser, token: AccessToken, messages: Messages) -> list[MessageThread]:
    try:
        return messages.list_threads(user, access_token=token)
    except Exception as exc:
        _handle(exc)


@router.get(
    "/courses/{course_id}/messages",
    response_model=list[MessageResponse],
    summary="Read a conversation",
    description=(
        "Oldest first. Students always get their own conversation; teachers must pass `student_id`. "
        "Pass `after` (the last message's `created_at`) to fetch only newer messages."
    ),
    responses=ERROR_RESPONSES,
)
def get_messages(
    course_id: UUID,
    user: AnyUser,
    token: AccessToken,
    messages: Messages,
    student_id: Annotated[Optional[UUID], Query(description="Teacher only: whose conversation.")] = None,
    after: Annotated[Optional[datetime], Query(description="Only messages created after this time.")] = None,
) -> list[MessageResponse]:
    try:
        return messages.get_messages(user, course_id, student_id, after=after, access_token=token)
    except Exception as exc:
        _handle(exc)


@router.post(
    "/courses/{course_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
    description="Students message their course teacher; teachers message an enrolled student (`student_id`).",
    responses=ERROR_RESPONSES,
)
def send_message(
    course_id: UUID, body: MessageCreate, user: AnyUser, token: AccessToken, messages: Messages
) -> MessageResponse:
    try:
        return messages.send(user, course_id, body.body, body.student_id, access_token=token)
    except Exception as exc:
        _handle(exc)


@router.post(
    "/courses/{course_id}/messages/read",
    response_model=MarkReadResponse,
    summary="Mark a conversation as read",
    description="Marks the messages the caller received in this conversation as read.",
    responses=ERROR_RESPONSES,
)
def mark_read(
    course_id: UUID, body: MarkReadRequest, user: AnyUser, token: AccessToken, messages: Messages
) -> MarkReadResponse:
    try:
        return MarkReadResponse(
            updated=messages.mark_read(user, course_id, body.student_id, access_token=token)
        )
    except Exception as exc:
        _handle(exc)
