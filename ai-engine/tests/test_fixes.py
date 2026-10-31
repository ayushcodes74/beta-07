"""Comprehensive test suite for AI Engine Critical Fixes.

Covers:
- FIX 1: Empty OCR output protection (Genuine blank vs OCR extraction failure)
- FIX 2: Optional rubric compatibility (Rubric, Expected-answer-only, Instructions-only, No guidance)
- FIX 3: Deterministic MCQ grading (Bypasses Gemini, strict matching, safe explanations)
- FIX 4: OCR confidence safeguards (Boundary tests: 0.0, 0.35, 0.49, 0.50, 0.59, 0.60, 1.0, None)
- FIX 5: Asynchronous execution compatibility (async_evaluate_question, async_grade_submission)
- FIX 6: Additional quality improvements (LaTeX boundary protection in chunker, retry exhaustion)
"""

import asyncio
import json
from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError

from app.grading.evaluator import AnswerEvaluator
from app.llm.gemini_client import GeminiClient, LLMRateLimitError, LLMResponseValidationError
from app.rag.chunker import TextChunker
from app.schemas.assignment import ModelAnswer, QuestionType, Rubric, RubricCriterion
from app.schemas.common import SourceReference
from app.schemas.grading import CriterionEvaluation, GradingRequest, QuestionGrade
from app.trust.confidence import ConfidenceEstimator


def _make_mock_client(response_dict: dict) -> GeminiClient:
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = None
    mock_response.text = json.dumps(response_dict)
    mock_genai_client.models.generate_content.return_value = mock_response
    return GeminiClient(api_key="test-key", client=mock_genai_client)


@pytest.fixture
def sample_evidence():
    return [
        SourceReference(
            document_id="doc_test_1",
            title="Course Notes",
            snippet="Newton's second law is F = ma.",
            similarity_score=0.90,
        )
    ]


# ===========================================================================
# FIX 1: Empty OCR Output Protection Tests
# ===========================================================================

class TestFix1EmptyOcrProtection:
    """Verifies Case A (genuine blank) vs Case B (OCR extraction failure)."""

    def test_case_a_genuine_blank_no_ocr(self):
        """When OCR was not involved and student submitted empty text, award 0 with 1.0 confidence."""
        req = GradingRequest(
            course_id="CS101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="Explain recursion.",
            question_max_marks=5.0,
            student_answer="",
        )
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client({}))
        grade = evaluator.evaluate_question(req, ocr_confidence=None)

        assert grade.awarded_marks == 0.0
        assert grade.max_marks == 5.0
        assert grade.confidence == 1.0
        assert grade.review_required is False
        assert "No answer was submitted" in grade.overall_explanation

    def test_case_a_genuine_blank_high_ocr_confidence(self):
        """When OCR establishes with high confidence (>= 0.70) that page is blank."""
        req = GradingRequest(
            course_id="CS101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="Explain recursion.",
            question_max_marks=5.0,
            student_answer="   ",
        )
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client({}))
        grade = evaluator.evaluate_question(req, ocr_confidence=0.95)

        assert grade.awarded_marks == 0.0
        assert grade.confidence == 1.0
        assert grade.review_required is False
        assert "No answer was submitted" in grade.overall_explanation

    def test_case_b_failed_ocr_low_confidence_flags_review(self):
        """When OCR output is empty but OCR confidence is low (< 0.70), flag for teacher review."""
        req = GradingRequest(
            course_id="CS101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="Explain recursion.",
            question_max_marks=5.0,
            student_answer="",
            ocr_confidence=0.35,
        )
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client({}))
        grade = evaluator.evaluate_question(req)

        assert grade.awarded_marks == 0.0
        assert grade.confidence <= 0.50
        assert grade.confidence > 0.0
        assert grade.review_required is True
        assert any("ocr extraction failure" in r.lower() for r in grade.review_reasons)
        # The summary must say OCR failed rather than treating the answer as genuinely blank.
        explanation = grade.overall_explanation.lower()
        assert "ocr" in explanation and "could not be verified as intentionally blank" in explanation

    def test_case_b_failed_ocr_via_method_argument(self):
        """OCR confidence passed via method argument triggers extraction failure review."""
        req = GradingRequest(
            course_id="CS101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="Explain recursion.",
            question_max_marks=5.0,
            student_answer="",
        )
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client({}))
        grade = evaluator.evaluate_question(req, ocr_confidence=0.45)

        assert grade.review_required is True
        assert grade.confidence <= 0.50
        assert any("0.45" in r for r in grade.review_reasons)


