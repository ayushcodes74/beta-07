"""Request/response models for AI-assisted assignment drafting (POST /assignments/generate-ai).

Generated questions are suggestions for the teacher's editor only. Nothing is stored
until the teacher saves the assignment through the normal create endpoint.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_GENERATED_QUESTIONS = 10


class AssignmentGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: Annotated[str, Field(min_length=3, max_length=300, examples=["Newton's laws of motion"])]
    instructions: Annotated[str | None, Field(default=None, max_length=2000)] = None
    question_count: Annotated[int, Field(ge=1, le=MAX_GENERATED_QUESTIONS)] = 3
    question_format: Literal["mixed", "subjective", "mcq"] = "mixed"
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"
    total_marks: Annotated[int, Field(ge=1, le=10000)] = 20

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
        description="False while course-material upload is unavailable; questions come from the topic alone."
    )
