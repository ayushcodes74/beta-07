"""Feedback generation service for student submissions.

Generates constructive, actionable, and encouraging feedback by synthesizing
criterion evaluations, matched concepts, missing concepts, and deduction reasoning.
"""

from __future__ import annotations

from typing import List, Optional
from app.schemas.grading import CriterionEvaluation, QuestionGrade


class FeedbackGenerator:
    """Builds structured and constructive student feedback from evaluation results."""

    @staticmethod
    def generate_question_feedback(
        question_id: str,
        max_marks: float,
        awarded_marks: float,
        criterion_evaluations: List[CriterionEvaluation],
        overall_explanation: str,
    ) -> str:
        """Create a holistic feedback summary for an individual question.

        Args:
            question_id: Question identifier.
            max_marks: Maximum marks.
            awarded_marks: Awarded marks.
            criterion_evaluations: Individual criteria evaluations.
            overall_explanation: High-level summary of performance.

        Returns:
            Constructive, markdown-formatted feedback text.
        """
        score_ratio = awarded_marks / max_marks if max_marks > 0 else 0.0
        lines: List[str] = []

        # Opening summary
        if score_ratio >= 0.95:
            lines.append(f"Excellent work on Question {question_id}! ({awarded_marks}/{max_marks} marks)")
        elif score_ratio >= 0.70:
            lines.append(f"Good answer on Question {question_id}. ({awarded_marks}/{max_marks} marks)")
        elif score_ratio >= 0.40:
            lines.append(f"Partial understanding demonstrated on Question {question_id}. ({awarded_marks}/{max_marks} marks)")
        else:
            lines.append(f"Question {question_id} requires substantial review. ({awarded_marks}/{max_marks} marks)")

        if overall_explanation:
            lines.append(f"\n{overall_explanation.strip()}")

        # Criterion breakdown
        deductions: List[str] = []
        demonstrated: List[str] = []

        for c in criterion_evaluations:
            c_name = c.criterion_name or c.criterion_id
            if c.awarded_marks < c.max_marks:
                diff = round(c.max_marks - c.awarded_marks, 2)
                missing_str = f" Missing: {', '.join(c.missing_concepts)}." if c.missing_concepts else ""
                deductions.append(f"- **{c_name}** (-{diff} marks): {c.explanation}{missing_str}")
            if c.matched_concepts:
                demonstrated.extend(c.matched_concepts)

        if demonstrated:
            lines.append(f"\n**Concepts Demonstrated:** {', '.join(sorted(set(demonstrated)))}.")

        if deductions:
            lines.append("\n**Deduction Breakdown:**")
            lines.extend(deductions)

        return "\n".join(lines)

    @staticmethod
    def generate_overall_feedback(question_grades: List[QuestionGrade]) -> str:
        """Generate comprehensive assignment-level feedback across all questions."""
        if not question_grades:
            return "No graded questions available."

        total_awarded = sum(q.awarded_marks for q in question_grades)
        total_max = sum(q.max_marks for q in question_grades)
        pct = (total_awarded / total_max * 100.0) if total_max > 0 else 0.0

        all_strengths: List[str] = []
        all_improvements: List[str] = []

        for q in question_grades:
            all_strengths.extend(q.strengths)
            all_improvements.extend(q.areas_for_improvement)

        sections: List[str] = [
            f"### Overall Assignment Feedback (Score: {total_awarded:.1f}/{total_max:.1f} — {pct:.1f}%)"
        ]

        if all_strengths:
            unique_strengths = sorted(set(all_strengths))[:4]
            sections.append("\n**Key Strengths:**")
            sections.extend([f"- {s}" for s in unique_strengths])

        if all_improvements:
            unique_imp = sorted(set(all_improvements))[:4]
            sections.append("\n**Areas for Growth:**")
            sections.extend([f"- {imp}" for imp in unique_imp])

        return "\n".join(sections)

