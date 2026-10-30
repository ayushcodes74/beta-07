"""Unit tests for Module 4: AI Grading and Feedback."""

from unittest.mock import MagicMock
import pytest

from app.grading.evidence_retriever import GradingEvidenceRetriever, EvidenceRetrievalResult
from app.grading.feedback_generator import FeedbackGenerator
from app.grading.evaluator import AnswerEvaluator, _LLMQuestionGradeResponse, _LLMCriterionEvaluation
from app.schemas.assignment import ModelAnswer, Rubric, RubricCriterion
from app.schemas.common import SourceReference
from app.schemas.grading import (
    CriterionEvaluation,
    GradingRequest,
    GradingResult,
    GradingStatus,
    QuestionGrade,
)
from app.schemas.rag import RetrievedChunk


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_rubric() -> Rubric:
    return Rubric(
        total_marks=10.0,
        criteria=[
            RubricCriterion(
                criterion_id="crit_1",
                description="Define deadlock concept.",
                max_marks=4.0,
                expected_concepts=["Resource blocking", "Processes waiting indefinitely"],
                acceptable_alternatives=["Permanent block of execution"],
            ),
            RubricCriterion(
                criterion_id="crit_2",
                description="List Coffman conditions.",
                max_marks=6.0,
                expected_concepts=["Mutual exclusion", "Hold and wait", "No preemption", "Circular wait"],
                acceptable_alternatives=["Four necessary conditions"],
            ),
        ],
    )


@pytest.fixture
def sample_grading_request(sample_rubric) -> GradingRequest:
    return GradingRequest(
        course_id="CS101",
        assignment_id="asgn_1",
        submission_id="sub_101",
        question_id="q_1",
        question_text="Define deadlock and explain the four Coffman conditions.",
        question_max_marks=10.0,
        student_answer="Deadlock occurs when processes are permanently waiting for resources held by each other. The conditions are mutual exclusion, hold & wait, no preemption, and circular wait.",
        rubric=sample_rubric,
        model_answer=ModelAnswer(
            text="A deadlock is a situation where a set of processes are blocked because each process is holding a resource and waiting for another resource acquired by some other process. Conditions: Mutual Exclusion, Hold and Wait, No Preemption, Circular Wait.",
            key_points=["Permanent blocking", "4 Coffman conditions"],
        ),
    )


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------

def test_criterion_evaluation_marks_validation():
    """Test that awarded marks cannot exceed max_marks."""
    with pytest.raises(ValueError, match="awarded_marks .* cannot exceed max_marks"):
        CriterionEvaluation(
            criterion_id="c1",
            max_marks=5.0,
            awarded_marks=6.5,
            explanation="Invalid",
        )


def test_grading_result_percentage_and_status():
    """Test that percentage is calculated and status updates to NEEDS_REVIEW when flagged."""
    res = GradingResult(
        submission_id="sub_1",
        assignment_id="asgn_1",
        total_awarded_marks=15.0,
        total_max_marks=20.0,
        question_results=[
            QuestionGrade(
                question_id="q1",
                max_marks=20.0,
                awarded_marks=15.0,
                criterion_evaluations=[
                    CriterionEvaluation(criterion_id="c1", max_marks=20.0, awarded_marks=15.0, explanation="Good")
                ],
                overall_explanation="Good effort.",
                review_required=True,
                review_reasons=["Unusual derivation"],
            )
        ],
        overall_feedback="Well done.",
        review_required=True,
    )

    assert res.percentage == 75.0
    assert res.grading_status == GradingStatus.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# Evidence Retriever Tests
# ---------------------------------------------------------------------------

def test_evidence_retriever_course_isolation():
    """Test evidence retrieval strictly passes course_id and formats context."""
    mock_rag_retriever = MagicMock()
    mock_rag_retriever.retrieve.return_value.chunks = [
        RetrievedChunk(
            chunk_id="chunk_1",
            course_id="CS101",
            document_id="textbook_ch7",
            title="OS Book",
            page_number=140,
            section="Deadlocks",
            text="Deadlock is a state in which each process is waiting for an event that only another process can cause.",
            similarity_score=0.91,
        )
    ]

    retriever = GradingEvidenceRetriever(retriever=mock_rag_retriever)
    result = retriever.retrieve_evidence_for_grading(
        course_id="CS101",
        question_text="What is a deadlock?",
    )

    assert result.has_sufficient_evidence is True
    assert len(result.source_references) == 1
    assert result.source_references[0].document_id == "textbook_ch7"
    assert "Deadlock is a state" in result.course_context


