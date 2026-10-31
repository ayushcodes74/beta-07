"""Functional grading evaluation across 16 academic scenarios.

Tests the complete data flow:
Student answer -> assignment context -> reference material -> rubric evaluation -> LLM -> structured grading result.
"""

from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError

from app.assignment.generator import AssignmentGenerator
from app.grading.evaluator import AnswerEvaluator, _LLMQuestionGradeResponse, _LLMCriterionEvaluation
from app.grading.evidence_retriever import GradingEvidenceRetriever, EvidenceRetrievalResult
from app.llm.gemini_client import GeminiClient
from app.rag.retriever import CourseMaterialRetriever
from app.rag.vector_store import InMemoryVectorStore
from app.schemas.assignment import (
    DifficultyLevel,
    ModelAnswer,
    QuestionType,
    Rubric,
    RubricCriterion,
    SyllabusCoverageStatus,
)
from app.schemas.common import ReviewReasonCategory, SourceReference
from app.schemas.grading import GradingRequest, GradingStatus
from app.schemas.rag import DocumentChunk, RetrievedChunk
from app.schemas.trust import ConfidenceLevel
from app.syllabus.detector import SyllabusDetector
from app.trust.confidence import ConfidenceEstimator
from app.trust.injection_detector import PromptInjectionDetector
from app.trust.review_router import HumanReviewRouter
from app.trust.service import TrustService


def _make_mock_client(response_dict: dict) -> GeminiClient:
    """Helper to mock GeminiClient structured generation."""
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = None
    import json
    mock_response.text = json.dumps(response_dict)
    mock_genai_client.models.generate_content.return_value = mock_response
    return GeminiClient(api_key="test-key", client=mock_genai_client)


def _make_rubric(criteria_specs: list[tuple[str, str, float, list[str]]]) -> Rubric:
    """Create a validated Rubric from tuples of (id, desc, max_marks, expected_concepts)."""
    criteria = [
        RubricCriterion(
            criterion_id=cid,
            description=desc,
            max_marks=marks,
            expected_concepts=concepts,
        )
        for cid, desc, marks, concepts in criteria_specs
    ]
    total = sum(c.max_marks for c in criteria)
    return Rubric(criteria=criteria, total_marks=total)


@pytest.fixture
def physics_evidence():
    return [
        SourceReference(
            document_id="doc_phys_01",
            title="Classical Mechanics Ch 3",
            page_number=42,
            snippet="Newton's second law states that the net force on an object is equal to the rate of change of its linear momentum: F = dp/dt. When mass is constant, F = ma.",
            similarity_score=0.92,
        )
    ]


