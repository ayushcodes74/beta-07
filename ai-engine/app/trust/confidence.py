"""Multi-factor confidence estimation service.

Computes a deterministic, measurable confidence score by evaluating evidence quality,
evidence coverage, rubric clarity, OCR text confidence, and evaluation completeness.
Does not rely on uncalibrated LLM self-reporting.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from app.schemas.assignment import Rubric
from app.schemas.common import SourceReference
from app.schemas.grading import CriterionEvaluation, QuestionGrade
from app.schemas.trust import ConfidenceBreakdown, ConfidenceLevel

logger = logging.getLogger(__name__)


class ConfidenceEstimator:
    """Calculates objective confidence metrics for academic grading evaluations."""

    def __init__(
        self,
        weight_evidence_quality: float = 0.30,
        weight_evidence_coverage: float = 0.25,
        weight_rubric_clarity: float = 0.15,
        weight_ocr_quality: float = 0.15,
        weight_completeness: float = 0.15,
        review_threshold: float = 0.70,
    ):
        """Initialize ConfidenceEstimator with configurable weights.

        Args:
            weight_evidence_quality: Weight for similarity & chunk presence (default: 0.30).
            weight_evidence_coverage: Weight for proportion of criteria supported by evidence (default: 0.25).
            weight_rubric_clarity: Weight for well-defined, non-ambiguous criteria (default: 0.15).
            weight_ocr_quality: Weight for OCR text extraction fidelity (default: 0.15).
            weight_completeness: Weight for evaluation structure completeness (default: 0.15).
            review_threshold: Overall score below which teacher review is recommended (default: 0.70).
        """
        total = weight_evidence_quality + weight_evidence_coverage + weight_rubric_clarity + weight_ocr_quality + weight_completeness
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Confidence weights must sum to 1.0, got {total:.2f}")

        self.w_ev_quality = weight_evidence_quality
        self.w_ev_coverage = weight_evidence_coverage
        self.w_rubric = weight_rubric_clarity
        self.w_ocr = weight_ocr_quality
        self.w_complete = weight_completeness
        self.review_threshold = review_threshold

    def calculate_confidence(
        self,
        question_grade: QuestionGrade,
        rubric: Rubric,
        source_references: List[SourceReference],
        ocr_confidence: Optional[float] = None,
        has_sufficient_evidence: bool = True,
    ) -> ConfidenceBreakdown:
        """Compute multi-factor confidence breakdown for a question evaluation.

        Formula:
          Overall = (w_ev_qual * EvidenceQuality)
                  + (w_ev_cov * EvidenceCoverage)
                  + (w_rubric * RubricClarity)
                  + (w_ocr * OCRQuality)
                  + (w_complete * Completeness)

        Args:
            question_grade: QuestionGrade produced by evaluator.
            rubric: Target rubric.
            source_references: Supporting course references.
            ocr_confidence: Optional OCR extraction score from OCR teammate (0.0 to 1.0).
            has_sufficient_evidence: Flag from evidence retriever.

        Returns:
            ConfidenceBreakdown with individual factor scores and review recommendation.
        """
        # 1. Evidence Quality Factor [0.0 - 1.0]
        ev_quality = self._score_evidence_quality(source_references, has_sufficient_evidence)

        # 2. Evidence Coverage Factor [0.0 - 1.0]
        ev_coverage = self._score_evidence_coverage(question_grade.criterion_evaluations, has_sufficient_evidence)

        # 3. Rubric Clarity Factor [0.0 - 1.0]
        rubric_clarity = self._score_rubric_clarity(rubric)

        # 4. OCR Quality Factor [0.0 - 1.0]
        ocr_score = 1.0 if ocr_confidence is None else max(0.0, min(1.0, float(ocr_confidence)))

        # 5. Completeness Factor [0.0 - 1.0]
        completeness = self._score_completeness(question_grade, rubric)

        # 6. Weighted Sum
        overall = (
            (self.w_ev_quality * ev_quality)
            + (self.w_ev_coverage * ev_coverage)
            + (self.w_rubric * rubric_clarity)
            + (self.w_ocr * ocr_score)
            + (self.w_complete * completeness)
        )
        overall = round(max(0.0, min(1.0, overall)), 2)

        # Categorical rating
        if overall >= 0.80:
            level = ConfidenceLevel.HIGH
        elif overall >= 0.60:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW

        # Trigger review recommendation if below threshold or if evidence is critically low
        review_rec = (overall < self.review_threshold) or (ev_quality < 0.3) or (ocr_score < 0.60)

        explanation = self._build_explanation(
            overall=overall,
            ev_quality=ev_quality,
            ev_coverage=ev_coverage,
            rubric_clarity=rubric_clarity,
            ocr_score=ocr_score,
            completeness=completeness,
            review_rec=review_rec,
        )

        return ConfidenceBreakdown(
            overall=overall,
            level=level,
            evidence_quality=round(ev_quality, 2),
            evidence_coverage=round(ev_coverage, 2),
            rubric_clarity=round(rubric_clarity, 2),
            ocr_quality=round(ocr_score, 2),
            evaluation_completeness=round(completeness, 2),
            explanation=explanation,
            review_recommended=review_rec,
        )

    @staticmethod
    def _score_evidence_quality(
        references: List[SourceReference],
        has_sufficient_evidence: bool,
    ) -> float:
        """Score based on presence and vector similarity of source citations."""
        if not has_sufficient_evidence or not references:
            return 0.1

        scores = [r.similarity_score for r in references if r.similarity_score is not None]
        if not scores:
            return 0.7  # Chunks present but un-scored

        avg_sim = sum(scores) / len(scores)
        # More chunks (up to 3) boosts confidence
        count_bonus = min(0.2, (len(references) - 1) * 0.1)
        return max(0.2, min(1.0, avg_sim + count_bonus))

    @staticmethod
    def _score_evidence_coverage(
        criterion_evals: List[CriterionEvaluation],
        has_sufficient_evidence: bool,
    ) -> float:
        """Measure what percentage of evaluated criteria cite course evidence."""
        if not has_sufficient_evidence or not criterion_evals:
            return 0.1

        criteria_with_evidence = sum(1 for c in criterion_evals if c.evidence_references)
        return criteria_with_evidence / len(criterion_evals)

    @staticmethod
    def _score_rubric_clarity(rubric: Rubric) -> float:
        """Assess whether rubric criteria are unambiguous and detailed."""
        if not rubric.criteria:
            return 0.2

        clarity_points = 0.0
        for c in rubric.criteria:
            score = 0.0
            if c.description and len(c.description.strip()) > 10:
                score += 0.5
            if c.expected_concepts:
                score += 0.3
            if c.acceptable_alternatives:
                score += 0.2
            clarity_points += score

        return max(0.3, min(1.0, clarity_points / len(rubric.criteria)))

    @staticmethod
    def _score_completeness(question_grade: QuestionGrade, rubric: Rubric) -> float:
        """Verify all criteria were evaluated with valid explanations."""
        if not question_grade.criterion_evaluations:
            return 0.0

        rubric_ids = {c.criterion_id for c in rubric.criteria}
        eval_ids = {c.criterion_id for c in question_grade.criterion_evaluations}

        # Did evaluator score every criterion?
        coverage = len(rubric_ids.intersection(eval_ids)) / len(rubric_ids) if rubric_ids else 0.5

        # Check non-empty explanations
        valid_explanations = sum(
            1 for c in question_grade.criterion_evaluations if c.explanation and len(c.explanation.strip()) > 5
        )
        expl_ratio = valid_explanations / len(question_grade.criterion_evaluations)

        return round((coverage * 0.5) + (expl_ratio * 0.5), 2)

    @staticmethod
    def _build_explanation(
        overall: float,
        ev_quality: float,
        ev_coverage: float,
        rubric_clarity: float,
        ocr_score: float,
        completeness: float,
        review_rec: bool,
    ) -> str:
        """Generate human-readable justification for calculated confidence."""
        flags: List[str] = []
        if ev_quality < 0.5:
            flags.append("weak course evidence")
        if ev_coverage < 0.5:
            flags.append("partial evidence coverage")
        if rubric_clarity < 0.6:
            flags.append("ambiguous rubric criteria")
        if ocr_score < 0.7:
            flags.append(f"low OCR extraction confidence ({ocr_score:.2f})")
        if completeness < 0.7:
            flags.append("incomplete criterion evaluations")

        if not flags:
            return f"High confidence ({overall:.2f}): strong evidence, clear rubric, and comprehensive evaluation."

        flag_str = ", ".join(flags)
        rec_str = " Human review recommended." if review_rec else ""
        return f"Confidence {overall:.2f} affected by {flag_str}.{rec_str}"

