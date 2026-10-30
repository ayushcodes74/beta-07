"""Pydantic schemas package."""

from app.schemas.common import (
    BaseSchema,
    SourceReference,
    ConfidenceScore,
    ReviewReasonCategory,
    ReviewStatus,
    ErrorDetail,
)
from app.schemas.rag import (
    DocumentChunk,
    RetrievedChunk,
    RetrievalRequest,
    RetrievalResult,
)
from app.schemas.assignment import (
    SyllabusCoverageStatus,
    QuestionType,
    DifficultyLevel,
    SyllabusCoverageResult,
    MCQOption,
    RubricCriterion,
    Rubric,
    ModelAnswer,
    QuestionDraft,
    AssignmentDraft,
    AssignmentGenerationRequest,
)
from app.schemas.grading import (
    GradingStatus,
    GradingRequest,
    CriterionEvaluation,
    QuestionGrade,
    GradingResult,
)

__all__ = [
    "BaseSchema",
    "SourceReference",
    "ConfidenceScore",
    "ReviewReasonCategory",
    "ReviewStatus",
    "ErrorDetail",
    "DocumentChunk",
    "RetrievedChunk",
    "RetrievalRequest",
    "RetrievalResult",
    "SyllabusCoverageStatus",
    "QuestionType",
    "DifficultyLevel",
    "SyllabusCoverageResult",
    "MCQOption",
    "RubricCriterion",
    "Rubric",
    "ModelAnswer",
    "QuestionDraft",
    "AssignmentDraft",
    "AssignmentGenerationRequest",
    "GradingStatus",
    "GradingRequest",
    "CriterionEvaluation",
    "QuestionGrade",
    "GradingResult",
]
