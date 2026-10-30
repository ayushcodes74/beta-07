"""RAG and Knowledge Retrieval Pydantic schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import Field

from app.schemas.common import BaseSchema, SourceReference


class DocumentChunk(BaseSchema):
    """Represents a discrete semantic chunk of a course document."""

    chunk_id: str = Field(description="Unique deterministic or random chunk identifier.")
    course_id: str = Field(description="Course or subject scope identifier.")
    document_id: str = Field(description="Source document identifier provided by OCR teammate.")
    title: Optional[str] = Field(default=None, description="Document title or filename.")
    page_number: Optional[int] = Field(default=None, description="Source page number.")
    section: Optional[str] = Field(default=None, description="Chapter, topic, or section header.")
    text: str = Field(description="The textual content of the chunk.")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional metadata (e.g. OCR confidence, bounding boxes).",
    )
    embedding: Optional[List[float]] = Field(
        default=None,
        description="Dense vector embedding of the chunk text.",
    )


class RetrievedChunk(BaseSchema):
    """A document chunk retrieved via similarity search with matching metrics."""

    chunk_id: str = Field(description="Unique chunk identifier.")
    course_id: str = Field(description="Course identifier.")
    document_id: str = Field(description="Source document identifier.")
    title: Optional[str] = Field(default=None, description="Document title or filename.")
    page_number: Optional[int] = Field(default=None, description="Source page number.")
    section: Optional[str] = Field(default=None, description="Chapter or section heading.")
    text: str = Field(description="Retrieved chunk text.")
    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Cosine similarity score (0.0 to 1.0).",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Source metadata.",
    )

    def to_source_reference(self) -> SourceReference:
        """Convert to standard SourceReference for grading and evidence schemas."""
        return SourceReference(
            document_id=self.document_id,
            title=self.title,
            page_number=self.page_number,
            section=self.section,
            snippet=self.text,
            similarity_score=self.similarity_score,
        )


class RetrievalRequest(BaseSchema):
    """Request query payload for RAG retrieval."""

    query: str = Field(min_length=1, description="Search query, question, or student answer.")
    course_id: str = Field(min_length=1, description="Target course ID for scope isolation.")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of chunks to return.")
    similarity_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score required for inclusion.",
    )


class RetrievalResult(BaseSchema):
    """Result returned by the RAG retriever service."""

    query: str = Field(description="Original search query.")
    course_id: str = Field(description="Course scope identifier.")
    chunks: List[RetrievedChunk] = Field(
        default_factory=list,
        description="Retrieved matching chunks sorted by relevance descending.",
    )
    total_found: int = Field(
        default=0,
        description="Total number of chunks meeting threshold and course filter.",
    )