# ===========================================================================
# FIX 2: Optional Rubric Compatibility Tests
# ===========================================================================

class TestFix2OptionalRubricCompatibility:
    """Verifies rubric, expected-answer-only, instructions-only, and no-guidance grading."""

    def test_rubric_provided_grades_normally(self, sample_evidence):
        """Traditional rubric evaluation works as before."""
        rubric = Rubric(
            criteria=[
                RubricCriterion(
                    criterion_id="c1",
                    description="States F = ma",
                    max_marks=5.0,
                    expected_concepts=["F = ma"],
                )
            ],
            total_marks=5.0,
        )
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="State Newton's second law.",
            question_max_marks=5.0,
            student_answer="F = ma",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 5.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 5.0,
                    "max_marks": 5.0,
                    "explanation": "Correct formula.",
                    "matched_concepts": ["F = ma"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                }
            ],
            "overall_explanation": "Full marks.",
            "strengths": ["Correct"],
            "areas_for_improvement": [],
            "confidence": 1.0,
            "review_required": False,
            "review_reasons": [],
        }
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client(llm_resp))
        grade = evaluator.evaluate_question(req, retrieved_evidence=["F = ma"], source_references=sample_evidence)

        assert grade.awarded_marks == 5.0
        assert grade.review_required is False

    def test_only_expected_answer_provided(self, sample_evidence):
        """When only expected_answer is provided (no rubric), grades holistically without error."""
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="State Newton's second law.",
            question_max_marks=5.0,
            student_answer="Force equals mass times acceleration.",
            rubric=None,
            expected_answer="Net force equals mass times acceleration (F = ma).",
        )
        llm_resp = {
            "awarded_marks": 4.5,
            "criterion_evaluations": [
                {
                    "criterion_id": "holistic_eval",
                    "awarded_marks": 4.5,
                    "max_marks": 5.0,
                    "explanation": "Demonstrates accurate conceptual understanding of the expected answer.",
                    "matched_concepts": ["mass times acceleration"],
                    "missing_concepts": [],
                    "confidence": 0.9,
                }
            ],
            "overall_explanation": "Good answer aligning with expected solution.",
            "strengths": ["Clear concepts"],
            "areas_for_improvement": [],
            "confidence": 0.9,
            "review_required": False,
            "review_reasons": [],
        }
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client(llm_resp))
        grade = evaluator.evaluate_question(req, retrieved_evidence=["F = ma"], source_references=sample_evidence)

        assert grade.awarded_marks == 4.5
        assert grade.max_marks == 5.0
        assert len(grade.criterion_evaluations) == 1
        assert grade.criterion_evaluations[0].criterion_id == "holistic_eval"

    def test_only_model_answer_model_provided(self, sample_evidence):
        """When model_answer object is provided without rubric."""
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="State Newton's second law.",
            question_max_marks=5.0,
            student_answer="F = ma",
            rubric=None,
            model_answer=ModelAnswer(
                text="F = ma",
                key_points=["Force", "Mass", "Acceleration"],
            ),
        )
        llm_resp = {
            "awarded_marks": 5.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "holistic_eval",
                    "awarded_marks": 5.0,
                    "max_marks": 5.0,
                    "explanation": "Matches model answer.",
                    "matched_concepts": ["Force", "Mass", "Acceleration"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                }
            ],
            "overall_explanation": "Perfect match.",
            "strengths": [],
            "areas_for_improvement": [],
            "confidence": 1.0,
            "review_required": False,
            "review_reasons": [],
        }
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client(llm_resp))
        grade = evaluator.evaluate_question(req, retrieved_evidence=["F = ma"], source_references=sample_evidence)

        assert grade.awarded_marks == 5.0

    def test_only_instructions_provided_flags_review(self, sample_evidence):
        """When only instructions exist (no rubric or expected answer), flags for review."""
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="Discuss Newton's contributions.",
            question_max_marks=5.0,
            student_answer="Newton developed mechanics and calculus.",
            rubric=None,
            expected_answer=None,
            instructions="Award marks for mention of calculus and mechanics.",
        )
        llm_resp = {
            "awarded_marks": 4.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "instruction_eval",
                    "awarded_marks": 4.0,
                    "max_marks": 5.0,
                    "explanation": "Followed teacher instructions.",
                    "matched_concepts": ["calculus", "mechanics"],
                    "missing_concepts": [],
                    "confidence": 0.8,
                }
            ],
            "overall_explanation": "Addressed instructions.",
            "strengths": [],
            "areas_for_improvement": [],
            "confidence": 0.8,
            "review_required": False,
            "review_reasons": [],
        }
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client(llm_resp))
        grade = evaluator.evaluate_question(req, retrieved_evidence=["Newton contributions"], source_references=sample_evidence)

        assert grade.review_required is True
        assert any("instructions without an official rubric" in r for r in grade.review_reasons)

    def test_no_guidance_provided_flags_review(self, sample_evidence):
        """When no rubric, expected answer, or instructions are provided, flags teacher review."""
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="Explain inertia.",
            question_max_marks=5.0,
            student_answer="Inertia is resistance to change in motion.",
            rubric=None,
            expected_answer=None,
            instructions=None,
        )
        llm_resp = {
            "awarded_marks": 4.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "general_eval",
                    "awarded_marks": 4.0,
                    "max_marks": 5.0,
                    "explanation": "Reasonable explanation.",
                    "matched_concepts": ["resistance to change"],
                    "missing_concepts": [],
                    "confidence": 0.7,
                }
            ],
            "overall_explanation": "Adequate explanation.",
            "strengths": [],
            "areas_for_improvement": [],
            "confidence": 0.7,
            "review_required": False,
            "review_reasons": [],
        }
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client(llm_resp))
        grade = evaluator.evaluate_question(req, retrieved_evidence=["Inertia"], source_references=sample_evidence)

        assert grade.review_required is True
        assert any("no rubric, expected answer, or grading instructions" in r.lower() for r in grade.review_reasons)


