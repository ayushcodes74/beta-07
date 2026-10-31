"""Authentication of API callers (Module 1).

Agreed flow:

1. The frontend signs users up, logs them in and logs them out directly with
   Supabase Auth (supabase-js). FastAPI has no register/login/logout logic and
   never handles passwords or issues tokens.
2. The frontend sends the Supabase access token as ``Authorization: Bearer``.
3. FastAPI verifies the token (``app.core.security``) and resolves the user's
   role from the trusted profile record (``app.services.user_service``).

Logout: Supabase ``signOut()`` revokes the session's refresh tokens. Access
tokens already issued remain valid until their ``exp``; this backend does not
keep a revocation list.
"""

from dataclasses import dataclass
from uuid import UUID

from app.core.security import TokenVerifier
from app.schemas.user import Role
from app.services.user_service import UserService


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated caller: verified identity plus trusted role."""

    id: UUID
    email: str | None
    role: Role
    display_name: str | None = None


class AuthService:
    def __init__(self, verifier: TokenVerifier, users: UserService) -> None:
        self._verifier = verifier
        self._users = users

    def authenticate(self, access_token: str) -> CurrentUser:
        """Verify the token, then look up the caller's role.

        Raises the verification errors from ``app.core.security`` and the
        profile errors from ``app.services.user_service``.
        """
        claims = self._verifier.verify(access_token)
        profile = self._users.get_profile(claims.user_id, access_token=access_token)
        return CurrentUser(
            id=claims.user_id, email=claims.email, role=profile.role, display_name=profile.display_name
        )
