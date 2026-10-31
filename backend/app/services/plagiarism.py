"""Conservative, OCR-aware local passage matching for authorized submissions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Sequence
from uuid import UUID

from app.schemas.integrity import (
    IntegrityEvidence,
    OCRQualitySummary,
    OCRRegionReference,
)
from app.schemas.ocr import OCRDocumentResult, PageResult

MIN_PASSAGE_TOKENS = 8
MIN_PASSAGE_SIMILARITY = 0.8
LOW_OCR_CONFIDENCE = 0.65
_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
_GENERIC_PATTERNS = (
    ("is defined as", "can be defined as", "refers to", "is the process by which", "is a process by which"),
    ("in conclusion", "in this essay", "as mentioned above", "the main idea is"),
)
_GENERIC_WORDS = frozenset(
    "a an as above and are be by can conclusion defined essay is it main mentioned of the this to which"
    " process refers idea".split()
)


@dataclass(frozen=True)
class _Token:
    normalized: str
    start: int
    end: int


@dataclass(frozen=True)
class _PageText:
    page_number: int
    text: str
    tokens: list[_Token]
    region_spans: list[tuple[int, int, OCRRegionReference]]
    unreadable: bool


def _tokens(text: str) -> list[_Token]:
    return [
        _Token(
            normalized=unicodedata.normalize("NFKC", match.group()).casefold(),
            start=match.start(),
            end=match.end(),
        )
        for match in _TOKEN_PATTERN.finditer(text)
    ]


def _page_text(page: PageResult) -> _PageText:
    blocks = sorted(page.text_blocks, key=lambda block: block.sequence)
    nonempty_blocks = [
        block for block in blocks if block.text.strip() and block.type.casefold() != "printed"
    ]
    if nonempty_blocks:
        text = "\n".join(block.text for block in nonempty_blocks)
        region_spans: list[tuple[int, int, OCRRegionReference]] = []
        cursor = 0
        for block in nonempty_blocks:
            reference = OCRRegionReference(
                page_number=page.page_number,
                region_id=block.block_id,
                bounding_box=block.bounding_box,
                confidence=block.confidence,
                original_text=block.text,
            )
            region_spans.append((cursor, cursor + len(block.text), reference))
            cursor += len(block.text) + 1
    elif not blocks:
        text = page.full_text
        region_spans = []
    else:
        text = ""
        region_spans = []

    return _PageText(
        page_number=page.page_number,
        text=text,
        tokens=_tokens(text),
        region_spans=region_spans,
        unreadable=page.status in {"failed", "unreadable", "degraded"}
        or any("unreadable" in warning.casefold() for warning in page.warnings),
    )


def _quality_summary(document: OCRDocumentResult, pages: Sequence[_PageText]) -> OCRQualitySummary:
    confidences: list[float] = []
    low_confidence: list[OCRRegionReference] = []
    for page in document.pages:
        for block in page.text_blocks:
            if block.confidence is not None:
                confidences.append(block.confidence)
            if block.confidence is None or block.confidence < LOW_OCR_CONFIDENCE:
                low_confidence.append(
                    OCRRegionReference(
                        page_number=page.page_number,
                        region_id=block.block_id,
                        bounding_box=block.bounding_box,
                        confidence=block.confidence,
                        original_text=block.text,
                    )
                )

    expected_pages = set(range(1, document.processing_summary.total_pages + 1))
    available_pages = {page.page_number for page in document.pages}
    return OCRQualitySummary(
        mean_confidence=sum(confidences) / len(confidences) if confidences else None,
        low_confidence_regions=low_confidence,
        unreadable_pages=sorted(page.page_number for page in pages if page.unreadable),
        missing_pages=sorted(expected_pages - available_pages),
    )


def _region_refs(page: _PageText, start: int, end: int) -> list[OCRRegionReference]:
    return [
        region
        for region_start, region_end, region in page.region_spans
        if region_start < end and region_end > start
    ]


def _generic_context(tokens: Sequence[_Token]) -> tuple[bool, bool]:
    normalized = " ".join(token.normalized for token in tokens)
    definition_style = any(phrase in normalized for phrase in _GENERIC_PATTERNS[0])
    boilerplate_style = any(phrase in normalized for phrase in _GENERIC_PATTERNS[1])
    informative_words = {token.normalized for token in tokens} - _GENERIC_WORDS
    generic = (definition_style or boilerplate_style) and len(informative_words) <= 3
    note = definition_style or boilerplate_style
    return generic, note


def _candidate_spans(
    current_tokens: Sequence[_Token], source_tokens: Sequence[_Token]
) -> list[tuple[int, int, int, int, float]]:
    current_words = [token.normalized for token in current_tokens]
    source_words = [token.normalized for token in source_tokens]
    matcher = SequenceMatcher(None, current_words, source_words, autojunk=False)
    matching = [block for block in matcher.get_matching_blocks() if block.size]
    merged: list[list[int]] = []
    for block in matching:
        if merged:
            previous = merged[-1]
            current_gap = block.a - (previous[0] + previous[2])
            source_gap = block.b - (previous[1] + previous[2])
            if 0 <= current_gap <= 2 and 0 <= source_gap <= 2:
                previous[2] = block.a + block.size - previous[0]
                previous[3] = block.b + block.size - previous[1]
                continue
        merged.append([block.a, block.b, block.size, block.size])

    spans: list[tuple[int, int, int, int, float]] = []
    for current_start, source_start, current_length, source_length in merged:
        if min(current_length, source_length) < MIN_PASSAGE_TOKENS:
            continue
        current_segment = current_words[current_start : current_start + current_length]
        source_segment = source_words[source_start : source_start + source_length]
        score = SequenceMatcher(None, current_segment, source_segment, autojunk=False).ratio()
        if score >= MIN_PASSAGE_SIMILARITY:
            spans.append(
                (
                    current_start,
                    current_start + current_length,
                    source_start,
                    source_start + source_length,
                    score,
                )
            )
    return spans


def _build_evidence(
    current_id: UUID,
    source_id: UUID,
    current_page: _PageText,
    source_page: _PageText,
    current_span: tuple[int, int],
    source_span: tuple[int, int],
    score: float,
) -> IntegrityEvidence | None:
    current_start, current_end = current_span
    source_start, source_end = source_span
    current_tokens = current_page.tokens[current_start:current_end]
    source_tokens = source_page.tokens[source_start:source_end]
    if not current_tokens or not source_tokens:
        return None

    current_char_start, current_char_end = current_tokens[0].start, current_tokens[-1].end
    source_char_start, source_char_end = source_tokens[0].start, source_tokens[-1].end
    current_passage = current_page.text[current_char_start:current_char_end]
    source_passage = source_page.text[source_char_start:source_char_end]
    generic, definition_style = _generic_context(current_tokens)
    if generic:
        return None

    current_regions = _region_refs(current_page, current_char_start, current_char_end)
    source_regions = _region_refs(source_page, source_char_start, source_char_end)
    current_anchor = ",".join(region.region_id for region in current_regions if region.region_id)
    source_anchor = ",".join(region.region_id for region in source_regions if region.region_id)
    if not current_anchor:
        current_anchor = f"page-{current_page.page_number}-text"
    if not source_anchor:
        source_anchor = f"page-{source_page.page_number}-text"
    uncertain = not current_regions or not source_regions or any(
        region.confidence is None or region.confidence < LOW_OCR_CONFIDENCE
        for region in [*current_regions, *source_regions]
    )
    context_note = (
        "Definition-style wording can be common; treat this passage only as a review signal."
        if definition_style
        else None
    )
    return IntegrityEvidence(
        submission_id=current_id,
        answer_id=f"ocr:{current_page.page_number}:{current_anchor}",
        source_submission_id=source_id,
        source_answer_id=f"ocr:{source_page.page_number}:{source_anchor}",
        source_reference=f"submission:{source_id}",
        current_passage=current_passage,
        source_passage=source_passage,
        exact_match_score=score,
        current_regions=current_regions,
        source_regions=source_regions,
        ocr_uncertain=uncertain,
        context_note=context_note,
        detected_at=datetime.now(UTC),
    )


def compare_ocr_documents(
    current_id: UUID,
    current: OCRDocumentResult,
    source_id: UUID,
    source: OCRDocumentResult,
) -> tuple[list[IntegrityEvidence], OCRQualitySummary]:
    """Compare page text while retaining evidence locations and OCR uncertainty."""
    current_pages = [_page_text(page) for page in current.pages]
    source_pages = [_page_text(page) for page in source.pages]
    evidence: list[IntegrityEvidence] = []
    for current_page in current_pages:
        if not current_page.tokens:
            continue
        for source_page in source_pages:
            if not source_page.tokens:
                continue
            for start, end, source_start, source_end, score in _candidate_spans(
                current_page.tokens, source_page.tokens
            ):
                item = _build_evidence(
                    current_id,
                    source_id,
                    current_page,
                    source_page,
                    (start, end),
                    (source_start, source_end),
                    score,
                )
                if item is not None:
                    evidence.append(item)
                if len(evidence) >= 10:
                    break
            if len(evidence) >= 10:
                break
        if len(evidence) >= 10:
            break
    return evidence, _quality_summary(current, current_pages)


def summarize_ocr(document: OCRDocumentResult) -> OCRQualitySummary:
    """Expose calibrated OCR confidence and unreadable/missing-page signals."""
    return _quality_summary(document, [_page_text(page) for page in document.pages])