# ===========================================================================
# FIX 3: Deterministic MCQ Grading Tests
# ===========================================================================

class TestFix3DeterministicMcqGrading:
    """Verifies that MCQs evaluate strictly and deterministically without invoking Gemini."""

    def test_mcq_correct_option_awards_full_marks(self):
        req = GradingRequest(
            course_id="CS301",
            assignment_id="a1",
            submission_id="s1",
            question_id="q_mcq_1",
            question_text="What protocol operates at the transport layer?",
            question_max_marks=2.5,
            question_type=QuestionType.MCQ,
            selected_option_id="B",
            correct_option_id="B",
        )
        mock_client = MagicMock()
        evaluator = AnswerEvaluator(gemini_client=mock_client)
        grade = evaluator.evaluate_question(req)

        assert grade.awarded_marks == 2.5
        assert grade.max_marks == 2.5
        assert grade.confidence == 1.0
        assert grade.review_required is False
        assert "Selected option 'B' is correct." in grade.criterion_evaluations[0].explanation
        # Assert LLM was never called
        mock_client.generate_structured.assert_not_called()
        mock_client.generate_text.assert_not_called()

    def test_mcq_incorrect_option_awards_zero_marks(self):
        req = GradingRequest(
            course_id="CS301",
            assignment_id="a1",
            submission_id="s1",
            question_id="q_mcq_1",
            question_text="What protocol operates at the transport layer?",
            question_max_marks=2.5,
            question_type=QuestionType.MCQ,
            selected_option_id="A",
            correct_option_id="B",
        )
        mock_client = MagicMock()
        evaluator = AnswerEvaluator(gemini_client=mock_client)
        grade = evaluator.evaluate_question(req)

        assert grade.awarded_marks == 0.0
        assert grade.max_marks == 2.5
        assert grade.confidence == 1.0
        assert grade.review_required is False
        assert "Selected option 'A' is incorrect." in grade.criterion_evaluations[0].explanation
        # Must not reveal the correct option to student in student-facing explanation
        assert "B" not in grade.overall_explanation
        mock_client.generate_structured.assert_not_called()

    def test_mcq_case_insensitive_matching(self):
        """Lowercase 'b' matches uppercase 'B'."""
        req = GradingRequest(
            course_id="CS301",
            assignment_id="a1",
            submission_id="s1",
            question_id="q_mcq_1",
            question_text="Question?",
            question_max_marks=1.0,
            question_type=QuestionType.MCQ,
            student_answer="b",  # lowercase in student_answer
            correct_option_id="B",
        )
        mock_client = MagicMock()
        evaluator = AnswerEvaluator(gemini_client=mock_client)
        grade = evaluator.evaluate_question(req)

        assert grade.awarded_marks == 1.0
        mock_client.generate_structured.assert_not_called()

    def test_mcq_missing_selection_awards_zero(self):
        req = GradingRequest(
            course_id="CS301",
            assignment_id="a1",
            submission_id="s1",
            question_id="q_mcq_1",
            question_text="Question?",
            question_max_marks=1.0,
            question_type=QuestionType.MCQ,
            student_answer="",
            correct_option_id="B",
        )
        mock_client = MagicMock()
        evaluator = AnswerEvaluator(gemini_client=mock_client)
        grade = evaluator.evaluate_question(req)

        assert grade.awarded_marks == 0.0
        assert grade.confidence == 1.0
        assert "No option was selected" in grade.overall_explanation
        mock_client.generate_structured.assert_not_called()

    def test_mcq_missing_teacher_key_flags_review(self):
        req = GradingRequest(
            course_id="CS301",
            assignment_id="a1",
            submission_id="s1",
            question_id="q_mcq_1",
            question_text="Question?",
            question_max_marks=1.0,
            question_type=QuestionType.MCQ,
            student_answer="B",
            correct_option_id=None,  # Missing key
        )
        mock_client = MagicMock()
        evaluator = AnswerEvaluator(gemini_client=mock_client)
        grade = evaluator.evaluate_question(req)

        assert grade.review_required is True
        assert any("correct_option_id" in r for r in grade.review_reasons)
        mock_client.generate_structured.assert_not_called()


