"""Whole-submission copy detection between students' answer sheets for the same assignment.

Complements app.services.plagiarism (which lists individual matching passages): this answers
"how much of this answer sheet is the same as that one?" so a teacher can be told about pairs of
students who handed in (nearly) the same work.

Method: word 5-gram "shingles" of the normalized OCR text. Overlap of two sheets is
|A ∩ B| / min(|A|, |B|) (containment), so copying all of a shorter answer sheet into a longer one is
still caught. Shingles that come from the assignment's own question text (students often copy the
question) and boilerplate that most of the class shares are ignored, so matching those is not copying.

A flag is evidence for a teacher to look at, never a misconduct finding: both students in a pair are
flagged, because the system cannot tell who copied from whom.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import re
import unicodedata
from typing import Hashable, Iterable, Mapping, Optional, TypeVar

SHINGLE_SIZE = 5
# Fewer distinct answer shingles than this on either sheet = too little writing to judge.
MIN_SHINGLES = 12
# Share of the shorter sheet's answer text found in the other sheet.
COPY_FLAG_OVERLAP = 0.6
# With at least this many sheets, phrases present on more than half of them are treated as boilerplate.
BOILERPLATE_MIN_SHEETS = 4

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
# "[Page 2]" headers added to transcripts, and lone question labels like "Q1", "Q.2", "3)".
_NOISE_LINE = re.compile(r"^\s*(?:\[page \d+\]|q(?:uestion)?\s*\.?\s*\d{1,2}\s*[.):]?|\d{1,2}\s*[.):])\s*$", re.I)

K = TypeVar("K", bound=Hashable)


def _words(text: str) -> list[str]:
    lines = [line for line in (text or "").splitlines() if not _NOISE_LINE.match(line)]
    normalized = unicodedata.normalize("NFKC", "\n".join(lines)).casefold()
    return _TOKEN.findall(normalized)


def shingles(text: str) -> set[int]:
    words = _words(text)
    return {hash(tuple(words[i : i + SHINGLE_SIZE])) for i in range(len(words) - SHINGLE_SIZE + 1)}


def question_shingles(question_texts: Iterable[str]) -> set[int]:
    found: set[int] = set()
    for text in question_texts:
        found |= shingles(text)
    return found


@dataclass(frozen=True)
class CopyMatch:
    first: Hashable
    second: Hashable
    overlap: float  # 0-1, share of the shorter sheet's answer text that also appears in the other
    shared_phrases: int


def overlap(a: set[int], b: set[int]) -> Optional[float]:
    """Containment of the smaller set in the larger, or None when either sheet is too short to judge."""
    if min(len(a), len(b)) < MIN_SHINGLES:
        return None
    return len(a & b) / min(len(a), len(b))


def answer_fingerprints(texts: Mapping[K, str], question_texts: Iterable[str] = ()) -> dict[K, set[int]]:
    """Answer-only shingles per sheet: question text and class-wide boilerplate removed."""
    excluded = question_shingles(question_texts)
    prints = {key: shingles(text) - excluded for key, text in texts.items()}
    if len(prints) >= BOILERPLATE_MIN_SHEETS:
        counts: dict[int, int] = {}
        for shingle_set in prints.values():
            for s in shingle_set:
                counts[s] = counts.get(s, 0) + 1
        common = {s for s, n in counts.items() if n > len(prints) / 2}
        if common:
            prints = {key: shingle_set - common for key, shingle_set in prints.items()}
    return prints


def find_copies(
    texts: Mapping[K, str], question_texts: Iterable[str] = (), threshold: float = COPY_FLAG_OVERLAP
) -> list[CopyMatch]:
    """Every pair of sheets whose answer overlap reaches ``threshold``, highest overlap first."""
    prints = answer_fingerprints(texts, question_texts)
    matches = []
    for a, b in combinations(prints, 2):
        value = overlap(prints[a], prints[b])
        if value is not None and value >= threshold:
            matches.append(CopyMatch(a, b, round(value, 3), len(prints[a] & prints[b])))
    matches.sort(key=lambda m: m.overlap, reverse=True)
    return matches


def identical_files(
    file_hashes: Mapping[K, Optional[str]], owners: Mapping[K, Hashable]
) -> list[tuple[K, K]]:
    """Pairs of submissions by *different* students whose uploaded files are byte-for-byte identical.

    Exact duplicates need no OCR text, so this also catches a copied PDF that OCR could not read.
    """
    by_hash: dict[str, list[K]] = {}
    for key, value in file_hashes.items():
        if value:
            by_hash.setdefault(value, []).append(key)
    pairs = []
    for keys in by_hash.values():
        for a, b in combinations(keys, 2):
            if owners.get(a) != owners.get(b):
                pairs.append((a, b))
    return pairs


def similarity_to_others(
    current: K, texts: Mapping[K, str], question_texts: Iterable[str] = ()
) -> dict[K, float]:
    """Overlap of ``current`` with every other sheet that is long enough to compare."""
    prints = answer_fingerprints(texts, question_texts)
    mine = prints.get(current)
    if mine is None:
        return {}
    result = {}
    for key, other in prints.items():
        if key == current:
            continue
        value = overlap(mine, other)
        if value is not None:
            result[key] = round(value, 3)
    return result
