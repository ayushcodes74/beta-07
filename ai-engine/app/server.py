"""HTTP wrapper exposing AI Engine services to the TrustGrade backend.

The backend cannot import this package directly (both projects use the top-level
package name ``app``), so the AI Engine runs as a small internal service, the same
way the OCR Engine does. Bind it to localhost only; it has no authentication of its
own and relies on the backend to authenticate and authorize teachers.

Run from the ai-engine directory:
    uvicorn app.server:app --host 127.0.0.1 --port 8002
"""

from __future__ import annotations

import importlib.util
import logging
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from app.assignment.generator import AssignmentGenerator
from app.config import get_settings
from app.grading.evaluator import AnswerEvaluator
from app.grading.evidence_retriever import IndexEvidenceRetriever
from app.rag.context_builder import ContextBuilder
from app.rag.course_index import get_course_index
from app.rag.embeddings import EmbeddingsUnavailableError
from app.schemas.common import SourceReference
from app.grading.feedback_generator import FeedbackGenerator
from app.schemas.assignment import QuestionType, Rubric, RubricCriterion
from app.schemas.grading import GradingRequest, GradingResult
from app.llm.fallback_client import get_llm_client
from app.llm.gemini_client import (
    LLMAPIError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
)
from app.schemas.assignment import AssignmentDraft, AssignmentGenerationRequest

logger = logging.getLogger("ai_engine.server")

app = FastAPI(
    title="TrustGrade AI Engine",
    description="Internal service: assignment generation and answer grading for the TrustGrade backend.",
    version="1.0.0",
)


class GenerateAssignmentRequest(AssignmentGenerationRequest):
    """Generation request, optionally with course material text to ground questions in."""

    course_materials: Optional[str] = Field(
        default=None,
        max_length=200_000,
        description="Optional course text. Without it, questions are generated from the topic alone.",
    )


class GradeQuestionInput(BaseModel):
    """One assignment question with the teacher's answer key (sent by the backend, never by students)."""

    question_id: str = Field(min_length=1, max_length=100)
    type: Literal["mcq", "subjective"]
    text: str = Field(min_length=1, max_length=5000)
    marks: float = Field(gt=0, le=1000)
    expected_answer: Optional[str] = Field(default=None, max_length=20_000)
    instructions: Optional[str] = Field(default=None, max_length=5000)
    options: List[dict] = Field(default_factory=list, max_length=20)
    correct_option_id: Optional[str] = Field(default=None, max_length=20)


class GradeSubmissionRequest(BaseModel):
    """Grade a whole submission whose answers are one OCR transcript of the student's pages."""

    submission_id: str = Field(min_length=1, max_length=100)
    assignment_id: str = Field(min_length=1, max_length=100)
    course_id: Optional[str] = Field(default=None, max_length=100)
    student_text: str = Field(max_length=200_000, description="OCR text of the entire submission")
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    questions: List[GradeQuestionInput] = Field(min_length=1, max_length=50)


# The OCR transcript is not split per question (handwritten pages have no reliable question
# boundaries), so every question sees the whole transcript and is told to grade only its own part.
_LOCATE_ANSWER_HINT = (
    "The student answer is the OCR transcript of the student's ENTIRE handwritten submission "
    "(all questions, plus page headers and possible OCR spelling errors). Find and grade ONLY the part "
    "that answers question {number}. Ignore answers to other questions. If no part of the transcript "
    "answers this question, award 0 marks and say the answer was not found. Do not penalize obvious OCR "
    "misspellings of otherwise correct terms."
)


_PER_POINT_HINT = (
    "Grade each rubric criterion (one marking point of the teacher's key) independently: award its marks "
    "when that point is present in the student's answer, part of its marks when it is partly present, and 0 "
    "only when it is absent. The question total is the sum of the criteria."
)

def _lenient_hint(partial_credit: float) -> str:
    """Subject-neutral lenient marking rules (GRADING_LENIENCY=lenient)."""
    partial = (
        f"award {round(partial_credit * 100)}% of its marks, never 0"
        if partial_credit > 0
        else "award part of its marks"
    )
    return (
        "Mark LENIENTLY, like a supportive human examiner: "
        "(1) award full marks for a point when the student conveys its idea in their own words, even if less "
        "detailed, synonymous, or differently phrased than the key; "
        "(2) PARTIAL CREDIT: a marking point usually combines a core idea with specific details (its expected "
        "concepts). If the student conveys the core idea or any one of its expected concepts — in any wording, "
        "including a broader or more general term for the same thing — but not all of the details, the point "
        f"is PARTLY present: {partial}; "
        "(3) for every point, list in matched_concepts the student's words that relate to it, even if only "
        "partly; "
        "(4) do not deduct for missing minor qualifiers, exact figures, spelling, grammar, or OCR errors; "
        "(5) give 0 only when nothing the student wrote relates to the point."
    )