# ===========================================================================
# FIX 4: OCR Confidence Safeguards & Boundaries Tests
# ===========================================================================

class TestFix4OcrConfidenceSafeguards:
    """Verifies confidence caps and thresholds across all specified boundaries."""

    @pytest.fixture
    def mock_question_grade(self):
        return QuestionGrade(
            question_id="q1",
            max_marks=5.0,
            awarded_marks=5.0,
            criterion_evaluations=[
                CriterionEvaluation(
                    criterion_id="c1",
                    criterion_name="Criterion 1",
                    max_marks=5.0,
                    awarded_marks=5.0,
                    explanation="Well explained answer with evidence support.",
                    matched_concepts=["concept"],
                    evidence_references=[
                        SourceReference(document_id="d1", snippet="snip", similarity_score=0.95)
                    ],
                    confidence=1.0,
                )
            ],
            overall_explanation="High quality response.",
        )

    @pytest.fixture
    def mock_rubric(self):
        return Rubric(
            criteria=[
                RubricCriterion(
                    criterion_id="c1",
                    description="Detailed explanation with all core concepts demonstrated",
                    max_marks=5.0,
                    expected_concepts=["concept"],
                )
            ],
            total_marks=5.0,
        )

    def test_boundary_0_0(self, mock_question_grade, mock_rubric):
        """OCR confidence 0.0: overall confidence must be capped at <= 0.59 and review_recommended=True."""
        est = ConfidenceEstimator()
        res = est.calculate_confidence(
            question_grade=mock_question_grade,
            rubric=mock_rubric,
            source_references=mock_question_grade.criterion_evaluations[0].evidence_references,
            ocr_confidence=0.0,
        )
        assert res.overall <= 0.59
        assert res.review_recommended is True

    def test_boundary_0_35(self, mock_question_grade, mock_rubric):
        """OCR confidence 0.35: overall confidence must be capped at <= 0.59 and review_recommended=True."""
        est = ConfidenceEstimator()
        res = est.calculate_confidence(
            question_grade=mock_question_grade,
            rubric=mock_rubric,
            source_references=mock_question_grade.criterion_evaluations[0].evidence_references,
            ocr_confidence=0.35,
        )
        assert res.overall <= 0.59
        assert res.review_recommended is True

    def test_boundary_0_49(self, mock_question_grade, mock_rubric):
        """OCR confidence 0.49: overall confidence must be capped at <= 0.59 and review_recommended=True."""
        est = ConfidenceEstimator()
        res = est.calculate_confidence(
            question_grade=mock_question_grade,
            rubric=mock_rubric,
            source_references=mock_question_grade.criterion_evaluations[0].evidence_references,
            ocr_confidence=0.49,
        )
        assert res.overall <= 0.59
        assert res.review_recommended is True

    def test_boundary_0_50(self, mock_question_grade, mock_rubric):
        """OCR confidence 0.50: not capped at 0.59 (since not < 0.50), but < 0.60 so review_recommended=True."""
        est = ConfidenceEstimator()
        res = est.calculate_confidence(
            question_grade=mock_question_grade,
            rubric=mock_rubric,
            source_references=mock_question_grade.criterion_evaluations[0].evidence_references,
            ocr_confidence=0.50,
        )
        # Not capped at 0.59, but review still recommended because 0.50 < 0.60
        assert res.review_recommended is True

    def test_boundary_0_59(self, mock_question_grade, mock_rubric):
        """OCR confidence 0.59: review_recommended=True because < 0.60."""
        est = ConfidenceEstimator()
        res = est.calculate_confidence(
            question_grade=mock_question_grade,
            rubric=mock_rubric,
            source_references=mock_question_grade.criterion_evaluations[0].evidence_references,
            ocr_confidence=0.59,
        )
        assert res.review_recommended is True

    def test_boundary_0_60(self, mock_question_grade, mock_rubric):
        """OCR confidence 0.60: does not trigger OCR-specific review flag."""
        est = ConfidenceEstimator()
        res = est.calculate_confidence(
            question_grade=mock_question_grade,
            rubric=mock_rubric,
            source_references=mock_question_grade.criterion_evaluations[0].evidence_references,
            ocr_confidence=0.60,
        )
        # Overall is high (> 0.70) and OCR is not < 0.60, so review_recommended should be False
        assert res.overall >= 0.70
        assert res.review_recommended is False

    def test_boundary_1_0(self, mock_question_grade, mock_rubric):
        """OCR confidence 1.0: full confidence without review."""
        est = ConfidenceEstimator()
        res = est.calculate_confidence(
            question_grade=mock_question_grade,
            rubric=mock_rubric,
            source_references=mock_question_grade.criterion_evaluations[0].evidence_references,
            ocr_confidence=1.0,
        )
        assert res.overall >= 0.85
        assert res.review_recommended is False

    def test_boundary_none_handled_explicitly(self, mock_question_grade, mock_rubric):
        """OCR confidence None (metadata absent): handled as baseline 1.0 without triggering OCR review."""
        est = ConfidenceEstimator()
        res = est.calculate_confidence(
            question_grade=mock_question_grade,
            rubric=mock_rubric,
            source_references=mock_question_grade.criterion_evaluations[0].evidence_references,
            ocr_confidence=None,
        )
        assert res.ocr_quality == 1.0
        assert res.review_recommended is False