def test_evidence_retriever_insufficient_evidence():
    """Test retriever flags insufficient evidence when no chunks meet threshold."""
    mock_rag_retriever = MagicMock()
    mock_rag_retriever.retrieve.return_value.chunks = []

    retriever = GradingEvidenceRetriever(retriever=mock_rag_retriever)
    result = retriever.retrieve_evidence_for_grading(
        course_id="CS101",
        question_text="Exotic topic not in course notes.",
    )

    assert result.has_sufficient_evidence is False
    assert len(result.source_references) == 0
    assert "No relevant course material found" in result.course_context


# ---------------------------------------------------------------------------
# Feedback Generator Tests
# ---------------------------------------------------------------------------

def test_feedback_generator_question_breakdown():
    """Test question feedback reflects score, strengths, and deduction reasons."""
    evals = [
        CriterionEvaluation(
            criterion_id="c1",
            criterion_name="Definition",
            max_marks=4.0,
            awarded_marks=4.0,
            explanation="Clear explanation of deadlocks.",
            matched_concepts=["Resource blocking"],
        ),
        CriterionEvaluation(
            criterion_id="c2",
            criterion_name="Conditions",
            max_marks=6.0,
            awarded_marks=3.0,
            explanation="Mentioned 2 of 4 conditions.",
            matched_concepts=["Mutual exclusion", "Hold and wait"],
            missing_concepts=["No preemption", "Circular wait"],
        ),
    ]

    feedback = FeedbackGenerator.generate_question_feedback(
        question_id="Q1",
        max_marks=10.0,
        awarded_marks=7.0,
        criterion_evaluations=evals,
        overall_explanation="Good understanding of definition, incomplete conditions.",
    )

    assert "Good answer on Question Q1" in feedback
    assert "(-3.0 marks): Mentioned 2 of 4 conditions" in feedback
    assert "Missing: No preemption, Circular wait" in feedback
    assert "**Concepts Demonstrated:** Hold and wait, Mutual exclusion, Resource blocking" in feedback


# ---------------------------------------------------------------------------
# Semantic Evaluator Tests
# ---------------------------------------------------------------------------

def test_evaluate_question_partial_credit(sample_grading_request):
    """Test semantic evaluator awards partial credit and explains missing concepts."""
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = _LLMQuestionGradeResponse(
        awarded_marks=8.0,
        overall_explanation="The student accurately defines deadlock and lists 3 out of 4 conditions.",
        strengths=["Clear conceptual definition", "Identified primary Coffman conditions"],
        areas_for_improvement=["Remember to include circular wait"],
        confidence=0.92,
        review_required=False,
        criterion_evaluations=[
            _LLMCriterionEvaluation(
                criterion_id="crit_1",
                criterion_name="Define deadlock",
                awarded_marks=4.0,
                max_marks=4.0,
                explanation="Fully defined using equivalent wording.",
                matched_concepts=["Processes permanently waiting"],
                missing_concepts=[],
            ),
            _LLMCriterionEvaluation(
                criterion_id="crit_2",
                criterion_name="List Coffman conditions",
                awarded_marks=4.0,
                max_marks=6.0,
                explanation="Missed circular wait condition.",
                matched_concepts=["Mutual exclusion", "Hold and wait", "No preemption"],
                missing_concepts=["Circular wait"],
            ),
        ],
    )

    mock_ev_retriever = MagicMock()
    mock_ev_retriever.retrieve_evidence_for_grading.return_value = EvidenceRetrievalResult(
        course_context="Course chapter on deadlocks.",
        evidence_snippets=["Deadlocks require 4 Coffman conditions."],
        source_references=[],
        has_sufficient_evidence=True,
        retrieved_chunks=[],
    )

    evaluator = AnswerEvaluator(
        gemini_client=mock_client,
        evidence_retriever=mock_ev_retriever,
    )

    result = evaluator.evaluate_question(sample_grading_request)

    assert isinstance(result, QuestionGrade)
    assert result.awarded_marks == 8.0
    assert result.max_marks == 10.0
    assert len(result.criterion_evaluations) == 2
    assert result.criterion_evaluations[0].awarded_marks == 4.0
    assert result.criterion_evaluations[1].awarded_marks == 4.0
    assert "Circular wait" in result.criterion_evaluations[1].missing_concepts


