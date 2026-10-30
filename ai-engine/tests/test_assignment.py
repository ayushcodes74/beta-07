"""Unit tests for Module 3B & 3C: Assignment and Rubric Generation."""

from unittest.mock import MagicMock
import pytest

from app.assignment.generator import AssignmentGenerator, _GeneratedAssignmentResponse, _GeneratedQuestion
from app.assignment.rubric_generator import RubricGenerator, _RawRubricResponse
from app.schemas.assignment import (
    AssignmentDraft,
    AssignmentGenerationRequest,
    DifficultyLevel,
    MCQOption,
    QuestionDraft,
    QuestionType,
    Rubric,
    RubricCriterion,
)


# ---------------------------------------------------------------------------
# Rubric Generator Tests
# ---------------------------------------------------------------------------

def test_rubric_generator_success():
    """Test generating rubric where criteria sum matches max_marks."""
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = _RawRubricResponse(
        instructions="Grade objectively.",
        criteria=[
            RubricCriterion(
                criterion_id="crit_1",
                description="Define deadlock conditions.",
                max_marks=4.0,
                expected_concepts=["Mutual exclusion", "Hold and wait"],
                acceptable_alternatives=["Coffman conditions"],
            ),
            RubricCriterion(
                criterion_id="crit_2",
                description="Explain avoidance technique.",
                max_marks=6.0,
                expected_concepts=["Banker's algorithm", "Safe state"],
                acceptable_alternatives=["Resource allocation graph"],
            ),
        ],
    )

    gen = RubricGenerator(gemini_client=mock_client)
    rubric = gen.generate_rubric(
        question_text="Explain deadlock prevention and avoidance.",
        max_marks=10.0,
        course_context="Chapter 7 Operating Systems: Deadlocks.",
    )

    assert isinstance(rubric, Rubric)
    assert rubric.total_marks == 10.0
    assert len(rubric.criteria) == 2
    assert sum(c.max_marks for c in rubric.criteria) == 10.0


def test_rubric_generator_reconciliation_on_rounding_difference():
    """Test automatic mark reconciliation when LLM outputs criteria that don't sum to max_marks."""
    mock_client = MagicMock()
    # LLM outputs 3.0 + 5.0 = 8.0, but max_marks is 10.0
    mock_client.generate_structured.return_value = _RawRubricResponse(
        criteria=[
            RubricCriterion(criterion_id="c1", description="Part 1", max_marks=3.0),
            RubricCriterion(criterion_id="c2", description="Part 2", max_marks=5.0),
        ],
    )

    gen = RubricGenerator(gemini_client=mock_client)
    rubric = gen.generate_rubric(
        question_text="Explain TCP handshake.",
        max_marks=10.0,
        course_context="Networking text",
    )

    assert rubric.total_marks == 10.0
    assert sum(c.max_marks for c in rubric.criteria) == 10.0


def test_rubric_generator_invalid_max_marks():
    """Test that zero or negative max_marks raises ValueError."""
    gen = RubricGenerator(gemini_client=MagicMock())
    with pytest.raises(ValueError, match="max_marks must be greater than 0"):
        gen.generate_rubric(question_text="Valid question", max_marks=-5.0, course_context="Context")


# ---------------------------------------------------------------------------
# Assignment Generator Tests
# ---------------------------------------------------------------------------

