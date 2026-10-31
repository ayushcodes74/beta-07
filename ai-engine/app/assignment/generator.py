"""Assignment Generator service.

Generates draft MCQ and subjective assignments grounded exclusively in course
materials, complete with model answers, rubrics, and source citations.
All assignments are created with status='DRAFT' requiring teacher approval.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field

from app.llm.gemini_client import GeminiClient, get_gemini_client
from app.llm import prompts
from app.rag.context_builder import ContextBuilder
from app.rag.retriever import CourseMaterialRetriever
from app.assignment.rubric_generator import RubricGenerator
from app.schemas.assignment import (
    AssignmentDraft,
    AssignmentGenerationRequest,
    DifficultyLevel,
    ModelAnswer,
    MCQOption,
    QuestionDraft,
    QuestionType,
    Rubric,
)
from app.schemas.common import SourceReference

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intermediate LLM Output Schemas
# ---------------------------------------------------------------------------

class _GeneratedQuestion(BaseModel):
    question_text: str
    question_type: QuestionType
    marks: float
    difficulty: DifficultyLevel
    learning_objective: Optional[str] = None
    mcq_options: Optional[List[MCQOption]] = None
    model_answer_text: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    acceptable_approaches: List[str] = Field(default_factory=list)
    has_sufficient_evidence: bool = True
    evidence_notes: Optional[str] = None


class _GeneratedAssignmentResponse(BaseModel):
    title: str
    instructions: str
    questions: List[_GeneratedQuestion] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Assignment Generator Service
# ---------------------------------------------------------------------------

class AssignmentGenerator:
    """Service to generate draft assignments and rubrics for teacher review."""

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        retriever: Optional[CourseMaterialRetriever] = None,
        rubric_generator: Optional[RubricGenerator] = None,
    ):
        self.gemini_client = gemini_client or get_gemini_client()
        self.retriever = retriever
        self.rubric_generator = rubric_generator or RubricGenerator(gemini_client=self.gemini_client)

    def generate_assignment(
        self,
        request: AssignmentGenerationRequest,
        course_materials: Optional[str] = None,
    ) -> AssignmentDraft:
        """Generate a complete draft assignment from teacher request and course material.

        Args:
            request: The validated AssignmentGenerationRequest.
            course_materials: Optional direct course text; if omitted, retriever will fetch.

        Returns:
            AssignmentDraft with status="DRAFT" and grounded questions.
        """
        # 1. Retrieve course context if not explicitly provided
        context_text = course_materials or ""
        source_refs: List[SourceReference] = []

        if not context_text and self.retriever is not None:
            retrieval_res = self.retriever.retrieve(
                query=f"{request.topic} {request.teacher_instructions or ''}",
                course_id=request.course_id,
                top_k=8,
                similarity_threshold=0.05,
            )
            if retrieval_res.chunks:
                context_text = ContextBuilder().build_context_block(retrieval_res.chunks)
                source_refs = ContextBuilder.to_source_references(retrieval_res.chunks)

        grounded = bool(context_text.strip())
        if not grounded:
            logger.warning("No course materials provided or retrieved for topic '%s'; using topic-only mode", request.topic)
            context_text = prompts.NO_COURSE_MATERIAL
        system_instruction = (
            prompts.SYSTEM_ASSIGNMENT_GENERATOR if grounded else prompts.SYSTEM_ASSIGNMENT_GENERATOR_TOPIC_ONLY
        )

        # 2. Determine question split
        num_mcq, num_sub = self._calculate_question_split(request.question_count, request.question_type)

        # 3. Format prompt
        prompt = prompts.build_assignment_generation_prompt(
            course_material=context_text,
            topic=request.topic,
            num_mcq=num_mcq,
            num_subjective=num_sub,
            target_difficulty=request.difficulty.value,
            grounded=grounded,
        )

        if request.teacher_instructions:
            prompt += f"\n### TEACHER SPECIAL INSTRUCTIONS:\n{request.teacher_instructions}\n"

        prompt += f"\nTotal target assignment marks: {request.total_marks}.\n"

        # 4. Invoke LLM for structured questions
        llm_response = self.gemini_client.generate_structured(
            prompt=prompt,
            response_schema=_GeneratedAssignmentResponse,
            system_instruction=system_instruction,
        )

        # 5. Process and assemble draft questions
        deduplicated = self._deduplicate_questions(llm_response.questions)
        assembled_questions: List[QuestionDraft] = []
        mark_per_question = round(request.total_marks / len(deduplicated), 2) if deduplicated else 1.0

        for idx, q in enumerate(deduplicated):
            q_id = f"q_{idx + 1}_{uuid.uuid4().hex[:6]}"
            q_marks = mark_per_question

            # Build model answer & rubric for subjective
            model_ans: Optional[ModelAnswer] = None
            q_rubric: Optional[Rubric] = None

            if q.question_type in (QuestionType.SUBJECTIVE, QuestionType.MIXED):
                if q.model_answer_text or q.key_points:
                    model_ans = ModelAnswer(
                        text=q.model_answer_text or "See key points.",
                        key_points=q.key_points or ["Demonstrate correct understanding."],
                        acceptable_approaches=q.acceptable_approaches or ["Equivalent terminology accepted."],
                    )
                # Generate rubric
                q_rubric = self.rubric_generator.generate_rubric(
                    question_text=q.question_text,
                    max_marks=q_marks,
                    course_context=context_text,
                    model_answer=model_ans.text if model_ans else None,
                    grounded=grounded,
                )

            # Check evidence flag
            has_evidence = q.has_sufficient_evidence and grounded

            draft_q = QuestionDraft(
                question_id=q_id,
                question_type=q.question_type,
                question_text=q.question_text,
                marks=q_marks,
                difficulty=q.difficulty,
                learning_objective=q.learning_objective,
                mcq_options=q.mcq_options,
                model_answer=model_ans,
                rubric=q_rubric,
                source_evidence=source_refs,
                has_sufficient_evidence=has_evidence,
                evidence_notes=q.evidence_notes or ("Grounded in course notes" if has_evidence else "Insufficient course material"),
            )
            assembled_questions.append(draft_q)

        # 6. Reconcile question marks to match request.total_marks exactly
        self._reconcile_assignment_marks(assembled_questions, request.total_marks)

        assignment_id = f"asgn_{request.course_id}_{uuid.uuid4().hex[:8]}"
        return AssignmentDraft(
            assignment_id=assignment_id,
            course_id=request.course_id,
            topic=request.topic,
            title=llm_response.title or f"{request.topic} Assignment",
            instructions=llm_response.instructions or "Complete all questions.",
            total_marks=request.total_marks,
            questions=assembled_questions,
            status="DRAFT",  # Always DRAFT!
        )

    @staticmethod
    def _calculate_question_split(count: int, q_type: QuestionType) -> tuple[int, int]:
        """Calculate counts for MCQ and subjective questions."""
        if q_type == QuestionType.MCQ:
            return count, 0
        if q_type == QuestionType.SUBJECTIVE:
            return 0, count
        # Mixed: approx 50/50
        mcq = count // 2
        sub = count - mcq
        return mcq, sub

    @staticmethod
    def _deduplicate_questions(questions: List[_GeneratedQuestion]) -> List[_GeneratedQuestion]:
        """Filter out duplicate questions with identical or near-identical text."""
        seen = set()
        unique: List[_GeneratedQuestion] = []
        for q in questions:
            norm = "".join(q.question_text.lower().split())
            if norm not in seen and len(norm) > 10:
                seen.add(norm)
                unique.append(q)
        return unique

    @staticmethod
    def _reconcile_assignment_marks(questions: List[QuestionDraft], total_marks: float) -> None:
        """Ensure sum of question marks equals total_marks."""
        if not questions:
            return
        curr_sum = sum(q.marks for q in questions)
        diff = round(total_marks - curr_sum, 2)
        if abs(diff) > 0.01:
            # Adjust the last question
            questions[-1].marks = max(1.0, round(questions[-1].marks + diff, 2))
            if questions[-1].rubric is not None:
                # Update rubric total to match adjusted question marks
                questions[-1].rubric = RubricGenerator._reconcile_marks(
                    questions[-1].rubric.criteria,
                    questions[-1].marks,
                )
                # Reconstruct rubric with matching total
                questions[-1].rubric = Rubric(
                    criteria=questions[-1].rubric,
                    total_marks=questions[-1].marks,
                )

    # -----------------------------------------------------------------------
    # Teacher Editing Interface
    # -----------------------------------------------------------------------

    @staticmethod
    def edit_question(
        assignment: AssignmentDraft,
        question_id: str,
        question_text: Optional[str] = None,
        marks: Optional[float] = None,
        model_answer_text: Optional[str] = None,
        rubric: Optional[Rubric] = None,
    ) -> AssignmentDraft:
        """Allow a teacher to edit a question in a draft assignment."""
        for q in assignment.questions:
            if q.question_id == question_id:
                if question_text is not None:
                    q.question_text = question_text
                if marks is not None:
                    q.marks = marks
                if model_answer_text is not None:
                    if q.model_answer:
                        q.model_answer.text = model_answer_text
                    else:
                        q.model_answer = ModelAnswer(text=model_answer_text)
                if rubric is not None:
                    q.rubric = rubric
                break

        # Re-verify total marks
        assignment.total_marks = sum(q.marks for q in assignment.questions)
        return assignment

