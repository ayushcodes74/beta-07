"""Within-submission handwriting consistency check (teacher review signal; NOT validated writer verification).

Compares the handwriting style of each answer (or page) of one submission against the rest of the same
submission and flags segments whose style differs much more than the writer's own line-to-line variation.

Features per handwritten text line (classic writer-identification features, no trained model):
- stroke/edge direction histogram (slant and curvature), stroke thickness, ink density
- letter size / spacing statistics from connected components
- uniform LBP texture histogram of the ink

This is an unvalidated heuristic. A different pen, page, scan or writing speed can also change these
features. Results are for teacher review only and must never be shown to students as a finding.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

ANALYSIS_VERSION = "hw-consistency-1"
METHOD = "within-submission style comparison (unvalidated heuristic)"
# A segment is flagged only if BOTH its composite effect size >= DEFAULT_THRESHOLD and a permutation test
# (shuffling which lines belong to the segment) gives p < P_VALUE_ALPHA. Rough calibration on two real
# writers (scripts/evaluate_handwriting_consistency.py): same-writer effect ~0.3-0.7, different-writer ~1.0-1.3.
# NOT a validated operating point.
DEFAULT_THRESHOLD = 0.9
P_VALUE_ALPHA = 0.01
PERMUTATIONS = 300
# Below this, one writer's natural variation (e.g. neat copied question lines vs. fast answers) looks like
# a different writer, so the result is "insufficient handwriting" rather than a guess.
MIN_LINES_PER_SEGMENT = 6
LINE_HEIGHT = 48

_BARE_NUMBER_MARKER = re.compile(r"^\s*(\d{1,2})\s*[.):](?!\d)")
_PREFIXED_MARKER = re.compile(r"^\s*q(?:uestion)?\s*\.?\s*(?:no\.?\s*)?(\d{1,2})\b", re.I)


@dataclass
class LineSample:
    page_number: int
    bbox: Tuple[int, int, int, int]
    text: str
    features: np.ndarray
    crop: np.ndarray = field(repr=False)


@dataclass
class Segment:
    segment_id: str
    label: str
    lines: List[LineSample]

    @property
    def page_numbers(self) -> List[int]:
        return sorted({line.page_number for line in self.lines})


# ---------------------------------------------------------------------------------------------
# Line features
# ---------------------------------------------------------------------------------------------

def _lbp_histogram(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Uniform LBP (P=8, R=1) histogram (10 bins) over ink-adjacent pixels."""
    g = gray.astype(np.int16)
    center = g[1:-1, 1:-1]
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
    bits = [(g[1 + dy:g.shape[0] - 1 + dy, 1 + dx:g.shape[1] - 1 + dx] >= center).astype(np.uint8) for dy, dx in offsets]
    stack = np.stack(bits, axis=-1)
    transitions = np.sum(stack != np.roll(stack, 1, axis=-1), axis=-1)
    ones = np.sum(stack, axis=-1)
    codes = np.where(transitions <= 2, ones, 9)  # 0..8 uniform patterns, 9 = non-uniform
    m = mask[1:-1, 1:-1] > 0
    if not m.any():
        return np.zeros(10)
    hist = np.bincount(codes[m].ravel(), minlength=10).astype(float)
    return hist / hist.sum()