def test_generate_assignment_mcq_and_subjective():
    """Test generating a mixed assignment with MCQs and subjective questions."""
    mock_client = MagicMock()

    # Mock response from LLM
    mock_llm_assignment = _GeneratedAssignmentResponse(
        title="Operating Systems Quiz 1",
        instructions="Answer all questions in 45 minutes.",
        questions=[
            _GeneratedQuestion(
                question_text="Which CPU scheduling algorithm can lead to starvation?",
                question_type=QuestionType.MCQ,
                marks=5.0,
                difficulty=DifficultyLevel.EASY,
                learning_objective="Understand scheduling limitations",
                mcq_options=[
                    MCQOption(id="A", text="Round Robin", is_correct=False, explanation="RR uses time slicing preventing starvation."),
                    MCQOption(id="B", text="Shortest Job First (SJF)", is_correct=True, explanation="Long jobs may starve if short jobs keep arriving."),
                    MCQOption(id="C", text="First-Come, First-Served", is_correct=False, explanation="FCFS does not starve."),
                    MCQOption(id="D", text="None of the above", is_correct=False),
                ],
            ),
            _GeneratedQuestion(
                question_text="Describe the four necessary Coffman conditions for a deadlock.",
                question_type=QuestionType.SUBJECTIVE,
                marks=5.0,
                difficulty=DifficultyLevel.MEDIUM,
                learning_objective="Recall deadlock prerequisites",
                model_answer_text="Mutual exclusion, Hold & wait, No preemption, Circular wait.",
                key_points=["Mutual exclusion", "Hold and wait", "No preemption", "Circular wait"],
            ),
        ],
    )
    mock_client.generate_structured.return_value = mock_llm_assignment

    # Mock rubric generator
    mock_rubric_gen = MagicMock()
    mock_rubric_gen.generate_rubric.return_value = Rubric(
        total_marks=5.0,
        criteria=[
            RubricCriterion(criterion_id="rc1", description="4 conditions", max_marks=5.0),
        ],
    )

    generator = AssignmentGenerator(
        gemini_client=mock_client,
        rubric_generator=mock_rubric_gen,
    )

    request = AssignmentGenerationRequest(
        course_id="CS101",
        topic="CPU Scheduling and Deadlocks",
        question_type=QuestionType.MIXED,
        question_count=2,
        total_marks=10.0,
    )

    draft = generator.generate_assignment(
        request=request,
        course_materials="OS Textbook excerpts covering scheduling and Coffman conditions.",
    )

    assert isinstance(draft, AssignmentDraft)
    # Draft status requirement
    assert draft.status == "DRAFT"
    assert draft.course_id == "CS101"
    assert draft.topic == "CPU Scheduling and Deadlocks"
    assert draft.total_marks == 10.0
    assert len(draft.questions) == 2

    # Check MCQ
    mcq = draft.questions[0]
    assert mcq.question_type == QuestionType.MCQ
    assert len(mcq.mcq_options) == 4
    assert sum(1 for o in mcq.mcq_options if o.is_correct) == 1

    # Check Subjective
    subj = draft.questions[1]
    assert subj.question_type == QuestionType.SUBJECTIVE
    assert subj.model_answer is not None
    assert subj.rubric is not None


def test_assignment_draft_enforces_draft_status():
    """Test that AssignmentDraft strictly rejects non-DRAFT status."""
    with pytest.raises(ValueError, match="All freshly generated assignments must have status='DRAFT'"):
        AssignmentDraft(
            assignment_id="a1",
            course_id="CS101",
            topic="Test",
            title="Test",
            total_marks=10.0,
            status="PUBLISHED",
            questions=[
                QuestionDraft(
                    question_id="q1",
                    question_type=QuestionType.SUBJECTIVE,
                    question_text="Explain x",
                    marks=10.0,
                )
            ],
        )


def test_assignment_deduplication():
    """Test duplicate questions are automatically filtered out."""
    q1 = _GeneratedQuestion(
        question_text="What is virtual memory and paging?",
        question_type=QuestionType.SUBJECTIVE,
        marks=5.0,
        difficulty=DifficultyLevel.MEDIUM,
    )
    # Identical question with different casing and spacing
    q2 = _GeneratedQuestion(
        question_text="  WHAT is virtual   memory and paging?  ",
        question_type=QuestionType.SUBJECTIVE,
        marks=5.0,
        difficulty=DifficultyLevel.MEDIUM,
    )
    q3 = _GeneratedQuestion(
        question_text="What is a translation lookaside buffer (TLB)?",
        question_type=QuestionType.SUBJECTIVE,
        marks=5.0,
        difficulty=DifficultyLevel.HARD,
    )

    unique = AssignmentGenerator._deduplicate_questions([q1, q2, q3])
    assert len(unique) == 2
    assert unique[0].question_text == q1.question_text
    assert unique[1].question_text == q3.question_text


def test_teacher_editing():
    """Test teacher editing draft assignment questions and recalculating total marks."""
    assignment = AssignmentDraft(
        assignment_id="asgn_1",
        course_id="CS101",
        topic="Databases",
        title="SQL Basics",
        total_marks=10.0,
        status="DRAFT",
        questions=[
            QuestionDraft(
                question_id="q_1",
                question_type=QuestionType.SUBJECTIVE,
                question_text="What is 1NF?",
                marks=5.0,
            ),
            QuestionDraft(
                question_id="q_2",
                question_type=QuestionType.SUBJECTIVE,
                question_text="What is 2NF?",
                marks=5.0,
            ),
        ],
    )

    # Teacher modifies question 1 marks from 5.0 to 7.0 and updates question text
    updated = AssignmentGenerator.edit_question(
        assignment=assignment,
        question_id="q_1",
        question_text="Explain First Normal Form (1NF) with an example.",
        marks=7.0,
    )

    assert updated.questions[0].marks == 7.0
    assert updated.questions[0].question_text == "Explain First Normal Form (1NF) with an example."
    assert updated.total_marks == 12.0  # 7.0 + 5.0