# ===========================================================================
# FIX 5: Asynchronous Execution Compatibility Tests
# ===========================================================================

class TestFix5AsyncExecutionCompatibility:
    """Verifies that async wrappers execute safely on a worker thread."""

    @pytest.mark.asyncio
    async def test_async_evaluate_question(self, sample_evidence):
        req = GradingRequest(
            course_id="CS101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="Explain async I/O.",
            question_max_marks=5.0,
            student_answer="Async I/O uses an event loop to handle concurrent tasks without blocking.",
            expected_answer="Event loop and concurrency.",
        )
        llm_resp = {
            "awarded_marks": 5.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "holistic_eval",
                    "awarded_marks": 5.0,
                    "max_marks": 5.0,
                    "explanation": "Correct async description.",
                    "matched_concepts": ["event loop"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                }
            ],
            "overall_explanation": "Great job.",
            "strengths": [],
            "areas_for_improvement": [],
            "confidence": 1.0,
            "review_required": False,
            "review_reasons": [],
        }
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client(llm_resp))
        grade = await evaluator.async_evaluate_question(req, retrieved_evidence=["async"], source_references=sample_evidence)

        assert grade.awarded_marks == 5.0
        assert grade.max_marks == 5.0

    @pytest.mark.asyncio
    async def test_async_grade_submission(self, sample_evidence):
        req = GradingRequest(
            course_id="CS101",
            assignment_id="a1",
            submission_id="s1",
            question_id="q1",
            question_text="Explain async I/O.",
            question_max_marks=5.0,
            student_answer="Async I/O uses an event loop.",
            expected_answer="Event loop.",
        )
        llm_resp = {
            "awarded_marks": 5.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "holistic_eval",
                    "awarded_marks": 5.0,
                    "max_marks": 5.0,
                    "explanation": "Correct.",
                    "matched_concepts": ["event loop"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                }
            ],
            "overall_explanation": "Good.",
            "strengths": [],
            "areas_for_improvement": [],
            "confidence": 1.0,
            "review_required": False,
            "review_reasons": [],
        }
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client(llm_resp))
        result = await evaluator.async_grade_submission("s1", "a1", [req])

        assert result.total_awarded_marks == 5.0
        assert result.total_max_marks == 5.0
        assert result.percentage == 100.0


