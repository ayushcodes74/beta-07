"""Syllabus detection and coverage verification service.

Determines whether a question is within the supplied course syllabus strictly
using retrieved course documents and syllabus text, never external LLM assumptions.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.llm.gemini_client import GeminiClient, get_gemini_client
from app.llm import prompts
from app.rag.context_builder import ContextBuilder
from app.rag.retriever import CourseMaterialRetriever
from app.schemas.assignment import SyllabusCoverageResult, SyllabusCoverageStatus
from app.schemas.common import SourceReference
from app.schemas.rag import RetrievedChunk

logger = logging.getLogger(__name__)


class SyllabusDetector:
    """Service to evaluate question syllabus alignment."""

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        retriever: Optional[CourseMaterialRetriever] = None,
    ):
        """Initialize the SyllabusDetector.

        Args:
            gemini_client: Gemini API client instance.
            retriever: Course material retriever for pulling course evidence.
        """
        self.gemini_client = gemini_client or get_gemini_client()
        self.retriever = retriever

    def detect_coverage(
        self,
        question: str,
        course_id: str,
        retrieved_evidence: Optional[List[RetrievedChunk]] = None,
        syllabus_text: Optional[str] = None,
    ) -> SyllabusCoverageResult:
        """Determine whether a question falls within the course syllabus.

        Args:
            question: Question text to evaluate.
            course_id: Course identifier.
            retrieved_evidence: Optional pre-retrieved course chunks.
            syllabus_text: Optional explicit syllabus outline.

        Returns:
            SyllabusCoverageResult with classification, concepts, and citations.
        """
        clean_question = question.strip() if question else ""
        if not clean_question:
            raise ValueError("Question cannot be empty for syllabus detection.")

        # 1. Retrieve evidence if not provided
        chunks = retrieved_evidence
        if chunks is None and self.retriever is not None:
            retrieval_res = self.retriever.retrieve(
                query=clean_question,
                course_id=course_id,
                top_k=5,
                similarity_threshold=0.1,
            )
            chunks = retrieval_res.chunks

        chunks = chunks or []

        # 2. Check for complete lack of evidence/syllabus context
        has_syllabus = bool(syllabus_text and syllabus_text.strip())
        if not chunks and not has_syllabus:
            logger.info("No course evidence or syllabus supplied for '%s'; returning UNCERTAIN.", course_id)
            return SyllabusCoverageResult(
                status=SyllabusCoverageStatus.UNCERTAIN,
                confidence=0.0,
                covered_concepts=[],
                uncovered_concepts=["All required concepts (insufficient evidence)"],
                reasoning=(
                    f"Insufficient evidence: No course material or syllabus documents were found for course '{course_id}'. "
                    "Cannot verify syllabus coverage without authoritative course evidence."
                ),
                evidence=[],
            )

        # 3. Format evidence context
        evidence_context = ContextBuilder().build_context_block(chunks)
        combined_reference_text = ""
        if has_syllabus:
            combined_reference_text += f"### FORMAL SYLLABUS OUTLINE:\n{syllabus_text.strip()}\n\n"
        if chunks:
            combined_reference_text += f"### RETRIEVED COURSE EXCERPTS:\n{evidence_context}"

        prompt = prompts.build_syllabus_prompt(
            question=clean_question,
            syllabus_content=combined_reference_text,
        )

        # 4. Generate structured classification
        result = self.gemini_client.generate_structured(
            prompt=prompt,
            response_schema=SyllabusCoverageResult,
            system_instruction=prompts.SYSTEM_SYLLABUS_ANALYST,
        )

        # 5. Attach structured source references
        source_refs = ContextBuilder.to_source_references(chunks)
        if source_refs and not result.evidence:
            result.evidence = source_refs

        return result
