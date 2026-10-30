"""Marking rubric generator for subjective questions.

Produces criteria with explicit point allocations, expected concepts,
and acceptable alternative formulations grounded in course materials.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from app.llm.gemini_client import GeminiClient, get_gemini_client
from app.llm import prompts
from app.schemas.assignment import Rubric, RubricCriterion

logger = logging.getLogger(__name__)


class _RawRubricResponse(BaseModel):
    """Intermediate schema for LLM rubric generation."""
    instructions: Optional[str] = None
    criteria: List[RubricCriterion] = Field(min_length=1)


class RubricGenerator:
    """Service to create rubrics for subjective questions."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.gemini_client = gemini_client or get_gemini_client()

    def generate_rubric(
        self,
        question_text: str,
        max_marks: float,
        course_context: str,
        model_answer: Optional[str] = None,
    ) -> Rubric:
        """Generate a structured marking rubric for a subjective question.

        Args:
            question_text: The subjective question prompt.
            max_marks: Total marks available for the question.
            course_context: Course excerpts grounding the rubric.
            model_answer: Optional reference model answer.

        Returns:
            Rubric with criteria strictly summing to max_marks.
        """
        if max_marks <= 0:
            raise ValueError(f"max_marks must be greater than 0, got {max_marks}")
        if not question_text or not question_text.strip():
            raise ValueError("question_text cannot be empty.")

        model_answer_section = f"\n### MODEL ANSWER REFERENCE:\n{model_answer}" if model_answer else ""

        prompt = f"""### QUESTION (Max Marks: {max_marks}):
{question_text}
{model_answer_section}
### RELEVANT COURSE MATERIAL:
{course_context}

Generate a clear, objective marking rubric for grading this subjective question.
Requirements:
1. Divide the evaluation into logical criteria (e.g. concept definitions, analysis, examples).
2. The sum of all criteria marks MUST EXACTLY equal {max_marks}.
3. Specify expected concepts for full marks on each criterion.
4. Specify acceptable alternative formulations and equivalent terminology supported by the course material.
5. Support partial credit within each criterion.
"""

        raw = self.gemini_client.generate_structured(
            prompt=prompt,
            response_schema=_RawRubricResponse,
            system_instruction=prompts.SYSTEM_ASSIGNMENT_GENERATOR,
        )

        # Normalize and reconcile criteria marks to guarantee exact equality with max_marks
        reconciled_criteria = self._reconcile_marks(raw.criteria, max_marks)

        return Rubric(
            criteria=reconciled_criteria,
            total_marks=max_marks,
            instructions=raw.instructions or "Evaluate against criteria and allow partial credit for valid reasoning.",
        )

    @staticmethod
    def _reconcile_marks(
        criteria: List[RubricCriterion],
        target_total: float,
    ) -> List[RubricCriterion]:
        """Adjust criteria marks if needed so they sum exactly to target_total."""
        if not criteria:
            return criteria

        current_sum = sum(c.max_marks for c in criteria)
        diff = round(target_total - current_sum, 2)

        if abs(diff) > 0.001:
            # Scale proportionally or adjust the final criterion
            if current_sum > 0:
                scale = target_total / current_sum
                adjusted: List[RubricCriterion] = []
                running_sum = 0.0

                for i, c in enumerate(criteria):
                    if i == len(criteria) - 1:
                        # Final item takes the exact remainder
                        final_marks = max(0.5, round(target_total - running_sum, 2))
                        adjusted.append(c.model_copy(update={"max_marks": final_marks}))
                    else:
                        scaled_mark = max(0.5, round(c.max_marks * scale, 2))
                        running_sum += scaled_mark
                        adjusted.append(c.model_copy(update={"max_marks": scaled_mark}))
                return adjusted
            else:
                # Distribute evenly if all were 0
                even_mark = round(target_total / len(criteria), 2)
                return [c.model_copy(update={"max_marks": even_mark}) for c in criteria]

        return criteria

