"""Untaught-but-valid methods: the grader reports the method so the teacher can review it."""

from unittest.mock import MagicMock

import pytest

from app.grading.evaluator import AnswerEvaluator, _LLMCriterionEvaluation, _LLMQuestionGradeResponse
from app.grading.evidence_retriever import EvidenceRetrievalResult
from app.llm import prompts
from app.schemas.grading import GradingRequest, MethodApproach


def _request() -> GradingRequest:
    return GradingRequest(
        course_id="c1",
        assignment_id="a1",
        submission_id="s1",
        question_id="q1",
        question_text="Evaluate the integral of x*cos(x) dx.",
        question_max_marks=5.0,
        student_answer="Using the tabular (DI) method: x*sin(x) + cos(x) + C.",
        expected_answer="Integration by parts with u = x, dv = cos(x) dx gives x sin x + cos x + C.",
    )


def _evaluate(**method_fields) -> object:
    llm = MagicMock()
    llm.generate_structured.return_value = _LLMQuestionGradeResponse(
        awarded_marks=5.0,
        overall_explanation="Correct antiderivative.",
        criterion_evaluations=[
            _LLMCriterionEvaluation(criterion_id="c", awarded_marks=5.0, max_marks=5.0, explanation="Correct.")
        ],
        **method_fields,
    )
    retriever = MagicMock()
    retriever.retrieve_evidence_for_grading.return_value = EvidenceRetrievalResult(
        course_context="", evidence_snippets=[], source_references=[], has_sufficient_evidence=False, retrieved_chunks=[]
    )
    trust = MagicMock()
    trust.get_approved_reference_snippets.return_value = []
    trust.assess_submission.return_value = MagicMock(review_items=[], review_required=False)
    trust.assess_submission.return_value.confidence_breakdown.overall = 0.9
    return AnswerEvaluator(gemini_client=llm, evidence_retriever=retriever, trust_service=trust).evaluate_question(_request())


def test_valid_alternative_method_is_reported_with_full_marks():
    grade = _evaluate(
        approach="alternative_valid",
        method_name="Tabular (DI) integration",
        taught_method="Integration by parts",
        method_explanation="The DI table is a shortcut for repeated integration by parts; signs alternate correctly.",
    )
    assert grade.awarded_marks == 5.0  # marked on correctness, not penalised for the method
    m = grade.method_assessment
    assert m.approach is MethodApproach.ALTERNATIVE_VALID
    assert m.method_name == "Tabular (DI) integration"
    assert m.taught_method == "Integration by parts"
    assert "shortcut" in m.explanation


def test_default_is_taught_method_with_no_details():
    grade = _evaluate()
    assert grade.method_assessment.approach is MethodApproach.TAUGHT
    assert grade.method_assessment.method_name == ""


@pytest.mark.parametrize("raw", ["Alternative Valid", "alternative-valid", " ALTERNATIVE_VALID "])
def test_approach_casing_is_normalised(raw):
    grade = _evaluate(approach=raw, method_name="DI method")
    assert grade.method_assessment.approach is MethodApproach.ALTERNATIVE_VALID


def test_unknown_approach_counts_as_taught():
    grade = _evaluate(approach="creative", method_name="something")
    assert grade.method_assessment.approach is MethodApproach.TAUGHT
    assert grade.method_assessment.method_name == ""  # details only kept for non-taught methods


def test_unnamed_alternative_becomes_unclear():
    grade = _evaluate(approach="alternative_valid", method_name="  ")
    assert grade.method_assessment.approach is MethodApproach.UNCLEAR


def test_prompt_no_longer_requires_course_evidence_for_the_method():
    rules = prompts.SYSTEM_ACADEMIC_EVALUATOR
    assert "Mark the answer, not the method" in rules
    assert "absence of course evidence for the METHOD is not a reason to deduct" in rules
    assert "Evaluate solely based on" not in rules  # the old rule that contradicted crediting alternatives
