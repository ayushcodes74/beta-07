"""Unit tests for Module 3A: Syllabus Detection."""

from unittest.mock import MagicMock
import pytest

from app.syllabus.detector import SyllabusDetector
from app.schemas.assignment import SyllabusCoverageResult, SyllabusCoverageStatus
from app.schemas.common import SourceReference
from app.schemas.rag import RetrievedChunk


def test_detect_coverage_empty_question_raises():
    """Test that empty question text raises ValueError."""
    detector = SyllabusDetector(gemini_client=MagicMock())
    with pytest.raises(ValueError, match="Question cannot be empty"):
        detector.detect_coverage(question="", course_id="CS101")


def test_detect_coverage_insufficient_evidence_returns_uncertain():
    """Test that absence of course materials and syllabus returns UNCERTAIN without LLM call."""
    mock_client = MagicMock()
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value.chunks = []

    detector = SyllabusDetector(gemini_client=mock_client, retriever=mock_retriever)
    result = detector.detect_coverage(
        question="What is an AVL tree rotation?",
        course_id="CS201",
        retrieved_evidence=None,
        syllabus_text=None,
    )

    assert result.status == SyllabusCoverageStatus.UNCERTAIN
    assert result.confidence == 0.0
    assert "insufficient evidence" in result.reasoning.lower()
    # LLM should not have been called
    mock_client.generate_structured.assert_not_called()


def test_detect_coverage_in_syllabus():
    """Test question fully covered by syllabus material."""
    mock_client = MagicMock()
    expected_result = SyllabusCoverageResult(
        status=SyllabusCoverageStatus.IN_SYLLABUS,
        confidence=0.95,
        covered_concepts=["Process Scheduling", "Round Robin", "Time Quantum"],
        uncovered_concepts=[],
        reasoning="Topic is explicitly listed under Unit 2 CPU Scheduling.",
    )
    mock_client.generate_structured.return_value = expected_result

    evidence_chunk = RetrievedChunk(
        chunk_id="c1",
        course_id="CS101",
        document_id="syllabus_doc",
        title="CS101 Syllabus",
        page_number=2,
        section="Unit 2: CPU Scheduling",
        text="Unit 2 covers FCFS, SJF, and Round Robin scheduling algorithms.",
        similarity_score=0.92,
    )

    detector = SyllabusDetector(gemini_client=mock_client)
    res = detector.detect_coverage(
        question="Explain how the Round Robin scheduling algorithm handles time quantum.",
        course_id="CS101",
        retrieved_evidence=[evidence_chunk],
        syllabus_text="Unit 2: CPU Scheduling and Round Robin.",
    )

    assert res.status == SyllabusCoverageStatus.IN_SYLLABUS
    assert res.confidence == 0.95
    assert "Round Robin" in res.covered_concepts
    assert len(res.evidence) == 1
    assert res.evidence[0].document_id == "syllabus_doc"


def test_detect_coverage_partially_in_syllabus():
    """Test multi-concept question where only some concepts are covered."""
    mock_client = MagicMock()
    expected_result = SyllabusCoverageResult(
        status=SyllabusCoverageStatus.PARTIALLY_IN_SYLLABUS,
        confidence=0.85,
        covered_concepts=["Binary Search Trees"],
        uncovered_concepts=["Red-Black Trees", "Tree Rotations"],
        reasoning="BST is covered in Unit 3, but advanced balanced trees (Red-Black) are not.",
    )
    mock_client.generate_structured.return_value = expected_result

    detector = SyllabusDetector(gemini_client=mock_client)
    res = detector.detect_coverage(
        question="Compare binary search tree lookup with Red-Black tree rebalancing.",
        course_id="CS102",
        syllabus_text="Unit 3: Elementary Data Structures (Stacks, Queues, BSTs).",
    )

    assert res.status == SyllabusCoverageStatus.PARTIALLY_IN_SYLLABUS
    assert "Binary Search Trees" in res.covered_concepts
    assert "Red-Black Trees" in res.uncovered_concepts


def test_detect_coverage_out_of_syllabus():
    """Test question completely outside the supplied syllabus."""
    mock_client = MagicMock()
    expected_result = SyllabusCoverageResult(
        status=SyllabusCoverageStatus.OUT_OF_SYLLABUS,
        confidence=0.98,
        covered_concepts=[],
        uncovered_concepts=["Quantum Fourier Transform", "Qubits"],
        reasoning="Course covers classical algorithms; quantum mechanics is completely absent.",
    )
    mock_client.generate_structured.return_value = expected_result

    detector = SyllabusDetector(gemini_client=mock_client)
    res = detector.detect_coverage(
        question="Implement Quantum Fourier Transform using Hadamard gates.",
        course_id="CS101",
        syllabus_text="Unit 1: Python Basics. Unit 2: Loops and Functions.",
    )

    assert res.status == SyllabusCoverageStatus.OUT_OF_SYLLABUS
    assert len(res.covered_concepts) == 0
    assert "Quantum Fourier Transform" in res.uncovered_concepts