# ===========================================================================
# FIX 6: Additional Quality Improvements Tests
# ===========================================================================

class TestFix6QualityImprovements:
    """Verifies LaTeX boundary protection and LLM retry/malformed error handling."""

    def test_latex_boundary_protection_in_chunker(self):
        """Verifies that punctuation inside LaTeX formulas ($...$) does not cause mid-formula splitting."""
        chunker = TextChunker(chunk_size=60, chunk_overlap=10)
        # Sentence with formula containing a semicolon: $x = 1.5; y = 2.0$
        text = "Introduction. Here is an important equation: $x = 1.5; y = 2.0$ which describes the relationship."
        chunks = chunker.chunk_text(text, course_id="MATH101", document_id="doc1")

        for c in chunks:
            # Confirm dollar count in each chunk is balanced (even) so no formula was split across chunks
            assert c.text.count("$") % 2 == 0

    def test_malformed_llm_json_handling(self):
        """Completely invalid non-JSON output raises LLMResponseValidationError.

        It is deliberately not an LLMAPIError: the server maps it to its own 502 "unusable response"
        and the fallback client treats it differently from transport/API failures.
        """
        mock_genai = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "NOT JSON AT ALL"
        mock_genai.models.generate_content.return_value = mock_resp

        client = GeminiClient(api_key="test", client=mock_genai)
        with pytest.raises(LLMResponseValidationError):
            client.generate_structured("prompt", Rubric)

    def test_retry_exhaustion_raises_rate_limit(self):
        """When Gemini returns 429 continually, LLMRateLimitError is raised after retry exhaustion."""
        mock_genai = MagicMock()
        error_429 = Exception("ResourceExhausted: 429 quota exceeded")
        setattr(error_429, "code", 429)
        mock_genai.models.generate_content.side_effect = error_429

        client = GeminiClient(api_key="test", client=mock_genai)
        with pytest.raises(LLMRateLimitError):
            client.generate_text("prompt", max_retries=1)

