"""Text chunker for OCR extracted course documents.

Splits extracted documents into semantic, overlapping chunks while strictly
preserving document, page, section, and course metadata.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from typing import Any, Dict, List, Optional, Tuple
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

        # Sliding window with boundary awareness. Formula spans are computed once so no cut point
        # or overlap start ever lands inside $...$ / $$...$$.
        spans = self._latex_spans(clean_text, max_len=self.chunk_size)
        start = 0
        chunk_idx = 0
        total_len = len(clean_text)

        while start < total_len:
            end = min(start + self.chunk_size, total_len)

            # If not at the end of text, attempt to find a clean punctuation/newline boundary
            if end < total_len:
                boundary = self._find_natural_break(clean_text, start, end, spans)
                if boundary > start + self.min_chunk_size:
                    end = boundary
                span = self._span_containing(spans, end)
                if span is not None:
                    # Cut before the formula if that still leaves a real chunk, else after it.
                    end = span[0] if span[0] > start + self.min_chunk_size else span[1]

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
            span = self._span_containing(spans, next_start)
            if span is not None:
                # Start the overlap at the formula's opening "$" so it is never cut in half.
                next_start = span[0] if span[0] > start else span[1]
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
    def _latex_spans(text: str, max_len: Optional[int] = None) -> List[Tuple[int, int]]:
        """(open, close) index pairs of $...$ and $$...$$ formulas; close is just past the last "$".

        Escaped dollars (\\$) are ignored and an unclosed delimiter is treated as a stray "$" (e.g. a
        price), so it cannot make the rest of the document unsplittable. Spans longer than ``max_len``
        are dropped: they cannot fit in a chunk anyway, and are usually two unrelated "$" signs.
        """
        spans: List[Tuple[int, int]] = []
        i, n = 0, len(text)
        while i < n:
            if text[i] != "$" or (i > 0 and text[i - 1] == "\\"):
                i += 1
                continue
            delim = "$$" if text.startswith("$$", i) else "$"
            search = i + len(delim)
            while True:
                close = text.find(delim, search)
                if close == -1 or text[close - 1] != "\\":
                    break
                search = close + 1
            if close == -1:
                i += len(delim)
                continue
            span_end = close + len(delim)
            if max_len is None or span_end - i <= max_len:
                spans.append((i, span_end))
            i = span_end
        return spans

    @staticmethod
    def _span_containing(spans: List[Tuple[int, int]], pos: int) -> Optional[Tuple[int, int]]:
        """The formula span strictly containing ``pos`` (a cut at pos would split it), if any."""
        idx = bisect_right(spans, (pos, float("inf"))) - 1
        if idx >= 0 and spans[idx][0] < pos < spans[idx][1]:
            return spans[idx]
        return None

    @classmethod
    def _is_inside_latex(cls, text: str, pos: int) -> bool:
        """Check if index pos is inside an inline or block LaTeX formula ($...$ or $$...$$)."""
        return cls._span_containing(cls._latex_spans(text), pos) is not None

    @classmethod
    def _find_natural_break(
        cls, text: str, start: int, end: int, spans: Optional[List[Tuple[int, int]]] = None
    ) -> int:
        """Find the last natural break point (paragraph, sentence, or word) before end.

        Every occurrence in the second half of the window is tried, right to left, so a separator
        inside a formula (e.g. "; " in "$x = 1; y = 2$") falls back to the previous one instead of
        giving up. Returns ``end`` when no safe break exists.
        """
        if spans is None:
            spans = cls._latex_spans(text)
        sub = text[start:end]
        floor = len(sub) * 0.5

        def last_safe(sep: str) -> Optional[int]:
            idx = sub.rfind(sep)
            while idx != -1 and idx > floor:
                cand = start + idx + len(sep)
                if cls._span_containing(spans, cand) is None:
                    return cand
                idx = sub.rfind(sep, 0, idx)
            return None

        for sep in ["\n\n", ". ", "? ", "! ", ".\n", "; ", " "]:
            cand = last_safe(sep)
            if cand is not None:
                return cand
        return end

    @staticmethod
    def _generate_chunk_id(document_id: str, page_number: Optional[int], chunk_idx: int) -> str:
        """Create a deterministic unique chunk ID."""
        clean_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", document_id)
        p_str = f"p{page_number}" if page_number is not None else "p0"
        return f"{clean_doc_id}_{p_str}_c{chunk_idx}"