# "- Large hemispherical brick dome (1 mark)" / "* Bas-reliefs ... (2 marks)"
_MARK_POINT = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*(?P<text>.+?)\s*\(\s*(?P<marks>\d+(?:\.\d+)?)\s*marks?\s*\)\s*\.?\s*$", re.I)
_MARK_SECTION = re.compile(r"^\s*(?P<name>key points|marking scheme|marking points|rubric)\s*:?\s*$", re.I)


# Generic English list/relation words that join a point's core idea to its details.
_CONCEPT_SPLIT = re.compile(
    r"\s*(?:[,;]|\band\b|\bdepicting\b|\bshowing\b|\bincluding\b|\bsuch as\b|\bfeaturing\b|\bcontaining\b"
    r"|\bwhich\b|\bthat\b)\s*",
    re.I,
)


def _point_concepts(text: str) -> list[str]:
    """Split a marking point into its component ideas (core idea first, then details) so partial answers
    can be recognized. E.g. "X depicting A, B and C" -> ["X", "A", "B", "C"]."""
    parts = [p.strip(" .:-()") for p in _CONCEPT_SPLIT.split(text)]
    parts = [p for p in parts if len(p) > 2]
    return parts if len(parts) > 1 else [text]


def _rubric_from_mark_scheme(expected: str, total_marks: float) -> Optional[Rubric]:
    """Turn the per-point mark scheme written in a teacher's answer key into rubric criteria.

    Without this the evaluator grades the whole answer as one holistic criterion, and the LLM's single
    number often disagrees with its own point-by-point reasoning. "Key points" lines are preferred
    (atomic, checkable); otherwise "Rubric"/"Marking scheme" lines. Point marks are scaled so they sum
    to the question's marks. Returns None if the key has no per-point marks.
    """
    sections: dict[str, list[tuple[str, float]]] = {}
    current = "_unlabelled"
    for line in expected.splitlines():
        section = _MARK_SECTION.match(line)
        if section:
            current = section.group("name").lower()
            continue
        point = _MARK_POINT.match(line)
        if point and float(point.group("marks")) > 0:
            sections.setdefault(current, []).append((point.group("text").strip(), float(point.group("marks"))))

    points = next(
        (sections[name] for name in ("key points", "marking points", "marking scheme", "rubric", "_unlabelled")
         if sections.get(name)),
        None,
    )
    if not points:
        return None
    points_total = sum(m for _, m in points)
    if points_total >= total_marks:
        # Lenient: each point keeps the marks written next to it; the question total is capped at the
        # question's marks afterwards (e.g. 8 marks of points on a 7-mark question = best 7 of 8).
        marks = [round(m, 2) for _, m in points]
        rubric_total = round(sum(marks), 2)
    else:
        # Under-allocated key: scale up so a complete answer can still earn full marks.
        scale = total_marks / points_total
        marks = [round(m * scale, 2) for _, m in points]
        marks[-1] = round(total_marks - sum(marks[:-1]), 2)  # absorb rounding so criteria sum exactly
        if marks[-1] <= 0:
            return None
        rubric_total = total_marks
    return Rubric(
        criteria=[
            RubricCriterion(
                criterion_id=f"point_{i}",
                description=text,
                max_marks=m,
                expected_concepts=_point_concepts(text),
            )
            for i, ((text, _), m) in enumerate(zip(points, marks), start=1)
        ],
        total_marks=rubric_total,
    )


def _apply_lenient_floor(result: GradingResult, partial_credit: float) -> bool:
    """Lenient rule, enforced in code because the LLM does not apply it reliably: a marking point for
    which the LLM itself found matching evidence earns at least ``partial_credit`` of its marks.

    Returns True if any marks changed.
    """
    changed = False
    if partial_credit <= 0:
        return changed
    for grade in result.question_results:
        raised = False
        for crit in grade.criterion_evaluations:
            floor = round(crit.max_marks * partial_credit, 2)
            if crit.matched_concepts and crit.awarded_marks < floor:
                object.__setattr__(crit, "awarded_marks", floor)
                raised = True
        if raised:
            total = sum(c.awarded_marks for c in grade.criterion_evaluations)
            object.__setattr__(grade, "awarded_marks", round(min(total, grade.max_marks), 2))
            changed = True
    return changed


