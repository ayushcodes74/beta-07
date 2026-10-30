"""Text chunker for OCR extracted course documents.

Splits extracted documents into semantic, overlapping chunks while strictly
preserving document, page, section, and course metadata.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from app.schemas.rag import DocumentChunk


class TextChunker:
    """Configurable sliding-window text chunker with sentence-aware boundaries."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        min_chunk_size: int = 20,
    ):
        """Initialize the chunker.

        Args:
            chunk_size: Target character length per chunk.
            chunk_overlap: Overlapping characters between consecutive chunks.
            min_chunk_size: Minimum characters required to form a chunk.

        Raises:
            ValueError: If chunk_overlap >= chunk_size or values are non-positive.
        """
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        if chunk_overlap < 0:
            raise ValueError(f"chunk_overlap cannot be negative, got {chunk_overlap}")
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk_text(
        self,
        text: str,
        course_id: str,
        document_id: str,
        title: Optional[str] = None,
        page_number: Optional[int] = None,
        section: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentChunk]:
        """Split text into overlapping chunks while preserving document metadata.

        Args:
            text: Raw extracted text (e.g. from OCR).
            course_id: Course/subject identifier.
            document_id: Unique document identifier.
            title: Optional document title.
            page_number: Optional page number.
            section: Optional section or chapter header.
            metadata: Optional additional metadata dict.

        Returns:
            List of DocumentChunk instances.
        """
        clean_text = text.strip() if text else ""
        if not clean_text:
            return []

        base_meta = dict(metadata or {})
        chunks: List[DocumentChunk] = []

        # Short text: return as single chunk
        if len(clean_text) <= self.chunk_size:
            chunk_id = self._generate_chunk_id(document_id, page_number, 0)
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    course_id=course_id,
                    document_id=document_id,
                    title=title,
                    page_number=page_number,
                    section=section,
                    text=clean_text,
                    metadata=base_meta,
                )
            )
            return chunks

        # Sliding window with boundary awareness
        step = self.chunk_size - self.chunk_overlap
        start = 0
        chunk_idx = 0
        total_len = len(clean_text)

        while start < total_len:
            end = min(start + self.chunk_size, total_len)

            # If not at the end of text, attempt to find a clean punctuation/newline boundary
            if end < total_len:
                boundary = self._find_natural_break(clean_text, start, end)
                if boundary > start + self.min_chunk_size:
                    end = boundary

            chunk_content = clean_text[start:end].strip()
            if len(chunk_content) >= self.min_chunk_size or not chunks:
                chunk_id = self._generate_chunk_id(document_id, page_number, chunk_idx)
                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        course_id=course_id,
                        document_id=document_id,
                        title=title,
                        page_number=page_number,
                        section=section,
                        text=chunk_content,
                        metadata=base_meta,
                    )
                )
                chunk_idx += 1

            if end >= total_len:
                break

            # Advance window ensuring consistent overlap from the actual end of current chunk
            next_start = end - self.chunk_overlap
            if next_start <= start:
                next_start = start + max(1, self.chunk_size - self.chunk_overlap)
            start = next_start

        return chunks

    def chunk_document_pages(
        self,
        pages: List[Dict[str, Any]],
        course_id: str,
        document_id: str,
        title: Optional[str] = None,
        default_section: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """Chunk a multi-page document received from the OCR teammate.

        Args:
            pages: List of dicts, each with 'text', 'page_number', and optional 'section'.
            course_id: Course identifier.
            document_id: Document identifier.
            title: Optional document title.
            default_section: Default section fallback if page has none.

        Returns:
            Aggregated list of DocumentChunks across all pages.
        """
        all_chunks: List[DocumentChunk] = []

        for p_idx, page in enumerate(pages):
            text = page.get("text", "")
            page_num = page.get("page_number", p_idx + 1)
            section = page.get("section", default_section)
            extra_meta = {k: v for k, v in page.items() if k not in ("text", "page_number", "section")}

            page_chunks = self.chunk_text(
                text=text,
                course_id=course_id,
                document_id=document_id,
                title=title,
                page_number=page_num,
                section=section,
                metadata=extra_meta,
            )
            all_chunks.extend(page_chunks)

        return all_chunks

    @staticmethod
    def _find_natural_break(text: str, start: int, end: int) -> int:
        """Find the last natural break point (paragraph, sentence, or word) before end."""
        sub = text[start:end]
        # Look for double newline
        p_idx = sub.rfind("\n\n")
        if p_idx != -1 and p_idx > len(sub) * 0.5:
            return start + p_idx + 2

        # Look for sentence end (.!?)
        for sep in [". ", "? ", "! ", ".\n", "; "]:
            s_idx = sub.rfind(sep)
            if s_idx != -1 and s_idx > len(sub) * 0.5:
                return start + s_idx + len(sep)

        # Look for space
        sp_idx = sub.rfind(" ")
        if sp_idx != -1 and sp_idx > len(sub) * 0.5:
            return start + sp_idx + 1

        return end

    @staticmethod
    def _generate_chunk_id(document_id: str, page_number: Optional[int], chunk_idx: int) -> str:
        """Create a deterministic unique chunk ID."""
        clean_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", document_id)
        p_str = f"p{page_number}" if page_number is not None else "p0"
        return f"{clean_doc_id}_{p_str}_c{chunk_idx}"
