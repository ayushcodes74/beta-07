"""User profile retrieval, updates, and trusted role resolution (Module 1).

Profile operations use the authenticated user's Supabase access token so that
Supabase Row-Level Security (RLS) policies apply to all normal user operations.
The service-role key is never used for normal user profile operations.

The user's role comes exclusively from the trusted ``profiles`` table, never from
the request body, query string, token ``user_metadata``, or client input.

Disabled accounts (``is_disabled=True``) are rejected immediately during profile
validation before any valid ``UserProfile`` or authenticated identity is returned.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import logging
from typing import Any, Protocol
from uuid import UUID

from app.database.supabase import get_user_supabase
from app.schemas.user import ProfileUpdate, Role

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProfileRecord:
    """A profile as returned by the repository, before validation."""

    user_id: UUID
    role: str
    is_disabled: bool


@dataclass(frozen=True)
class UserProfile:
    """A validated profile with a recognised application role."""

    user_id: UUID
    role: Role


class ProfileRepositoryError(Exception):
    """The profile store failed or returned something unusable."""


class ProfileIntegrationNotConfiguredError(ProfileRepositoryError):
    """No confirmed profile integration is available yet."""


class ProfileNotFoundError(Exception):
    """The authenticated user has no profile record."""


class InvalidRoleError(Exception):
    """The profile record holds a role TrustGrade does not recognise."""


class DisabledAccountError(Exception):
    """The authenticated user's account has been disabled."""


class EmptyProfileUpdateError(Exception):
    """The update request contained no fields to change."""


class ProfileRepository(Protocol):
    """Access to the trusted profile record of the *calling* user.

    ``access_token`` is the caller's verified Supabase access token, so
    implementations can query under the user's RLS context.
    """

    def get_profile(self, user_id: UUID, *, access_token: str) -> ProfileRecord | None: ...

    def update_profile(
        self, user_id: UUID, changes: Mapping[str, Any], *, access_token: str
    ) -> ProfileRecord | None: ...


class UnconfiguredProfileRepository:
    """Placeholder until the database developer confirms the profile contract."""

    def get_profile(self, user_id: UUID, *, access_token: str) -> ProfileRecord | None:
        raise ProfileIntegrationNotConfiguredError("profile repository is not configured")

    def update_profile(
        self, user_id: UUID, changes: Mapping[str, Any], *, access_token: str
    ) -> ProfileRecord | None:
        raise ProfileIntegrationNotConfiguredError("profile repository is not configured")


class SupabaseProfileRepository:
    """Supabase implementation using the authenticated user's JWT."""

    @staticmethod
    def _to_record(data: Any) -> ProfileRecord | None:
        if not data:
            return None

        if isinstance(data, list):
            if not data:
                return None
            data = data[0]

        if not isinstance(data, Mapping):
            raise ProfileRepositoryError("Invalid profile response")

        try:
            if "is_disabled" not in data:
                raise ProfileRepositoryError("Missing is_disabled field in profile")

            is_disabled = data["is_disabled"]
            if not isinstance(is_disabled, bool):
                raise ProfileRepositoryError("is_disabled must be a boolean")

            return ProfileRecord(
                user_id=UUID(str(data["id"])),
                role=str(data["role"]),
                is_disabled=is_disabled,
            )
        except ProfileRepositoryError:
            raise
        except (KeyError, ValueError, TypeError):
            raise ProfileRepositoryError("Invalid profile data") from None

    def get_profile(
        self, user_id: UUID, *, access_token: str
    ) -> ProfileRecord | None:
        try:
            client = get_user_supabase(access_token)

            response = (
                client.table("profiles")
                .select("id, role, is_disabled")
                .eq("id", str(user_id))
                .execute()
            )

            return self._to_record(response.data)

        except ProfileRepositoryError:
            raise
        except Exception:
            logger.exception("Supabase profile lookup failed")
            raise ProfileRepositoryError("Profile lookup failed") from None

    def update_profile(
        self,
        user_id: UUID,
        changes: Mapping[str, Any],
        *,
        access_token: str,
    ) -> ProfileRecord | None:
        try:
            client = get_user_supabase(access_token)

            response = (
                client.table("profiles")
                .update(dict(changes))
                .eq("id", str(user_id))
                .select("id, role, is_disabled")
                .execute()
            )

            return self._to_record(response.data)

        except ProfileRepositoryError:
            raise
        except Exception:
            logger.exception("Supabase profile update failed")
            raise ProfileRepositoryError("Profile update failed") from None


def get_profile_repository() -> ProfileRepository:
    return SupabaseProfileRepository()


class UserService:
    def __init__(self, repository: ProfileRepository) -> None:
        self._repository = repository

    def get_profile(self, user_id: UUID, *, access_token: str) -> UserProfile:
        record = self._repository.get_profile(user_id, access_token=access_token)
        return self._validate(user_id, record)

    def update_profile(self, user_id: UUID, update: ProfileUpdate, *, access_token: str) -> UserProfile:
        # The target user is always the verified token subject; the payload
        # schema forbids id/role/email and any other unapproved field.
        changes = update.model_dump(exclude_unset=True)
        if not changes:
            raise EmptyProfileUpdateError
        record = self._repository.update_profile(user_id, changes, access_token=access_token)
        return self._validate(user_id, record)

    @staticmethod
    def _validate(user_id: UUID, record: ProfileRecord | None) -> UserProfile:
        if record is None:
            raise ProfileNotFoundError
        if record.user_id != user_id:
            # Defence in depth: never hand back somebody else's profile.
            logger.error("Profile repository returned a record for a different user")
            raise ProfileRepositoryError("profile/user mismatch")
        if record.is_disabled:
            logger.warning("Rejected disabled user %s", user_id)
            raise DisabledAccountError
        try:
            role = Role(record.role)
        except ValueError:
            logger.warning("User %s has an unrecognised role in their profile", user_id)
            raise InvalidRoleError from None
        return UserProfile(user_id=record.user_id, role=role)
