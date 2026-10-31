"""Authentication endpoints (Module 1).

Sign-up, login and logout are performed by the frontend directly against
Supabase Auth, so this backend deliberately exposes no register/login/logout
routes and never handles passwords or issues tokens. See
``app.services.auth_service`` for the full flow.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import require_authenticated_user
from app.schemas.auth import AuthenticatedUserResponse, ErrorResponse
from app.services.auth_service import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_ERROR_RESPONSES: dict[int | str, dict] = {
    401: {"model": ErrorResponse, "description": "Missing, malformed, expired or invalid access token."},
    403: {"model": ErrorResponse, "description": "No profile, disabled account, or the profile has an unrecognised role."},
    503: {"model": ErrorResponse, "description": "Token verification or profile lookup is unavailable."},
}


@router.get(
    "/me",
    response_model=AuthenticatedUserResponse,
    summary="Get the authenticated user",
    description=(
        "Returns the identity of the caller. The user id and email come from the verified "
        "Supabase access token; the role comes from the trusted profile record.\n\n"
        "**Authentication:** `Authorization: Bearer <Supabase access token>`.\n\n"
        "Sign-up, login and logout are done by the frontend directly with Supabase Auth; "
        "this API has no password or token-issuing endpoints. Logging out revokes the "
        "Supabase session's refresh tokens, but an already-issued access token stays "
        "valid until it expires."
    ),
    responses=AUTH_ERROR_RESPONSES,
)
def read_authenticated_user(
    user: Annotated[CurrentUser, Depends(require_authenticated_user)],
) -> AuthenticatedUserResponse:
    return AuthenticatedUserResponse(id=user.id, email=user.email, role=user.role, display_name=user.display_name)
