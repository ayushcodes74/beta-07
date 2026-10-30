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
    """Fields a user may change on their own profile.

    INTEGRATION PENDING: no editable fields are confirmed yet, so every field is
    currently rejected. Add approved, non-sensitive fields here once the
    database developer confirms them. Never add ``id``, ``role``, ``email`` or
    other privileged account fields.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
