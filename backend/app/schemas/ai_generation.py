"""Request/response models for AI-assisted assignment drafting (POST /assignments/generate-ai).

Generated questions are suggestions for the teacher's editor only. Nothing is stored
until the teacher saves the assignment through the normal create endpoint.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.course_material_service import MAX_MATERIAL_CHARS

MAX_GENERATED_QUESTIONS = 10
# Syllabus / rulebook text. Keep in sync with MAX_SYLLABUS_CHARS in frontend/src/services/api.ts
# (the AI Engine accepts up to 60,000).
MAX_SYLLABUS_CHARS = 50_000


class AssignmentGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: Annotated[str, Field(min_length=3, max_length=300, examples=["Newton's laws of motion"])]
    instructions: Annotated[str | None, Field(default=None, max_length=2000)] = None
    question_count: Annotated[int, Field(ge=1, le=MAX_GENERATED_QUESTIONS)] = 3
    question_format: Literal["mixed", "subjective", "mcq"] = "mixed"
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"
    total_marks: Annotated[int, Field(ge=1, le=10000)] = 20
    # Course material attached in the editor (extracted file text and/or pasted notes). When
    # present, questions are grounded in it instead of the topic alone. Not stored.
    course_material: Annotated[str | None, Field(default=None, max_length=MAX_MATERIAL_CHARS)] = None
    # Syllabus and/or rulebook for this assignment (extracted file text and/or pasted). Binding for
    # the AI: questions stay within its scope and follow its rules. Not stored.
    syllabus: Annotated[str | None, Field(default=None, max_length=MAX_SYLLABUS_CHARS)] = None

    @model_validator(mode="after")
    def _enough_marks(self) -> "AssignmentGenerationRequest":
        if self.total_marks < self.question_count:
            raise ValueError("total_marks must be at least question_count (every question needs a whole mark)")
        return self


class GeneratedQuestion(BaseModel):
    type: Literal["mcq", "subjective"]
    text: str
    marks: int = Field(ge=1, description="Whole marks; the database stores integer marks.")
    expected_answer: str = Field(description="Model answer and marking guidance for the teacher to review.")
    options: list[str] | None = None
    correct_option_index: int | None = None


class GeneratedAssignmentDraft(BaseModel):
    title: str
    instructions: str | None = None
    questions: list[GeneratedQuestion]
    grounded_in_course_materials: bool = Field(
        description="True when course material was attached to the request; otherwise questions come from the topic alone."
    )


class ExtractedCourseMaterial(BaseModel):
    """Text extracted from a course-material file attached in the assignment editor (not stored)."""

    filename: str
    text: str
    characters: int
    truncated: bool = Field(description=f"True if the text was cut to {MAX_MATERIAL_CHARS:,} characters.")
    pages: int | None = Field(default=None, description="PDF pages or PPTX slides, when known.")
