"""Authentication and authorization dependencies (Module 1).

Usage in other modules::

    @router.post("/courses", dependencies=[Depends(require_teacher)])
    def create_course(...): ...

    def view(user: CurrentUser = Depends(require_student)): ...

Status codes: 401 for missing/invalid credentials, 403 for authenticated users
without permission (or without a usable profile/role), 503 when the auth or
profile integration is unavailable or not configured.
"""

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.security import (
    SigningKeyUnavailableError,
    TokenVerificationError,
    TokenVerifier,
    TokenVerifierNotConfiguredError,
    build_token_verifier,
)
from app.schemas.user import Role
from app.services.auth_service import AuthService, CurrentUser
from app.services.user_service import (
    InvalidRoleError,
    ProfileIntegrationNotConfiguredError,
    ProfileNotFoundError,
    ProfileRepository,
    ProfileRepositoryError,
    UserService,
    get_profile_repository,
)

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="SupabaseAccessToken",
    description="Supabase Auth access token obtained by the frontend after sign-in.",
)


def api_error(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> HTTPException:
    """Build an HTTPException with the structured ``{"code", "message"}`` detail."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message}, headers=headers)


def _unauthorized(code: str, message: str, bearer_error: str | None = None) -> HTTPException:
    challenge = f'Bearer error="{bearer_error}"' if bearer_error else "Bearer"
    return api_error(status.HTTP_401_UNAUTHORIZED, code, message, {"WWW-Authenticate": challenge})


def auth_unavailable() -> HTTPException:
    return api_error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "auth_unavailable",
        "Authentication is temporarily unavailable.",
    )


def profile_error_to_http(exc: Exception) -> HTTPException:
    """Map user-service/profile errors to safe HTTP errors."""
    if isinstance(exc, ProfileNotFoundError):
        return api_error(status.HTTP_403_FORBIDDEN, "profile_not_found", "No user profile exists for this account.")
    if isinstance(exc, InvalidRoleError):
        return api_error(status.HTTP_403_FORBIDDEN, "invalid_role", "This account does not have a valid role.")
    if isinstance(exc, ProfileIntegrationNotConfiguredError):
        logger.error("Profile integration is not configured yet")
    elif isinstance(exc, ProfileRepositoryError):
        logger.error("Profile repository failure: %s", type(exc).__name__)
    return api_error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "profile_service_unavailable",
        "User profiles are temporarily unavailable.",
    )


@lru_cache
def _configured_token_verifier() -> TokenVerifier:
    return build_token_verifier(settings)


def get_token_verifier() -> TokenVerifier:
    try:
        return _configured_token_verifier()
    except TokenVerifierNotConfiguredError as exc:
        # Log which settings are missing (names only, no values).
        logger.error("JWT verification is not configured: %s", exc)
        raise auth_unavailable() from None


def get_user_service(
    repository: Annotated[ProfileRepository, Depends(get_profile_repository)],
) -> UserService:
    return UserService(repository)


def get_auth_service(
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    users: Annotated[UserService, Depends(get_user_service)],
) -> AuthService:
    return AuthService(verifier, users)


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    """Return the raw bearer token, or 401 if the header is missing or not Bearer."""
    if credentials is None or not credentials.credentials:
        raise _unauthorized("not_authenticated", "Authentication credentials were not provided.")
    return credentials.credentials


def get_current_user(
    token: Annotated[str, Depends(get_bearer_token)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentUser:
    """Verify the caller's access token and resolve their trusted role."""
    try:
        return auth.authenticate(token)
    except TokenVerificationError as exc:
        # Reason is logged for diagnostics; the token itself is never logged.
        logger.info("Rejected access token: %s", exc)
        raise _unauthorized("invalid_token", "Invalid or expired access token.", "invalid_token") from None
    except SigningKeyUnavailableError:
        logger.error("Could not retrieve JWT signing keys")
        raise auth_unavailable() from None
    except (ProfileNotFoundError, InvalidRoleError, ProfileRepositoryError) as exc:
        raise profile_error_to_http(exc) from None


def require_authenticated_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Any authenticated user with a valid profile and role."""
    return user


def require_role(*allowed: Role) -> Callable[[CurrentUser], CurrentUser]:
    """Build a dependency that only admits users whose trusted role is in ``allowed``."""

    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role not in allowed:
            raise api_error(
                status.HTTP_403_FORBIDDEN, "forbidden", "You do not have permission to perform this action."
            )
        return user

    return dependency


require_teacher = require_role(Role.TEACHER)
require_student = require_role(Role.STUDENT)