def line_features(crop_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Feature vector for one handwritten text line, or None if there is too little ink."""
    if crop_bgr is None or crop_bgr.size == 0:
        return None
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY) if crop_bgr.ndim == 3 else crop_bgr
    h, w = gray.shape[:2]
    if h < 10 or w < 2 * h:
        return None
    scale = LINE_HEIGHT / float(h)
    gray = cv2.resize(gray, (max(LINE_HEIGHT * 2, int(w * scale)), LINE_HEIGHT), interpolation=cv2.INTER_AREA)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink_fraction = float(np.count_nonzero(ink)) / ink.size
    if ink_fraction < 0.02 or ink_fraction > 0.6:
        return None

    # 1) Edge-direction histogram (12 bins over 0..180 deg), magnitude-weighted, at ink boundaries
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    strong = mag > np.percentile(mag, 75)
    angles = (np.degrees(np.arctan2(gy[strong], gx[strong])) + 180.0) % 180.0
    direction = np.histogram(angles, bins=12, range=(0, 180), weights=mag[strong])[0].astype(float)
    direction /= max(direction.sum(), 1e-9)

    # 2) Stroke thickness (relative to line height)
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    stroke = 2.0 * float(dist[ink > 0].mean()) / LINE_HEIGHT

    # 3) Letter size / spacing from connected components
    count, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    comps = stats[1:]
    comps = comps[comps[:, cv2.CC_STAT_AREA] >= 8]
    if len(comps) < 3:
        return None
    heights = comps[:, cv2.CC_STAT_HEIGHT] / LINE_HEIGHT
    widths = comps[:, cv2.CC_STAT_WIDTH] / LINE_HEIGHT
    lefts = np.sort(comps[:, cv2.CC_STAT_LEFT])
    gaps = np.diff(lefts) / LINE_HEIGHT if len(lefts) > 1 else np.array([0.0])
    shape = np.array([
        np.median(heights), np.median(widths), np.median(widths / np.maximum(heights, 1e-3)),
        np.median(gaps), len(comps) / (gray.shape[1] / LINE_HEIGHT),
    ])

    # 4) Texture
    lbp = _lbp_histogram(gray, cv2.dilate(ink, np.ones((3, 3), np.uint8)))

    return np.concatenate([direction, [stroke, ink_fraction], shape, lbp])


def _is_prose(text: str) -> bool:
    letters = sum(ch.isalpha() for ch in text)
    return letters >= 8 and letters / max(len(text.strip()), 1) >= 0.6


def _normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def collect_lines(pages: Sequence[Dict[str, Any]]) -> List[LineSample]:
    """pages: [{"page_number", "image" (BGR), "blocks": [{"text", "bbox": (x1,y1,x2,y2)}]}] in reading order."""
    # Printed letterheads/footers repeat on several pages; they are not the student's handwriting.
    seen_on: Dict[str, set] = {}
    for page in pages:
        for block in page["blocks"]:
            key = _normalized(block.get("text", ""))
            if len(key) >= 6:
                seen_on.setdefault(key, set()).add(page["page_number"])
    repeated = {key for key, numbers in seen_on.items() if len(numbers) >= 2}

    samples: List[LineSample] = []
    for page in pages:
        image = page["image"]
        for block in page["blocks"]:
            text = block.get("text", "") or ""
            if not _is_prose(text) or _normalized(text) in repeated:
                continue
            x1, y1, x2, y2 = (int(v) for v in block["bbox"])
            crop = image[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
            features = line_features(crop)
            if features is not None:
                samples.append(LineSample(page["page_number"], (x1, y1, x2, y2), text, features, crop))
    return samples


# ---------------------------------------------------------------------------------------------
# Segmentation & scoring
# ---------------------------------------------------------------------------------------------

def _segments_by_answer(lines: List[LineSample]) -> List[Segment]:
    segments: List[Segment] = []
    last = 0
    for line in lines:
        match = _PREFIXED_MARKER.match(line.text) or _BARE_NUMBER_MARKER.match(line.text)
        number = int(match.group(1)) if match else None
        if number is not None and number > last:
            segments.append(Segment(f"answer-{number}", f"Answer {number}", []))
            last = number
        if segments:
            segments[-1].lines.append(line)
    return segments


def build_groupings(lines: List[LineSample]) -> List[Tuple[str, List[Segment]]]:
    """Ways to split the submission for comparison: by answer (question number) and by page, each used
    when it yields 2+ segments with enough lines; halves of the lines only as a last resort."""
    def usable(segs: List[Segment]) -> List[Segment]:
        return [s for s in segs if len(s.lines) >= MIN_LINES_PER_SEGMENT]

    groupings: List[Tuple[str, List[Segment]]] = []
    answers = usable(_segments_by_answer(lines))
    if len(answers) >= 2:
        groupings.append(("answer", answers))
    by_page: Dict[int, List[LineSample]] = {}
    for line in lines:
        by_page.setdefault(line.page_number, []).append(line)
    pages = usable([Segment(f"page-{n}", f"Page {n}", ls) for n, ls in sorted(by_page.items())])
    if len(pages) >= 2:
        groupings.append(("page", pages))
    if not groupings and len(lines) >= 2 * MIN_LINES_PER_SEGMENT:
        half = len(lines) // 2
        groupings.append(("lines", [
            Segment("lines-1", f"Lines 1-{half}", lines[:half]),
            Segment("lines-2", f"Lines {half + 1}-{len(lines)}", lines[half:]),
        ]))
    return groupings


def _effect_size(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute standardized difference of feature means (pooled within-group SD per feature)."""
    var_a = a.var(axis=0, ddof=1) if len(a) > 1 else np.zeros(a.shape[1])
    var_b = b.var(axis=0, ddof=1) if len(b) > 1 else np.zeros(b.shape[1])
    pooled = np.sqrt(((len(a) - 1) * var_a + (len(b) - 1) * var_b) / max(len(a) + len(b) - 2, 1))
    pooled = np.maximum(pooled, 1e-3 + 0.05 * np.abs(np.concatenate([a, b]).mean(axis=0)))
    return float(np.mean(np.abs(a.mean(axis=0) - b.mean(axis=0)) / pooled))


def _permutation_p_value(segment: np.ndarray, rest: np.ndarray, observed: float, rng, n: int = PERMUTATIONS) -> float:
    """Share of random line re-assignments (same sizes) at least as different as the observed split."""
    pooled = np.vstack([segment, rest])
    size = len(segment)
    hits = 0
    for _ in range(n):
        order = rng.permutation(len(pooled))
        if _effect_size(pooled[order[:size]], pooled[order[size:]]) >= observed:
            hits += 1
    return (hits + 1) / (n + 1)


def _thumbnail(crop: np.ndarray, height: int = 40, max_width: int = 520) -> str:
    h, w = crop.shape[:2]
    scale = height / float(max(h, 1))
    resized = cv2.resize(crop, (min(max_width, max(1, int(w * scale))), height), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", resized)
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii") if ok else ""


def _samples(segment: Segment, count: int = 2) -> List[Dict[str, Any]]:
    longest = sorted(segment.lines, key=lambda l: l.bbox[2] - l.bbox[0], reverse=True)[:count]
    return [
        {"page_number": l.page_number, "bounding_box": dict(zip(("x1", "y1", "x2", "y2"), l.bbox)),
         "text": l.text, "image": _thumbnail(l.crop)}
        for l in longest
    ]


def analyze(pages: Sequence[Dict[str, Any]], threshold: float = DEFAULT_THRESHOLD) -> Dict[str, Any]:
    """Run the within-submission comparison. See module docstring for limitations."""
    lines = collect_lines(pages)
    groupings = build_groupings(lines)
    base = {
        "version": ANALYSIS_VERSION,
        "method": METHOD,
        "threshold": threshold,
        "p_value_alpha": P_VALUE_ALPHA,
        "min_lines_per_segment": MIN_LINES_PER_SEGMENT,
        "lines_analyzed": len(lines),
        "segments": [],
        "flagged": [],
        "limitations": (
            "Unvalidated heuristic. Different pens, paper, scanning, lighting or writing speed can also change "
            "handwriting style. Compare the samples yourself; this is not evidence of misconduct."
        ),
    }
    if not groupings:
        return {**base, "status": "insufficient_handwriting",
                "reason": f"Need at least two answers or pages with {MIN_LINES_PER_SEGMENT}+ handwritten lines each."}

    rng = np.random.default_rng(0)  # deterministic: same submission -> same result
    for kind, segments in groupings:
        matrices = [np.vstack([l.features for l in s.lines]) for s in segments]
        results = []
        for i, segment in enumerate(segments):
            rest = np.vstack([m for j, m in enumerate(matrices) if j != i])
            score = _effect_size(matrices[i], rest)
            p_value = _permutation_p_value(matrices[i], rest, score, rng)
            results.append((segment, score, score >= threshold and p_value < P_VALUE_ALPHA, p_value))

        flagged = [r for r in results if r[2]]
        if len(segments) == 2 and flagged:
            # Two parts: "A differs from B" is symmetric, so don't guess which one is the other writer.
            first, second = segments
            score, p_value = max((r[1], r[3]) for r in flagged)
            for segment in segments:
                base["segments"].append({
                    "segment_id": segment.segment_id, "kind": kind, "label": segment.label,
                    "page_numbers": segment.page_numbers, "line_count": len(segment.lines),
                    "difference_score": round(score, 3), "p_value": round(p_value, 4), "flagged": True,
                })
            base["flagged"].append({
                "segment_id": f"{first.segment_id}+{second.segment_id}", "kind": kind,
                "label": f"{first.label} and {second.label} look written by different hands",
                "page_numbers": sorted({*first.page_numbers, *second.page_numbers}),
                "difference_score": round(score, 3), "p_value": round(p_value, 4),
                "compared_with": second.label, "samples": _samples(first), "reference_samples": _samples(second),
            })
            continue
        flagged_ids = {r[0].segment_id for r in flagged}
        for segment, score, _, p_value in results:
            base["segments"].append({
                "segment_id": segment.segment_id, "kind": kind, "label": segment.label,
                "page_numbers": segment.page_numbers, "line_count": len(segment.lines),
                "difference_score": round(score, 3), "p_value": round(p_value, 4),
                "flagged": segment.segment_id in flagged_ids,
            })
        for segment, score, _, p_value in flagged:
            reference = min((r for r in results if r[0] is not segment), key=lambda r: r[1])[0]
            base["flagged"].append({
                "segment_id": segment.segment_id, "kind": kind, "label": segment.label,
                "page_numbers": segment.page_numbers, "difference_score": round(score, 3),
                "p_value": round(p_value, 4), "compared_with": reference.label,
                "samples": _samples(segment), "reference_samples": _samples(reference),
            })
    base["status"] = "possible_different_handwriting" if base["flagged"] else "consistent"
    return base
