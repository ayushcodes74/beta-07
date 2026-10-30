"""Context builder for LLM grounding.

Transforms retrieved chunks into formatted, token-budgeted context blocks
while preserving citations, page numbers, and boundary markers.
"""

from __future__ import annotations

from typing import List, Optional
from app.schemas.common import SourceReference
from app.schemas.rag import RetrievedChunk


class ContextBuilder:
    """Formats retrieved chunks into grounded LLM context with citation headers."""

    def __init__(self, max_characters: int = 4000):
        """Initialize ContextBuilder.

        Args:
            max_characters: Maximum cumulative characters allowed in the context block.
        """
        self.max_characters = max_characters

    def format_chunk(self, chunk: RetrievedChunk, index: int) -> str:
        """Format an individual chunk with full metadata citation header."""
        doc_label = chunk.title or chunk.document_id
        page_str = f", Page {chunk.page_number}" if chunk.page_number is not None else ""
        section_str = f", Section: '{chunk.section}'" if chunk.section else ""
        score_str = f" [Relevance: {chunk.similarity_score:.2f}]"

        header = f"[Source {index}: {doc_label}{page_str}{section_str}]{score_str}"
        return f"{header}\n\"{chunk.text}\""

    def build_context_block(
        self,
        chunks: List[RetrievedChunk],
        max_characters: Optional[int] = None,
    ) -> str:
        """Construct a complete grounded context block from retrieved chunks.

        Enforces character budget to avoid exceeding LLM context limits and
        clearly labels the text as verified course evidence.

        Args:
            chunks: List of RetrievedChunk objects sorted by relevance.
            max_characters: Optional character limit override.

        Returns:
            Formatted string of course evidence.
        """
        if not chunks:
            return "No verified course materials retrieved."

        budget = max_characters or self.max_characters
        formatted_pieces: List[str] = []
        current_len = 0

        for idx, chunk in enumerate(chunks, start=1):
            formatted = self.format_chunk(chunk, index=idx)
            piece_len = len(formatted) + 2  # including newline separator

            if current_len + piece_len > budget:
                # If budget exceeded, stop including additional chunks
                break

            formatted_pieces.append(formatted)
            current_len += piece_len

        if not formatted_pieces:
            # If the very first chunk exceeded the budget, truncate it cleanly
            first_chunk = self.format_chunk(chunks[0], index=1)
            return first_chunk[:budget] + " ... [Truncated]"

        return "\n\n".join(formatted_pieces)

    @staticmethod
    def extract_snippets_for_prompts(chunks: List[RetrievedChunk]) -> List[str]:
        """Convert chunks into a list of formatted citation snippets for prompt builders."""
        snippets: List[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            doc_label = chunk.title or chunk.document_id
            page_info = f" (p. {chunk.page_number})" if chunk.page_number else ""
            snippets.append(f"{chunk.text} [Ref: {doc_label}{page_info}]")
        return snippets

    @staticmethod
    def to_source_references(chunks: List[RetrievedChunk]) -> List[SourceReference]:
        """Convert a list of RetrievedChunk objects to SourceReference schemas."""
        return [c.to_source_reference() for c in chunks]