def test_evaluate_question_empty_answer(sample_grading_request):
    """Test that empty student answer receives 0 marks without invoking LLM."""
    mock_client = MagicMock()
    evaluator = AnswerEvaluator(gemini_client=mock_client)

    empty_req = sample_grading_request.model_copy(update={"student_answer": "   "})
    result = evaluator.evaluate_question(empty_req)

    assert result.awarded_marks == 0.0
    assert all(c.awarded_marks == 0.0 for c in result.criterion_evaluations)
    assert "No answer was submitted" in result.overall_explanation
    # LLM should not be called for empty submissions
    mock_client.generate_structured.assert_not_called()


def test_insufficient_evidence_flags_human_review(sample_grading_request):
    """Test that lack of course evidence automatically flags submission for teacher review."""
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = _LLMQuestionGradeResponse(
        awarded_marks=5.0,
        overall_explanation="Answer seems plausible but unverified.",
        confidence=0.5,
        review_required=False,
        criterion_evaluations=[
            _LLMCriterionEvaluation(
                criterion_id="crit_1",
                awarded_marks=2.0,
                max_marks=4.0,
                explanation="Plausible claim.",
            ),
            _LLMCriterionEvaluation(
                criterion_id="crit_2",
                awarded_marks=3.0,
                max_marks=6.0,
                explanation="Plausible claim.",
            ),
        ],
    )

    # Retriever reports insufficient evidence
    mock_ev_retriever = MagicMock()
    mock_ev_retriever.retrieve_evidence_for_grading.return_value = EvidenceRetrievalResult(
        course_context="No course material found.",
        evidence_snippets=[],
        source_references=[],
        has_sufficient_evidence=False,
        retrieved_chunks=[],
    )

    evaluator = AnswerEvaluator(
        gemini_client=mock_client,
        evidence_retriever=mock_ev_retriever,
    )

    grade = evaluator.evaluate_question(sample_grading_request)
    assert grade.review_required is True
    assert any("insufficient" in r.lower() for r in grade.review_reasons)


def test_grade_multi_question_submission(sample_grading_request):
    """Test full multi-question submission grading pipeline."""
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = _LLMQuestionGradeResponse(
        awarded_marks=9.0,
        overall_explanation="Excellent answer.",
        confidence=0.95,
        review_required=False,
        criterion_evaluations=[
            _LLMCriterionEvaluation(criterion_id="crit_1", awarded_marks=4.0, max_marks=4.0, explanation="Full"),
            _LLMCriterionEvaluation(criterion_id="crit_2", awarded_marks=5.0, max_marks=6.0, explanation="Near full"),
        ],
    )

    mock_ev = MagicMock()
    mock_ev.retrieve_evidence_for_grading.return_value = EvidenceRetrievalResult(
        course_context="Context",
        evidence_snippets=["Snippet"],
        source_references=[SourceReference(document_id="d1", snippet="Snippet", similarity_score=0.92)],
        has_sufficient_evidence=True,
        retrieved_chunks=[],
    )

    evaluator = AnswerEvaluator(gemini_client=mock_client, evidence_retriever=mock_ev)

    sub_result = evaluator.grade_submission(
        submission_id="sub_999",
        assignment_id="asgn_1",
        requests=[sample_grading_request],
    )

    assert isinstance(sub_result, GradingResult)
    assert sub_result.submission_id == "sub_999"
    assert sub_result.total_awarded_marks == 9.0
    assert sub_result.total_max_marks == 10.0
    assert sub_result.percentage == 90.0
    assert sub_result.grading_status == GradingStatus.COMPLETED
    assert not sub_result.review_required