class TestFunctional16Scenarios:
    """The 16 required functional academic grading scenarios."""

    # Scenario 1: Completely correct subjective answer
    def test_scenario_01_completely_correct_subjective(self, physics_evidence):
        rubric = _make_rubric([
            ("c1", "State F = ma formula and momentum relation", 3.0, ["F = ma", "rate of change of momentum"]),
            ("c2", "State condition of constant mass", 2.0, ["constant mass"]),
        ])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_1",
            question_id="q1",
            question_text="State and explain Newton's second law.",
            question_max_marks=5.0,
            student_answer="Newton's second law states that force is the rate of change of momentum (F = dp/dt). When mass is constant, this reduces to F = ma.",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 5.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 3.0,
                    "max_marks": 3.0,
                    "explanation": "Correctly states F = ma and momentum relationship.",
                    "matched_concepts": ["F = ma", "rate of change of momentum"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                },
                {
                    "criterion_id": "c2",
                    "awarded_marks": 2.0,
                    "max_marks": 2.0,
                    "explanation": "Explicitly notes constant mass assumption.",
                    "matched_concepts": ["constant mass"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                },
            ],
            "overall_explanation": "Flawless and complete answer.",
            "strengths": ["Clear conceptual formulation"],
            "areas_for_improvement": [],
            "confidence": 0.95,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["F = ma"], source_references=physics_evidence)

        assert grade.awarded_marks == 5.0
        assert grade.max_marks == 5.0
        assert grade.confidence >= 0.80
        assert grade.review_required is False
        assert len(grade.criterion_evaluations) == 2

    # Scenario 2: Partially correct answer
    def test_scenario_02_partially_correct_answer(self, physics_evidence):
        rubric = _make_rubric([
            ("c1", "State F = ma formula", 3.0, ["F = ma"]),
            ("c2", "State condition of constant mass", 2.0, ["constant mass"]),
        ])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_2",
            question_id="q1",
            question_text="State Newton's second law and its condition.",
            question_max_marks=5.0,
            student_answer="Force equals mass times acceleration (F = ma).",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 3.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 3.0,
                    "max_marks": 3.0,
                    "explanation": "Correctly states F = ma.",
                    "matched_concepts": ["F = ma"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                },
                {
                    "criterion_id": "c2",
                    "awarded_marks": 0.0,
                    "max_marks": 2.0,
                    "explanation": "Omitted the constant mass condition.",
                    "matched_concepts": [],
                    "missing_concepts": ["constant mass"],
                    "confidence": 0.9,
                },
            ],
            "overall_explanation": "Partially correct; missed condition.",
            "strengths": ["Correct equation"],
            "areas_for_improvement": ["Remember to state boundary conditions such as constant mass."],
            "confidence": 0.85,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["F = ma"], source_references=physics_evidence)

        assert grade.awarded_marks == 3.0
        assert grade.max_marks == 5.0
        assert "constant mass" in grade.criterion_evaluations[1].missing_concepts

    # Scenario 3: Completely incorrect answer
    def test_scenario_03_completely_incorrect_answer(self, physics_evidence):
        rubric = _make_rubric([("c1", "Newton's second law definition", 5.0, ["F = ma"])])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_3",
            question_id="q1",
            question_text="State Newton's second law.",
            question_max_marks=5.0,
            student_answer="Newton's second law says that energy cannot be created or destroyed, only transformed.",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 0.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 0.0,
                    "max_marks": 5.0,
                    "explanation": "Confuses conservation of energy with Newton's second law.",
                    "matched_concepts": [],
                    "missing_concepts": ["F = ma", "momentum"],
                    "confidence": 0.95,
                }
            ],
            "overall_explanation": "Incorrect definition.",
            "strengths": [],
            "areas_for_improvement": ["Review Newton's laws of motion."],
            "confidence": 0.9,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["F = ma"], source_references=physics_evidence)

        assert grade.awarded_marks == 0.0
        assert grade.max_marks == 5.0

    # Scenario 4: Answer containing irrelevant information
    def test_scenario_04_irrelevant_information(self, physics_evidence):
        rubric = _make_rubric([("c1", "State F = ma", 5.0, ["F = ma"])])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_4",
            question_id="q1",
            question_text="State Newton's second law.",
            question_max_marks=5.0,
            student_answer="F = ma. By the way, Newton was born in Lincolnshire in 1643 and enjoyed alchemy.",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 5.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 5.0,
                    "max_marks": 5.0,
                    "explanation": "Correct formula stated; historical notes are extraneous but do not invalidate answer.",
                    "matched_concepts": ["F = ma"],
                    "missing_concepts": [],
                    "confidence": 0.9,
                }
            ],
            "overall_explanation": "Answer is accurate; biographical remarks are irrelevant.",
            "strengths": ["Correct physics"],
            "areas_for_improvement": ["Focus strictly on the physics question."],
            "confidence": 0.85,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["F = ma"], source_references=physics_evidence)

        assert grade.awarded_marks == 5.0
        assert "irrelevant" in grade.overall_explanation.lower() or "extraneous" in grade.criterion_evaluations[0].explanation.lower()

    # Scenario 5: Correct answer expressed in different wording
    def test_scenario_05_different_wording_semantic_equivalence(self, physics_evidence):
        rubric = _make_rubric([("c1", "Acceleration relationship to net force and mass", 5.0, ["proportional to force", "inversely to mass"])])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_5",
            question_id="q1",
            question_text="Describe how net force affects acceleration.",
            question_max_marks=5.0,
            student_answer="The acceleration acquired by a body is directly proportional to the applied net force and inversely related to the inertia or mass of the body.",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 5.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 5.0,
                    "max_marks": 5.0,
                    "explanation": "Excellently captures semantic equivalence using alternative phrasing.",
                    "matched_concepts": ["proportional to force", "inversely to mass"],
                    "missing_concepts": [],
                    "confidence": 0.95,
                }
            ],
            "overall_explanation": "Full marks awarded for semantic understanding.",
            "strengths": ["Strong conceptual grasp"],
            "areas_for_improvement": [],
            "confidence": 0.92,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["proportional to force"], source_references=physics_evidence)

        assert grade.awarded_marks == 5.0

    # Scenario 6: Answer outside supplied syllabus
    def test_scenario_06_outside_supplied_syllabus(self):
        detector = SyllabusDetector(
            gemini_client=_make_mock_client({
                "status": "OUT_OF_SYLLABUS",
                "confidence": 0.95,
                "covered_concepts": [],
                "uncovered_concepts": ["Electroweak Symmetry Breaking", "Higgs Mechanism"],
                "reasoning": "The supplied syllabus covers only introductory classical mechanics; advanced quantum field theory topics are completely absent.",
                "evidence": [],
            })
        )
        res = detector.detect_coverage(
            question="Explain the Higgs mechanism in electroweak symmetry breaking.",
            course_id="PHY101",
            syllabus_text="Unit 1: Kinematics. Unit 2: Newton's Laws. Unit 3: Work & Energy.",
        )
        assert res.status == SyllabusCoverageStatus.OUT_OF_SYLLABUS
        assert "Higgs Mechanism" in res.uncovered_concepts

    # Scenario 7: Answer containing unsupported claims
    def test_scenario_07_unsupported_claims(self, physics_evidence):
        rubric = _make_rubric([("c1", "Carnot engine theoretical limit", 5.0, ["1 - Tc/Th", "cannot reach 100%"])])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_7",
            question_id="q1",
            question_text="What is the maximum efficiency of a heat engine?",
            question_max_marks=5.0,
            student_answer="A Carnot engine has 100% efficiency at room temperature because friction is eliminated.",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 0.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 0.0,
                    "max_marks": 5.0,
                    "explanation": "Claim of 100% efficiency contradicts the Second Law of Thermodynamics and course material.",
                    "matched_concepts": [],
                    "missing_concepts": ["1 - Tc/Th", "cannot reach 100%"],
                    "confidence": 0.9,
                }
            ],
            "overall_explanation": "Unsupported and incorrect scientific claim.",
            "strengths": [],
            "areas_for_improvement": ["Review Carnot cycle efficiency formula."],
            "confidence": 0.88,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["efficiency = 1 - Tc/Th"], source_references=physics_evidence)

        assert grade.awarded_marks == 0.0

    # Scenario 8: Empty answer
    def test_scenario_08_empty_answer(self):
        rubric = _make_rubric([("c1", "Core definition", 5.0, ["Newton's First Law"])])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_8",
            question_id="q1",
            question_text="State Newton's first law.",
            question_max_marks=5.0,
            student_answer="   ",  # whitespace only
            rubric=rubric,
        )
        evaluator = AnswerEvaluator(gemini_client=_make_mock_client({}))
        grade = evaluator.evaluate_question(req)

        assert grade.awarded_marks == 0.0
        assert grade.max_marks == 5.0
        assert grade.confidence == 1.0
        assert grade.review_required is False
        assert "No answer was submitted" in grade.overall_explanation

    # Scenario 9: Ambiguous answer
    def test_scenario_09_ambiguous_answer(self, physics_evidence):
        rubric = _make_rubric([("c1", "Direction of friction force", 4.0, ["opposes relative motion"])])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_9",
            question_id="q1",
            question_text="In which direction does kinetic friction act?",
            question_max_marks=4.0,
            student_answer="It acts along the motion or backwards sometimes depending on the observer.",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 1.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 1.0,
                    "max_marks": 4.0,
                    "explanation": "Answer is ambiguous and self-contradictory.",
                    "matched_concepts": [],
                    "missing_concepts": ["opposes relative motion"],
                    "confidence": 0.45,
                }
            ],
            "overall_explanation": "Vague and contradictory statements.",
            "strengths": [],
            "areas_for_improvement": ["Clarify that friction opposes relative motion between surfaces."],
            "confidence": 0.45,
            "review_required": True,
            "review_reasons": ["Ambiguous student answer"],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["opposes relative motion"], source_references=physics_evidence)

        assert grade.review_required is True
        assert any("ambiguous" in r.lower() for r in grade.review_reasons)

    # Scenario 10: Mathematical answer with LaTeX
    def test_scenario_10_mathematical_latex_answer(self, physics_evidence):
        rubric = _make_rubric([
            ("c1", "State kinetic energy formula", 2.0, ["$KE = \\frac{1}{2}mv^2$"]),
            ("c2", "Correct numerical substitution and answer", 3.0, ["$9\\text{ J}$"]),
        ])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_10",
            question_id="q1",
            question_text="Calculate the kinetic energy of a 2 kg mass at 3 m/s.",
            question_max_marks=5.0,
            student_answer=r"KE = \frac{1}{2}mv^2 = \frac{1}{2}(2)(3)^2 = 9\text{ J}",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 5.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 2.0,
                    "max_marks": 2.0,
                    "explanation": "Correct formula.",
                    "matched_concepts": ["KE formula"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                },
                {
                    "criterion_id": "c2",
                    "awarded_marks": 3.0,
                    "max_marks": 3.0,
                    "explanation": "Correct evaluation: 9 J.",
                    "matched_concepts": ["9 J"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                },
            ],
            "overall_explanation": "Mathematically accurate derivation.",
            "strengths": ["Correct calculation"],
            "areas_for_improvement": [],
            "confidence": 0.95,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["KE = 1/2 m v^2"], source_references=physics_evidence)

        assert grade.awarded_marks == 5.0

    # Scenario 11: Missing reference material
    def test_scenario_11_missing_reference_material(self):
        rubric = _make_rubric([("c1", "Specific course convention", 4.0, ["Convention A"])])
        req = GradingRequest(
            course_id="EMPTY_COURSE",
            assignment_id="asgn_1",
            submission_id="sub_11",
            question_id="q1",
            question_text="State the sign convention taught in lecture.",
            question_max_marks=4.0,
            student_answer="We use the right-hand rule sign convention.",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 4.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 4.0,
                    "max_marks": 4.0,
                    "explanation": "Appears plausible.",
                    "matched_concepts": ["right-hand rule"],
                    "missing_concepts": [],
                    "confidence": 0.7,
                }
            ],
            "overall_explanation": "Good answer.",
            "strengths": [],
            "areas_for_improvement": [],
            "confidence": 0.7,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        # Empty evidence retriever
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = MagicMock(chunks=[])
        ev_retriever = GradingEvidenceRetriever(retriever=mock_retriever)

        evaluator = AnswerEvaluator(gemini_client=client, evidence_retriever=ev_retriever)
        grade = evaluator.evaluate_question(req)

        # Missing evidence must flag review
        assert grade.review_required is True
        assert any("evidence" in r.lower() for r in grade.review_reasons)

    # Scenario 12: Missing rubric handled safely & flagged for review
    def test_scenario_12_missing_rubric_handled_safely(self, physics_evidence):
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_12",
            question_id="q1",
            question_text="Explain work.",
            question_max_marks=5.0,
            student_answer="Work is force times displacement.",
            rubric=None,  # Missing rubric
        )
        llm_resp = {
            "awarded_marks": 5.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "general_eval",
                    "awarded_marks": 5.0,
                    "max_marks": 5.0,
                    "explanation": "Correct statement.",
                    "matched_concepts": ["force times displacement"],
                    "missing_concepts": [],
                    "confidence": 0.8,
                }
            ],
            "overall_explanation": "Good answer.",
            "strengths": [],
            "areas_for_improvement": [],
            "confidence": 0.8,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["work = force * distance"], source_references=physics_evidence)

        # Successfully graded without crash, but review is required because no rubric or model answer was provided
        assert grade.review_required is True
        assert any("no rubric" in r.lower() for r in grade.review_reasons)

    # Scenario 13: Low-confidence answer due to poor OCR quality
    def test_scenario_13_low_confidence_from_poor_ocr(self, physics_evidence):
        rubric = _make_rubric([("c1", "Explanation", 5.0, ["Concept"])])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_13",
            question_id="q1",
            question_text="Explain momentum.",
            question_max_marks=5.0,
            student_answer="M...ntum is m... v...",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 2.5,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 2.5,
                    "max_marks": 5.0,
                    "explanation": "Text was partially unreadable.",
                    "matched_concepts": [],
                    "missing_concepts": [],
                    "confidence": 0.5,
                }
            ],
            "overall_explanation": "Partial transcript.",
            "strengths": [],
            "areas_for_improvement": [],
            "confidence": 0.5,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        # Pass low OCR confidence (0.35)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["momentum"], source_references=physics_evidence, ocr_confidence=0.35)

        # Triggers review because ocr_score < 0.60
        assert grade.review_required is True
        assert any("low ocr" in r.lower() for r in grade.review_reasons)
        # Fix 4 safeguard: OCR confidence < 0.50 (0.35) caps overall confidence at 0.59 (LOW)
        assert grade.confidence <= 0.59

    # Scenario 14: MCQ with correct option
    def test_scenario_14_mcq_correct_option(self):
        rubric = _make_rubric([("c1", "Selected Transport Layer (Option B)", 1.0, ["B"])])
        req = GradingRequest(
            course_id="CS301",
            assignment_id="asgn_net",
            submission_id="sub_14",
            question_id="q_mcq_1",
            question_text="Which OSI layer does TCP operate at? A) Network B) Transport C) Session D) Application",
            question_max_marks=1.0,
            student_answer="B",
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 1.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 1.0,
                    "max_marks": 1.0,
                    "explanation": "Correct option B selected.",
                    "matched_concepts": ["B"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                }
            ],
            "overall_explanation": "Correct MCQ choice.",
            "strengths": ["Correct answer"],
            "areas_for_improvement": [],
            "confidence": 1.0,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["TCP is transport layer"])

        assert grade.awarded_marks == 1.0
        assert grade.max_marks == 1.0

    # Scenario 15: MCQ with incorrect option
    def test_scenario_15_mcq_incorrect_option(self):
        rubric = _make_rubric([("c1", "Selected Transport Layer (Option B)", 1.0, ["B"])])
        req = GradingRequest(
            course_id="CS301",
            assignment_id="asgn_net",
            submission_id="sub_15",
            question_id="q_mcq_1",
            question_text="Which OSI layer does TCP operate at? A) Network B) Transport C) Session D) Application",
            question_max_marks=1.0,
            student_answer="A",  # Incorrect choice
            rubric=rubric,
        )
        llm_resp = {
            "awarded_marks": 0.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 0.0,
                    "max_marks": 1.0,
                    "explanation": "Option A is Network Layer (IP), whereas TCP is Transport Layer.",
                    "matched_concepts": [],
                    "missing_concepts": ["B"],
                    "confidence": 1.0,
                }
            ],
            "overall_explanation": "Incorrect option chosen.",
            "strengths": [],
            "areas_for_improvement": ["Review OSI layer responsibilities."],
            "confidence": 1.0,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["TCP is transport layer"])

        assert grade.awarded_marks == 0.0
        assert grade.max_marks == 1.0

    # Scenario 16: Boundary conditions: zero marks and maximum marks clamping
    def test_scenario_16_boundary_clamping_zero_and_max(self, physics_evidence):
        rubric = _make_rubric([("c1", "Criterion 1", 5.0, ["Concept"])])
        req = GradingRequest(
            course_id="PHY101",
            assignment_id="asgn_1",
            submission_id="sub_16",
            question_id="q1",
            question_text="Explain motion.",
            question_max_marks=5.0,
            student_answer="Something about motion.",
            rubric=rubric,
        )
        # LLM returns hallucinatory marks exceeding max (7.0 > 5.0)
        llm_resp = {
            "awarded_marks": 7.0,
            "criterion_evaluations": [
                {
                    "criterion_id": "c1",
                    "awarded_marks": 7.0,
                    "max_marks": 5.0,
                    "explanation": "Over-awarded.",
                    "matched_concepts": ["Concept"],
                    "missing_concepts": [],
                    "confidence": 1.0,
                }
            ],
            "overall_explanation": "Exceeded max.",
            "strengths": [],
            "areas_for_improvement": [],
            "confidence": 1.0,
            "review_required": False,
            "review_reasons": [],
        }
        client = _make_mock_client(llm_resp)
        evaluator = AnswerEvaluator(gemini_client=client)
        grade = evaluator.evaluate_question(req, retrieved_evidence=["motion"], source_references=physics_evidence)

        # Clamped strictly to max_marks (5.0)
        assert grade.awarded_marks == 5.0
        assert grade.max_marks == 5.0
        assert grade.criterion_evaluations[0].awarded_marks == 5.0
