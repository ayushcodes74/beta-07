"""Assignment Generator service.

Generates draft MCQ and subjective assignments grounded exclusively in course
materials, complete with model answers, rubrics, and source citations.
All assignments are created with status='DRAFT' requiring teacher approval.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from pydantic import BaseModel, Field

from app.llm.gemini_client import GeminiClient
from app.llm.fallback_client import get_llm_client
from app.llm import prompts
from app.llm.gemini_client import LLMError, LLMResponseValidationError
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

    #: Upper bound on concurrent rubric LLM calls (keeps bursts within provider rate limits).
    MAX_PARALLEL_RUBRICS = 4

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        retriever: Optional[CourseMaterialRetriever] = None,
        rubric_generator: Optional[RubricGenerator] = None,
    ):
        self.gemini_client = gemini_client or get_llm_client()
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

        if request.syllabus and request.syllabus.strip():
            prompt += prompts.build_syllabus_section(request.syllabus.strip())

        if request.teacher_instructions:
            prompt += f"\n### TEACHER SPECIAL INSTRUCTIONS:\n{request.teacher_instructions}\n"

        prompt += f"\nTotal target assignment marks: {request.total_marks}.\n"

        # 4. Invoke LLM for structured questions
        llm_response = self.gemini_client.generate_structured(
            prompt=prompt,
            response_schema=_GeneratedAssignmentResponse,
            system_instruction=system_instruction,
        )

        # 5. Process and assemble draft questions. Malformed questions (e.g. an MCQ without exactly
        # one correct option) are dropped individually instead of failing the whole assignment.
        deduplicated = [q for q in self._deduplicate_questions(llm_response.questions) if self._is_well_formed(q)]
        if not deduplicated:
            raise LLMResponseValidationError(
                "LLM returned no usable questions after validation.",
                raw_response=llm_response.model_dump_json()[:2000],
            )
        if len(deduplicated) < len(llm_response.questions):
            logger.warning(
                "Dropped %d duplicate/malformed generated question(s); keeping %d",
                len(llm_response.questions) - len(deduplicated), len(deduplicated),
            )
        assembled_questions: List[QuestionDraft] = []
        mark_per_question = round(request.total_marks / len(deduplicated), 2) if deduplicated else 1.0
        q_marks = mark_per_question
        q_ids = [f"q_{idx + 1}_{uuid.uuid4().hex[:6]}" for idx in range(len(deduplicated))]

        # Model answers for subjective questions
        model_answers: List[Optional[ModelAnswer]] = []
        for q in deduplicated:
            needs_rubric = q.question_type in (QuestionType.SUBJECTIVE, QuestionType.MIXED)
            model_answers.append(
                ModelAnswer(
                    text=q.model_answer_text or "See key points.",
                    key_points=q.key_points or ["Demonstrate correct understanding."],
                    acceptable_approaches=q.acceptable_approaches or ["Equivalent terminology accepted."],
                )
                if needs_rubric and (q.model_answer_text or q.key_points)
                else None
            )

        # Rubrics are independent LLM calls, so run them concurrently rather than one after another
        # (each can take tens of seconds on slower/free models).
        def _rubric(i: int) -> Rubric:
            q, model_ans = deduplicated[i], model_answers[i]
            try:
                return self.rubric_generator.generate_rubric(
                    question_text=q.question_text,
                    max_marks=q_marks,
                    course_context=context_text,
                    model_answer=model_ans.text if model_ans else None,
                    grounded=grounded,
                )
            except LLMError as exc:
                # Keep the already-generated question with a basic key-point rubric; the teacher
                # reviews the DRAFT anyway.
                logger.warning("Rubric generation failed for %s (%s); using basic rubric", q_ids[i], type(exc).__name__)
                return RubricGenerator.basic_rubric(q_marks, q.key_points)

        rubric_indices = [
            i for i, q in enumerate(deduplicated) if q.question_type in (QuestionType.SUBJECTIVE, QuestionType.MIXED)
        ]
        rubrics: dict[int, Rubric] = {}
        if rubric_indices:
            workers = min(len(rubric_indices), self.MAX_PARALLEL_RUBRICS)
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rubric") as pool:
                rubrics = dict(zip(rubric_indices, pool.map(_rubric, rubric_indices)))

        for idx, q in enumerate(deduplicated):
            q_id = q_ids[idx]
            model_ans = model_answers[idx]
            q_rubric: Optional[Rubric] = rubrics.get(idx)

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
    def _is_well_formed(q: _GeneratedQuestion) -> bool:
        """Reject questions that would fail QuestionDraft validation (bad MCQ option sets)."""
        if q.question_type == QuestionType.MCQ:
            options = q.mcq_options or []
            correct = sum(1 for o in options if o.is_correct)
            if len(options) < 2 or correct != 1:
                logger.warning(
                    "Dropping malformed MCQ (%d options, %d correct): %.80s", len(options), correct, q.question_text
                )
                return False
        return True

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
        if abs(diff) >= 0.01:
            # Adjust the last question (diff is a small rounding remainder)
            last = questions[-1]
            new_marks = round(last.marks + diff, 2)
            if new_marks <= 0:
                return
            if last.rubric is not None:
                # Rebuild the rubric first so the question never holds a rubric whose total mismatches.
                # (QuestionDraft validates on assignment, so the rubric must be a full Rubric object.)
                last.rubric = Rubric(
                    criteria=RubricGenerator._reconcile_marks(last.rubric.criteria, new_marks),
                    total_marks=new_marks,
                    instructions=last.rubric.instructions,
                )
            last.marks = new_marks

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