def _cap_to_question_marks(
    result: GradingResult, question_marks: dict[str, float], partial_credit: float = 0.0
) -> GradingResult:
    """Apply the lenient floor, then cap questions graded on an over-allocated mark scheme at the
    question's real marks, and recompute the totals and summary feedback."""
    changed = _apply_lenient_floor(result, partial_credit)
    for grade in result.question_results:
        real = question_marks.get(grade.question_id)
        if real is not None and grade.max_marks > real + 1e-9:
            # object.__setattr__ bypasses validate_assignment. QuestionGrade re-derives its total from the
            # criteria whenever it is validated (e.g. as the response model), so when the student earned
            # more than the question is worth, trim the criteria proportionally to sum to the cap.
            if grade.awarded_marks > real:
                factor = real / grade.awarded_marks
                for crit in grade.criterion_evaluations:
                    object.__setattr__(crit, "awarded_marks", round(crit.awarded_marks * factor, 2))
            object.__setattr__(grade, "awarded_marks", round(min(grade.awarded_marks, real), 2))
            object.__setattr__(grade, "max_marks", real)
            changed = True
    if not changed:
        return result
    grades = result.question_results
    return GradingResult(
        submission_id=result.submission_id,
        assignment_id=result.assignment_id,
        total_awarded_marks=round(sum(g.awarded_marks for g in grades), 2),
        total_max_marks=round(sum(g.max_marks for g in grades), 2),
        question_results=grades,
        overall_feedback=FeedbackGenerator.generate_overall_feedback(grades),
        review_required=result.review_required,
        review_reasons=result.review_reasons,
        grading_status=result.grading_status,
        rag=result.rag,
    )


def _to_grading_request(body: GradeSubmissionRequest, question: GradeQuestionInput, number: int) -> GradingRequest:
    question_text = question.text
    expected = question.expected_answer
    if question.type == "mcq":
        # The chosen option is written by hand inside the transcript, so it is graded like a short
        # answer against the correct option rather than by option id.
        options = "\n".join(f"{o.get('id')}) {o.get('text')}" for o in question.options)
        question_text = f"{question.text}\nOptions:\n{options}" if options else question.text
        correct = next((o for o in question.options if o.get("id") == question.correct_option_id), None)
        if question.correct_option_id:
            expected = f"Correct option: {question.correct_option_id}" + (f") {correct.get('text')}" if correct else "")
    settings = get_settings()
    instructions = _LOCATE_ANSWER_HINT.format(number=number)
    if settings.grading_leniency == "lenient":
        instructions += "\n" + _lenient_hint(settings.grading_partial_credit)
    rubric = _rubric_from_mark_scheme(expected, question.marks) if expected else None
    if rubric is not None:
        instructions += "\n" + _PER_POINT_HINT
    if question.instructions:
        instructions += f"\n{question.instructions}"
    return GradingRequest(
        rubric=rubric,
        course_id=body.course_id or body.assignment_id,
        assignment_id=body.assignment_id,
        submission_id=body.submission_id,
        question_id=question.question_id,
        question_text=question_text,
        # Over-allocated mark schemes are graded on their own total, then capped (see _cap_to_question_marks).
        question_max_marks=rubric.total_marks if rubric is not None else question.marks,
        student_answer=body.student_text,
        expected_answer=expected,
        instructions=instructions,
        question_type=QuestionType.SUBJECTIVE,
        ocr_confidence=body.ocr_confidence,
    )


_evaluator: Optional[AnswerEvaluator] = None


def get_evaluator() -> AnswerEvaluator:
    global _evaluator
    if _evaluator is None:
        # Evidence comes from the persistent course index (real embeddings), never a mock store.
        _evaluator = AnswerEvaluator(evidence_retriever=IndexEvidenceRetriever())
    return _evaluator


# ---------------------------------------------------------------------------
# Course-material RAG evidence for grading
# ---------------------------------------------------------------------------


