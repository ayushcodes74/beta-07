from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import Role


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable, machine-readable error code.", examples=["invalid_token"])
    message: str = Field(description="Safe, human-readable message.", examples=["Invalid or expired access token."])


class ErrorResponse(BaseModel):
    """Shape of Module 1 error responses: ``{"detail": {"code": ..., "message": ...}}``."""

    detail: ErrorDetail


class AuthenticatedUserResponse(BaseModel):
    """Identity of the caller, resolved from a verified token and the trusted profile role."""

    id: UUID = Field(description="Supabase Auth user id (verified token subject).")
    email: EmailStr | None = Field(description="Email from the verified access token, if present.")
    role: Role = Field(description="Role from the trusted profiles record.")
