"""User profile retrieval, updates and trusted role resolution (Module 1).

The role always comes from the trusted ``profiles`` record via a
``ProfileRepository``. It is never taken from the request body, query string,
the token's ``user_metadata`` or registration metadata.

INTEGRATION PENDING: there is no concrete Supabase-backed repository yet. The
database developer still has to confirm the profile table name, columns, the
role values, the editable fields, and the RLS policies. Until then the app uses
``UnconfiguredProfileRepository``, so profile-dependent routes return 503 and
never serve fake data.

The intended implementation reads profiles with the caller's own access token
so that Supabase RLS applies. It must not use the service-role key for normal
user operations.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.schemas.user import ProfileUpdate, Role

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProfileRecord:
    """A profile as returned by the repository, before validation."""

    user_id: UUID
    role: str


@dataclass(frozen=True)
class UserProfile:
    """A validated profile with a recognised application role."""

    user_id: UUID
    role: Role


class ProfileRepositoryError(Exception):
    """The profile store failed or returned something unusable."""


class ProfileIntegrationNotConfiguredError(ProfileRepositoryError):
    """No confirmed profile integration is available yet."""


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


def get_profile_repository() -> ProfileRepository:
    # TODO(db-contract): return the Supabase-backed repository once the
    # profiles table, columns, role values and RLS policies are confirmed.
    return UnconfiguredProfileRepository()


class ProfileNotFoundError(Exception):
    """The authenticated user has no profile record."""


class InvalidRoleError(Exception):
    """The profile record holds a role TrustGrade does not recognise."""


class EmptyProfileUpdateError(Exception):
    """The update request contained no fields to change."""


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
        try:
            role = Role(record.role)
        except ValueError:
            logger.warning("User %s has an unrecognised role in their profile", user_id)
            raise InvalidRoleError from None
        return UserProfile(user_id=record.user_id, role=role)
