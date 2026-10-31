"""Course request and response schemas (Module 2A).

Follows existing database schema:
  courses:
    - id (UUID)
    - teacher_id (UUID)
    - name (TEXT)
    - description (TEXT)
    - created_at (TIMESTAMP)
  course_enrollments:
    - id (UUID)
    - course_id (UUID)
    - student_id (UUID)
    - status (TEXT: 'active' / 'inactive')
    - enrolled_at (TIMESTAMP)

Designed to map cleanly to the React frontend Course model.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class CourseCreate(_StrictModel):
    """Payload to create a course."""

    name: Annotated[str, Field(min_length=1, max_length=200, description="Course name")]
    description: Annotated[str | None, Field(default=None, max_length=2000, description="Course description")] = None


class CourseUpdate(_StrictModel):
    """Payload to partially update a course."""

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=200)] = None
    description: Annotated[str | None, Field(default=None, max_length=2000)] = None

    @model_validator(mode="after")
    def _reject_empty_update(self) -> "CourseUpdate":
        if self.name is None and self.description is None:
            raise ValueError("At least one field must be provided for update")
        return self


class CourseResponse(BaseModel):
    """Course view compatible with the frontend Course model."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    teacher_id: UUID
    name: str
    description: str | None = None
    created_at: AwareDatetime
    code: str = Field(default="", description="Course code for frontend display")
    instructor: str = Field(default="", description="Instructor display name")
    students: int = Field(default=0, description="Number of active enrolled students")
    assignments: int = Field(default=0, description="Number of assignments in this course")
    activity: int = Field(default=0, description="Course activity percentage")
    average: float = Field(default=0.0, description="Course grade average")

    @field_validator("created_at")
    @classmethod
    def _normalise_created_at(cls, value: datetime) -> datetime:
        return _to_utc(value)


class EnrollmentCreate(_StrictModel):
    """Payload to enroll a student in a course."""

    student_id: UUID = Field(..., description="UUID of the student to enroll")


class EnrollmentByEmailCreate(_StrictModel):
    """Payload to enroll a student by the email they sign in with."""

    email: EmailStr = Field(..., max_length=320, description="Student's sign-in email address")


class EnrollmentResponse(BaseModel):
    """Enrollment record view."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    course_id: UUID
    student_id: UUID
    status: str
    enrolled_at: AwareDatetime

    @field_validator("enrolled_at")
    @classmethod
    def _normalise_enrolled_at(cls, value: datetime) -> datetime:
        return _to_utc(value)


class CourseStudentResponse(BaseModel):
    """Student view for teacher's course roster."""

    model_config = ConfigDict(extra="ignore")

    student_id: UUID
    name: str | None = Field(default=None, description="Student display name")
    email: str | None = Field(default=None, description="Student email address")
    status: str = Field(default="active", description="Enrollment status")
    enrolled_at: AwareDatetime

    @field_validator("enrolled_at")
    @classmethod
    def _normalise_enrolled_at(cls, value: datetime) -> datetime:
        return _to_utc(value)

