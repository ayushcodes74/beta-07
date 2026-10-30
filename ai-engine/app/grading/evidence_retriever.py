"""Evidence retrieval service for AI grading.

Retrieves course material strictly filtered by course_id to ground semantic
evaluations and detect when course evidence is insufficient.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.rag.context_builder import ContextBuilder
from app.rag.retriever import CourseMaterialRetriever
from app.schemas.common import SourceReference
from app.schemas.rag import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class EvidenceRetrievalResult:
    """Outcome of course evidence retrieval for grading."""

    course_context: str
    evidence_snippets: List[str]
    source_references: List[SourceReference]
    has_sufficient_evidence: bool
    retrieved_chunks: List[RetrievedChunk]


class GradingEvidenceRetriever:
    """Retrieves grounded course material for answering questions and evaluating student claims."""

    def __init__(
        self,
        retriever: Optional[CourseMaterialRetriever] = None,
        context_builder: Optional[ContextBuilder] = None,
        similarity_threshold: float = 0.15,
    ):
        """Initialize GradingEvidenceRetriever.

        Args:
            retriever: Course material retriever instance.
            context_builder: Context formatting helper.
            similarity_threshold: Minimum similarity score required for relevance.
        """
        self.retriever = retriever or CourseMaterialRetriever()
        self.context_builder = context_builder or ContextBuilder()
        self.similarity_threshold = similarity_threshold

    def retrieve_evidence_for_grading(
        self,
        course_id: str,
        question_text: str,
        student_answer: Optional[str] = None,
        top_k: int = 5,
    ) -> EvidenceRetrievalResult:
        """Retrieve course excerpts relevant to the question and student answer.

        Args:
            course_id: Target course ID ensuring isolation.
            question_text: The assignment question.
            student_answer: Optional student response to find supporting concepts.
            top_k: Maximum chunks to retrieve.

        Returns:
            EvidenceRetrievalResult containing formatted context, snippets, and references.
        """
        if not course_id:
            raise ValueError("course_id cannot be empty for evidence retrieval.")
        if not question_text:
            raise ValueError("question_text cannot be empty.")

        # Composite query targeting both the question and key student claims
        query = question_text
        if student_answer and len(student_answer.strip()) > 10:
            # Append concise excerpt of student answer
            query = f"{question_text} {student_answer[:200]}"

        # Retrieve strictly isolated to course_id
        retrieval_res = self.retriever.retrieve(
            query=query,
            course_id=course_id,
            top_k=top_k,
            similarity_threshold=self.similarity_threshold,
        )

        chunks = retrieval_res.chunks
        has_evidence = len(chunks) > 0

        if not has_evidence:
            logger.info("Insufficient course material retrieved for course '%s'", course_id)
            return EvidenceRetrievalResult(
                course_context="No relevant course material found in course documents.",
                evidence_snippets=[],
                source_references=[],
                has_sufficient_evidence=False,
                retrieved_chunks=[],
            )

        context_block = self.context_builder.build_context_block(chunks)
        snippets = self.context_builder.extract_snippets_for_prompts(chunks)
        source_refs = self.context_builder.to_source_references(chunks)

        return EvidenceRetrievalResult(
            course_context=context_block,
            evidence_snippets=snippets,
            source_references=source_refs,
            has_sufficient_evidence=True,
            retrieved_chunks=chunks,
        )

