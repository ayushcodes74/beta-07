"""Current-user profile endpoints (Module 1).

Both routes act only on the user identified by the verified access token;
there is no way to address another user's profile here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.endpoints.auth import AUTH_ERROR_RESPONSES
from app.core.dependencies import (
    api_error,
    get_bearer_token,
    get_user_service,
    profile_error_to_http,
    require_authenticated_user,
)
from app.schemas.auth import ErrorResponse
from app.schemas.user import ProfileUpdate, UserProfileResponse
from app.services.auth_service import CurrentUser
from app.services.user_service import (
    DisabledAccountError,
    EmptyProfileUpdateError,
    InvalidRoleError,
    ProfileNotFoundError,
    ProfileRepositoryError,
    UserService,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get my profile",
    description=(
        "Returns the caller's own profile.\n\n"
        "**Authentication:** `Authorization: Bearer <Supabase access token>`.\n\n"
        "Integration pending: only the fields confirmed so far (id, email, role) are returned; "
        "more profile fields will be added once the database contract is confirmed."
    ),
    responses=AUTH_ERROR_RESPONSES,
)
def read_my_profile(
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
) -> UserProfileResponse:
    # The profile (and role) was already loaded while authenticating the caller.
    return UserProfileResponse(id=user.id, email=user.email, role=user.role)


@router.patch(
    "/me",
    response_model=UserProfileResponse,
    summary="Update my profile",
    description=(
        "Updates permitted fields on the caller's own profile.\n\n"
        "**Authentication:** `Authorization: Bearer <Supabase access token>`.\n\n"
        "`id`, `role`, `email` and any field not in the request schema are rejected with 422. "
        "Integration pending: no editable fields are confirmed yet, so every update is "
        "currently rejected."
    ),
    responses={
        **AUTH_ERROR_RESPONSES,
        422: {"description": "Unknown, protected or invalid fields, or an empty update."},
    },
)
def update_my_profile(
    payload: ProfileUpdate,
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
    token: Annotated[str, Depends(get_bearer_token)],
    users: Annotated[UserService, Depends(get_user_service)],
) -> UserProfileResponse:
    try:
        profile = users.update_profile(user.id, payload, access_token=token)
    except EmptyProfileUpdateError:
        raise api_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "empty_update", "No updatable fields were provided."
        ) from None
    except (ProfileNotFoundError, DisabledAccountError, InvalidRoleError, ProfileRepositoryError) as exc:
        raise profile_error_to_http(exc) from None
    return UserProfileResponse(id=profile.user_id, email=user.email, role=profile.role)
