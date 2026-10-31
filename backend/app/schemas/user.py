from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Role(StrEnum):
    """TrustGrade application roles.

    The role is only ever read from the trusted profile record, never from the
    request, the token's ``user_metadata`` or registration metadata.
    """

    TEACHER = "teacher"
    STUDENT = "student"


class UserProfileResponse(BaseModel):
    """The authenticated user's own profile.

    INTEGRATION PENDING: limited to fields confirmed so far (user id, trusted
    role, verified email). Add profile fields once the database developer
    confirms the ``profiles`` columns.
    """

    id: UUID = Field(description="Supabase Auth user id (verified token subject).")
    email: EmailStr | None = Field(description="Email from the verified access token, if present.")
    role: Role = Field(description="Role from the trusted profiles record.")


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    avatar_url: str | None = Field(
        default=None,
        max_length=2048,
    )