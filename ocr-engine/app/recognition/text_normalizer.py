"""Safe text normalization service preserving original student transcripts."""

import re
from typing import List


class TextNormalizer:
    """Performs strictly safe whitespace normalization without altering grammar, vocabulary, or math notation."""

    # Matches multiple horizontal whitespace characters (spaces, tabs)
    _MULTI_SPACE_REGEX = re.compile(r"[^\S\r\n]+")
    # Matches more than two consecutive newlines
    _MULTI_NEWLINE_REGEX = re.compile(r"\n{3,}")

    @classmethod
    def normalize_block_text(cls, text: str) -> str:
        """Safely normalize whitespace within an extracted text block.

        Preserves:
        - Student grammar, typos, and phrasing as-is.
        - All punctuation marks and casing.
        - Mathematical notation and symbols.

        Args:
            text: Raw OCR transcript string.

        Returns:
            Normalized string.
        """
        if not text:
            return ""

        # Collapse multiple spaces or tabs into a single space
        cleaned = cls._MULTI_SPACE_REGEX.sub(" ", text)

        # Collapse excessive newlines within a block
        cleaned = cls._MULTI_NEWLINE_REGEX.sub("\n\n", cleaned)

        # Strip block-level edges
        return cleaned.strip()

    @classmethod
    def assemble_full_text(cls, block_texts: List[str]) -> str:
        """Combine ordered text block strings into full document text with clean line breaks."""
        non_empty = [b for b in block_texts if b.strip()]
        return "\n".join(non_empty)