def _evidence_query(question: GradeQuestionInput) -> str:
    """Retrieval query: the question plus its answer key (what the notes should support).

    The student's transcript is deliberately not used: it covers every question and OCR noise.
    """
    parts = [question.text]
    if question.expected_answer:
        parts.append(question.expected_answer[:1500])
    if question.type == "mcq":
        parts.extend(str(o.get("text", "")) for o in question.options)
    return "\n".join(p for p in parts if p)


def _retrieve_evidence(body: GradeSubmissionRequest):
    """Retrieve course passages per question.

    Returns (evidence map for the evaluator, per-question status info, RAG summary). Questions without
    usable evidence are mapped to empty evidence so the grader is told explicitly that none exists.
    """
    settings = get_settings()
    course_id = (body.course_id or "").strip()
    evidence: Dict[str, Tuple[List[str], List[SourceReference]]] = {}
    info: Dict[str, Tuple[str, Optional[str], List[SourceReference]]] = {}
    summary: Dict[str, Any] = {
        "course_id": course_id or None,
        "similarity_threshold": settings.rag_min_similarity,
        "top_k": settings.rag_top_k,
    }

    index = get_course_index()
    reason: Optional[str] = None
    if not course_id:
        reason = "This assignment is not linked to a course, so there are no course materials to search."
    else:
        summary["materials_indexed"] = len(index.list_materials(course_id))
        summary["chunks_indexed"] = index.store.chunk_count(course_id)
        if summary["chunks_indexed"] == 0:
            reason = "No course materials have been indexed for this course yet."

    builder = ContextBuilder()
    for question in body.questions:
        chunks = []
        q_reason = reason
        if q_reason is None:
            try:
                chunks = index.retrieve(
                    course_id, _evidence_query(question),
                    top_k=settings.rag_top_k, similarity_threshold=settings.rag_min_similarity,
                )
                summary["embedding_model"] = index.embedding_model
                if not chunks:
                    q_reason = (
                        "No passage in this course's materials was relevant enough to this question "
                        f"(similarity below {settings.rag_min_similarity})."
                    )
            except EmbeddingsUnavailableError as exc:
                q_reason = f"Semantic search is unavailable: {exc}."
        refs = builder.to_source_references(chunks)
        evidence[question.question_id] = (builder.extract_snippets_for_prompts(chunks), refs)
        info[question.question_id] = ("available" if chunks else "unavailable", q_reason, refs)

    with_evidence = sum(1 for status_, _, _ in info.values() if status_ == "available")
    summary["questions_with_evidence"] = with_evidence
    summary["status"] = (
        "available" if with_evidence == len(info) else "partial" if with_evidence else "unavailable"
    )
    if reason:
        summary["reason"] = reason
    return evidence, info, summary


def _attach_evidence(result: GradingResult, info, summary: Dict[str, Any]) -> None:
    for grade in result.question_results:
        status_, reason, refs = info.get(grade.question_id, ("not_requested", None, []))
        # object.__setattr__ bypasses validate_assignment (which would re-run total validation).
        object.__setattr__(grade, "evidence_status", status_)
        object.__setattr__(grade, "evidence_unavailable_reason", reason)
        object.__setattr__(grade, "evidence", refs)
    object.__setattr__(result, "rag", summary)


_generator: Optional[AssignmentGenerator] = None


def get_generator() -> AssignmentGenerator:
    """Lazily create the generator so the service starts even before any LLM is configured."""
    global _generator
    if _generator is None:
        _generator = AssignmentGenerator()
    return _generator


@app.get("/health")
def health() -> dict:
    chain = get_llm_client().describe()
    index = get_course_index()
    return {
        "status": "ok" if chain else "degraded",
        "gemini_configured": any(label.startswith("gemini:") for label in chain),
        "model": chain[0] if chain else None,
        "providers": chain,  # tried in this order, e.g. ["openrouter:google/gemma-4-31b-it:free", "gemini:gemini-2.5-flash"]
        "rag": {
            "embeddings_installed": importlib.util.find_spec("sentence_transformers") is not None,
            "embedding_model": index.embedding_model,
            "index_dir": str(index.store.root),
            "persistent": True,
        },
    }


# ---------------------------------------------------------------------------
# Course-material ingestion (called by the backend after it authorizes the teacher)
# ---------------------------------------------------------------------------


class MaterialPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str = Field(max_length=200_000)


class IndexMaterialRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=100)
    filename: str = Field(min_length=1, max_length=255)
    material_id: Optional[str] = Field(default=None, max_length=100)
    pages: List[MaterialPage] = Field(min_length=1, max_length=1000)


class SearchMaterialsRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=5000)
    top_k: int = Field(default=4, ge=1, le=20)
    similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0)


@app.post("/v1/materials/index")
def index_material(body: IndexMaterialRequest) -> dict:
    """Chunk, embed (all-MiniLM-L6-v2) and persist extracted course-material pages for one course.

    Re-uploading identical content returns ``duplicate: true`` and adds no chunks.
    """
    try:
        return get_course_index().index_material(
            course_id=body.course_id,
            filename=body.filename,
            pages=[p.model_dump() for p in body.pages],
            material_id=body.material_id,
        )
    except EmbeddingsUnavailableError as exc:
        logger.error("Cannot index course material: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Semantic embeddings unavailable: {exc}") from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None


@app.get("/v1/materials")
def list_materials(course_id: str) -> dict:
    index = get_course_index()
    return {
        "course_id": course_id,
        "materials": index.list_materials(course_id),
        "chunk_count": index.store.chunk_count(course_id),
        "embedding_model": index.embedding_model,
    }


@app.delete("/v1/materials/{material_id}")
def delete_material(material_id: str, course_id: str) -> dict:
    index = get_course_index()
    if material_id not in {m["material_id"] for m in index.list_materials(course_id)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material not found for this course.")
    return {"course_id": course_id, "material_id": material_id, "deleted_chunks": index.delete_material(course_id, material_id)}


@app.post("/v1/materials/search")
def search_materials(body: SearchMaterialsRequest) -> dict:
    """Debug/inspection: top course passages for a query (course-isolated)."""
    try:
        chunks = get_course_index().retrieve(
            body.course_id, body.query, top_k=body.top_k, similarity_threshold=body.similarity_threshold
        )
    except EmbeddingsUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Semantic embeddings unavailable: {exc}") from None
    return {
        "course_id": body.course_id,
        "results": [
            {
                "material_id": c.document_id,
                "filename": c.title,
                "page_number": c.page_number,
                "similarity": c.similarity_score,
                "content": c.text,
            }
            for c in chunks
        ],
    }


@app.post("/v1/assignments/generate", response_model=AssignmentDraft)
def generate_assignment(request: GenerateAssignmentRequest) -> AssignmentDraft:
    # Sync handler: FastAPI runs it in a worker thread, so slow Gemini calls don't block the loop.
    generation_request = AssignmentGenerationRequest.model_validate(
        request.model_dump(exclude={"course_materials"})
    )
    try:
        return get_generator().generate_assignment(generation_request, course_materials=request.course_materials)
    except LLMConfigError as exc:
        logger.error("No LLM provider is configured: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI generation is not configured.") from None
    except LLMRateLimitError:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "All AI providers are rate limited or out of quota. Try again later."
        ) from None
    except LLMTimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "All AI providers timed out.") from None
    except LLMResponseValidationError:
        logger.warning("LLM returned output that failed schema validation")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI provider returned an unusable response.") from None
    except (LLMAPIError, LLMError) as exc:
        logger.error("LLM request failed: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI provider request failed.") from None


@app.post("/v1/grading/grade-submission", response_model=GradingResult)
def grade_submission(body: GradeSubmissionRequest) -> GradingResult:
    """Suggest marks per question by comparing the OCR transcript with the teacher's answer keys.

    The result is a suggestion for teacher review, never a final grade.
    """
    requests = [_to_grading_request(body, q, i) for i, q in enumerate(body.questions, start=1)]
    evidence, evidence_info, rag_summary = _retrieve_evidence(body)
    try:
        result = get_evaluator().grade_submission(
            body.submission_id, body.assignment_id, requests, evidence=evidence
        )
        _attach_evidence(result, evidence_info, rag_summary)
        settings = get_settings()
        partial_credit = settings.grading_partial_credit if settings.grading_leniency == "lenient" else 0.0
        return _cap_to_question_marks(result, {q.question_id: q.marks for q in body.questions}, partial_credit)
    except LLMConfigError as exc:
        logger.error("No LLM provider is configured: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI grading is not configured.") from None
    except LLMRateLimitError:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "All AI providers are rate limited or out of quota. Try again later."
        ) from None
    except LLMTimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "All AI providers timed out.") from None
    except LLMResponseValidationError:
        logger.warning("LLM returned grading output that failed schema validation")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI provider returned an unusable response.") from None
    except (LLMAPIError, LLMError) as exc:
        logger.error("LLM grading request failed: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI provider request failed.") from None
