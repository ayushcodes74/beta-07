"""Assignment request/response schemas (Module 2).

Teacher-facing and student-facing views are separate models. Student views are
built from an explicit allow-list of fields, so correct MCQ answers and
expected answers can never reach a student response.

API-level limits (lengths, counts, 2 decimal places for marks) are backend
validation choices; align them with the database contract once confirmed.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

MAX_TOTAL_MARKS = Decimal("10000")
MAX_QUESTIONS = 200
MAX_MCQ_OPTIONS = 10

# Marks are exact decimals (no float rounding when summing), up to 2 decimal
# places, and are serialised as JSON numbers.
Marks = Annotated[
    Decimal,
    Field(gt=0, le=MAX_TOTAL_MARKS, max_digits=7, decimal_places=2, examples=[10]),
    PlainSerializer(float, return_type=float, when_used="json"),
]

NonBlankText = Annotated[str, Field(min_length=1)]


class AssignmentStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------
# Questions (full, teacher-side representation)
# --------------------------------------------------------------------------


class McqOption(_StrictModel):
    id: Annotated[str, Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$", examples=["A"])]
    text: Annotated[NonBlankText, Field(max_length=1000)]


class McqQuestion(_StrictModel):
    type: Literal["mcq"]
    text: Annotated[NonBlankText, Field(max_length=5000)]
    marks: Marks
    options: Annotated[list[McqOption], Field(min_length=2, max_length=MAX_MCQ_OPTIONS)]
    correct_option_id: Annotated[str, Field(min_length=1, description="Teacher/grading only.")]

    @model_validator(mode="after")
    def _check_options(self) -> "McqQuestion":
        ids = [option.id for option in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("MCQ option ids must be unique")
        texts = [option.text.casefold() for option in self.options]
        if len(set(texts)) != len(texts):
            raise ValueError("MCQ option texts must be unique")
        if self.correct_option_id not in ids:
            raise ValueError("correct_option_id must match one of the option ids")
        return self


class SubjectiveQuestion(_StrictModel):
    type: Literal["subjective"]
    text: Annotated[NonBlankText, Field(max_length=5000)]
    marks: Marks
    instructions: Annotated[str | None, Field(max_length=5000)] = None
    expected_answer: Annotated[
        str | None, Field(max_length=20000, description="Teacher/grading only.")
    ] = None


Question = Annotated[McqQuestion | SubjectiveQuestion, Field(discriminator="type")]


def _to_utc(value: datetime) -> datetime:
    # Same instant, normalised to UTC; the deadline itself is never shifted.
    return value.astimezone(UTC)


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------


class AssignmentContent(_StrictModel):
    """The teacher-editable content of an assignment, validated as a whole."""

    title: Annotated[NonBlankText, Field(max_length=200)]
    instructions: Annotated[str | None, Field(max_length=20000)] = None
    due_at: AwareDatetime = Field(
        description="Deadline as an ISO 8601 timestamp with a timezone offset; stored and returned in UTC."
    )
    total_marks: Marks
    questions: Annotated[list[Question], Field(max_length=MAX_QUESTIONS)] = []

    @field_validator("due_at")
    @classmethod
    def _normalise_due_at(cls, value: datetime) -> datetime:
        return _to_utc(value)

    @model_validator(mode="after")
    def _check_marks(self) -> "AssignmentContent":
        question_total = sum((question.marks for question in self.questions), Decimal(0))
        if question_total > self.total_marks:
            raise ValueError(
                f"total question marks ({question_total}) exceed the assignment total marks ({self.total_marks})"
            )
        return self


class AssignmentCreate(AssignmentContent):
    """New assignments are always created as drafts; status cannot be set here."""

    course_id: UUID | None = Field(
        default=None,
        description="Optional course owned by the teacher creating this assignment.",
    )


class AssignmentUpdate(_StrictModel):
    """Partial update. The merged result is re-validated as a whole assignment.

    ``questions``, when given, replaces the full question list.
    """

    title: Annotated[NonBlankText, Field(max_length=200)] | None = None
    instructions: Annotated[str | None, Field(max_length=20000)] = None
    due_at: AwareDatetime | None = None
    total_marks: Marks | None = None
    questions: Annotated[list[Question], Field(max_length=MAX_QUESTIONS)] | None = None

    @model_validator(mode="after")
    def _reject_null_required_fields(self) -> "AssignmentUpdate":
        for name in ("title", "due_at", "total_marks", "questions"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    @field_validator("due_at")
    @classmethod
    def _normalise_due_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _to_utc(value)


# --------------------------------------------------------------------------
# Teacher-facing responses (include answers)
# --------------------------------------------------------------------------


class McqQuestionTeacherView(McqQuestion):
    position: int = Field(description="1-based position within the assignment.")


class SubjectiveQuestionTeacherView(SubjectiveQuestion):
    position: int = Field(description="1-based position within the assignment.")


class AssignmentTeacherResponse(BaseModel):
    id: UUID
    teacher_id: UUID
    course_id: UUID | None = None
    status: AssignmentStatus
    title: str
    instructions: str | None
    due_at: AwareDatetime
    total_marks: Marks
    questions: list[
        Annotated[McqQuestionTeacherView | SubjectiveQuestionTeacherView, Field(discriminator="type")]
    ]


# --------------------------------------------------------------------------
# Student-facing responses (never include answers)
# --------------------------------------------------------------------------


class McqOptionStudentView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str


class McqQuestionStudentView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int
    type: Literal["mcq"] = "mcq"
    text: str
    marks: Marks
    options: list[McqOptionStudentView]


class SubjectiveQuestionStudentView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int
    type: Literal["subjective"] = "subjective"
    text: str
    marks: Marks
    instructions: str | None


class AssignmentStudentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    course_id: UUID | None = None
    title: str
    instructions: str | None
    due_at: AwareDatetime
    total_marks: Marks
    questions: list[
        Annotated[McqQuestionStudentView | SubjectiveQuestionStudentView, Field(discriminator="type")]
    ]
