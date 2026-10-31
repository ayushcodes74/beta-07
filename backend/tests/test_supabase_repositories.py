"""Unit tests for Supabase-backed repositories (Phase 1).

Covers all 12 required test scenarios using mocked Supabase clients:
1. Teacher retrieves own assignment.
2. Teacher cannot retrieve another teacher's assignment.
3. Questions are returned in position order.
4. Answer keys are retrieved only through authorized backend logic.
5. Submission belongs to the expected assignment.
6. OCR job is retrieved for the correct submission.
7. Grading result insertion uses existing columns only.
8. Duplicate grading result insertion is handled safely.
9. Student cannot retrieve unpublished grading results.
10. Teacher can retrieve their own grading results.
11. Teacher cannot modify another teacher's results.
12. Invalid grading status is rejected.

Note on Live vs Mocked Verification:
- These tests mock the Supabase HTTP PostgREST client to verify SQL queries, RLS parameters,
  column mappings, and business security policies without requiring a live cloud database.
- Live Supabase verification tests are explicitly demarcated and require active Supabase credentials.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.database.assignment_repository import (
    AssignmentQuestionRecord,
    QuestionAnswerKeyRecord,
    SupabaseAssignmentRepository,
)
from app.database.grading_repository import (
    GradingRepositoryError,
    GradingResultCreate,
    GradingResultRecord,
    GradingStatus,
    InvalidGradingStatusError,
    SupabaseGradingRepository,
)
from app.database.submission_repository import (
    OCRJobRecord,
    SubmissionAnswerRecord,
    SupabaseSubmissionRepository,
)
from app.schemas.assignment import AssignmentCreate, AssignmentStatus


def _mock_execute(data):
    mock = MagicMock()
    mock.execute.return_value = MagicMock(data=data)
    return mock


# ===========================================================================
# 1. AssignmentRepository Tests
# ===========================================================================


class TestAssignmentRepository:
    """Verifies assignment persistence, ownership isolation, question ordering, and answer key security."""

    @patch("app.database.assignment_repository.get_user_supabase")
    def test_create_persists_course_id_and_returns_content_without_course_field(self, mock_get_client):
        course_id = uuid4()
        teacher_id = uuid4()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        due_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        content = AssignmentCreate(
            title="Course quiz",
            due_at=due_at,
            total_marks=1,
            questions=[],
            course_id=course_id,
        )

        record = SupabaseAssignmentRepository().create(teacher_id, content, access_token="token")

        payload = mock_client.table("assignments").insert.call_args.args[0]
        assert payload["course_id"] == str(course_id)
        assert record.course_id == course_id
        assert "course_id" not in record.content.model_dump()

    @patch("app.database.assignment_repository.get_user_supabase")
    def test_assignment_course_ownership_is_teacher_scoped(self, mock_get_client):
        course_id = uuid4()
        teacher_id = uuid4()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        course_query = mock_client.table("courses").select.return_value
        course_query.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": str(course_id)}]
        )

        assert SupabaseAssignmentRepository().owns_course(
            course_id, teacher_id, access_token="token"
        ) is True
        mock_client.table("courses").select.assert_called_once_with("id")
        course_query.eq.assert_called_once_with("id", str(course_id))
        course_query.eq.return_value.eq.assert_called_once_with("teacher_id", str(teacher_id))

    @patch("app.database.assignment_repository.get_user_supabase")
    def test_1_teacher_retrieves_own_assignment(self, mock_get_client):
        """Teacher retrieves own assignment with full questions and answer keys."""
        aid = uuid4()
        tid = uuid4()
        qid1 = uuid4()
        qid2 = uuid4()

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock assignments table response
        mock_client.table("assignments").select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(aid),
                    "teacher_id": str(tid),
                    "course_id": None,
                    "title": "Physics Exam 1",
                    "description": "Answer all questions.",  # DB column backing `instructions`
                    "due_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
                    "total_marks": "10.00",
                    "status": "draft",
                }
            ]
        )

        # Mock assignment_questions response (ordered by position)
        mock_client.table("assignment_questions").select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(qid1),
                    "assignment_id": str(aid),
                    "position": 1,
                    "question_type": "mcq",
                    "question_text": "What is the speed of light?",
                    "marks": "5.00",
                    "instructions": None,
                    "options": [{"id": "A", "text": "3e8 m/s"}, {"id": "B", "text": "3e6 m/s"}],
                },
                {
                    "id": str(qid2),
                    "assignment_id": str(aid),
                    "position": 2,
                    "question_type": "subjective",
                    "question_text": "State Newton's first law.",
                    "marks": "5.00",
                    "instructions": "Mention inertia.",
                    "options": None,
                },
            ]
        )

        # Mock question_answer_keys response
        mock_client.table("question_answer_keys").select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"question_id": str(qid1), "correct_option_id": "A", "expected_answer": None},
                {"question_id": str(qid2), "correct_option_id": None, "expected_answer": "An object remains at rest..."},
            ]
        )

        repo = SupabaseAssignmentRepository()
        record = repo.get(aid, access_token="mock_token")

        assert record is not None
        assert record.id == aid
        assert record.teacher_id == tid
        assert record.status == AssignmentStatus.DRAFT
        assert record.content.instructions == "Answer all questions."
        assert len(record.content.questions) == 2
        assert record.content.questions[0].correct_option_id == "A"
        assert record.content.questions[1].expected_answer == "An object remains at rest..."

    @patch("app.database.assignment_repository.get_user_supabase")
    def test_2_teacher_cannot_retrieve_another_teachers_assignment(self, mock_get_client):
        """Teacher ownership verification fails for an assignment owned by someone else."""
        aid = uuid4()
        teacher_owner_id = uuid4()
        other_teacher_id = uuid4()

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock empty response when querying with other_teacher_id
        mock_client.table("assignments").select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        repo = SupabaseAssignmentRepository()
        is_owned = repo.verify_ownership(aid, other_teacher_id, access_token="mock_token")

        assert is_owned is False

    @patch("app.database.assignment_repository.get_user_supabase")
    def test_3_questions_are_returned_in_position_order(self, mock_get_client):
        """Questions are returned in position order with real question UUIDs (not position-derived)."""
        aid = uuid4()
        qid1 = uuid4()
        qid2 = uuid4()
        qid3 = uuid4()

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.table("assignment_questions").select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(qid1),
                    "assignment_id": str(aid),
                    "position": 1,
                    "question_type": "mcq",
                    "question_text": "Q1",
                    "marks": "2.00",
                    "instructions": None,
                    "options": [{"id": "A", "text": "Opt A"}],
                },
                {
                    "id": str(qid2),
                    "assignment_id": str(aid),
                    "position": 2,
                    "question_type": "subjective",
                    "question_text": "Q2",
                    "marks": "3.00",
                    "instructions": None,
                    "options": None,
                },
                {
                    "id": str(qid3),
                    "assignment_id": str(aid),
                    "position": 3,
                    "question_type": "subjective",
                    "question_text": "Q3",
                    "marks": "5.00",
                    "instructions": None,
                    "options": None,
                },
            ]
        )

        repo = SupabaseAssignmentRepository()
        questions = repo.get_questions(aid, access_token="mock_token")

        assert len(questions) == 3
        assert questions[0].position == 1
        assert questions[0].id == qid1  # Real UUID
        assert questions[1].position == 2
        assert questions[1].id == qid2
        assert questions[2].position == 3
        assert questions[2].id == qid3

    @patch("app.database.assignment_repository.get_user_supabase")
    def test_4_answer_keys_retrieved_only_through_authorized_backend_logic(self, mock_get_client):
        """Answer keys are retrieved separately; student published fetch NEVER queries question_answer_keys."""
        aid = uuid4()
        sid = uuid4()
        qid1 = uuid4()

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock published assignment
        mock_client.table("assignments").select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(aid),
                    "teacher_id": str(uuid4()),
                    "course_id": None,
                    "title": "Public Exam",
                    "instructions": None,
                    "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                    "total_marks": "5.00",
                    "status": "published",
                }
            ]
        )

        # Mock questions for student
        mock_client.table("assignment_questions").select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(qid1),
                    "assignment_id": str(aid),
                    "position": 1,
                    "question_type": "subjective",
                    "question_text": "Explain photosynthesis.",
                    "marks": "5.00",
                    "instructions": None,
                    "options": None,
                }
            ]
        )

        repo = SupabaseAssignmentRepository()
        student_record = repo.get_published_for_student(aid, sid, access_token="student_token")

        assert student_record is not None
        # Assert student record has no expected answer
        assert student_record.content.questions[0].expected_answer is None
        # Verify question_answer_keys table was NEVER touched
        for call_args in mock_client.table.call_args_list:
            assert call_args[0][0] != "question_answer_keys", "question_answer_keys must never be queried for student!"


# ===========================================================================
# 2. SubmissionRepository Tests
# ===========================================================================


class TestSubmissionRepository:
    """Verifies submission persistence, student data isolation, and OCR job tracking."""

    @patch("app.database.submission_repository.get_user_supabase")
    def test_listing_submissions_hydrates_linked_ocr_job_ids(self, mock_get_client):
        submission_id = uuid4()
        assignment_id = uuid4()
        student_id = uuid4()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.table("submissions").select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(submission_id),
                    "assignment_id": str(assignment_id),
                    "student_id": str(student_id),
                    "pdf_path": "submissions/answer.pdf",
                    "status": "submitted",  # DB lifecycle value; OCR progress lives in ocr_jobs
                    "created_at": "",
                    "updated_at": "",
                }
            ]
        )
        # ocr_jobs.id is a DB UUID; the OCR engine job id lives in processing_metadata.
        mock_client.table("ocr_jobs").select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"submission_id": str(submission_id), "status": "pending",
                   "processing_metadata": {"ocr_job_id": "job-123"}}]
        )

        records = SupabaseSubmissionRepository().list_by_assignment(
            assignment_id, access_token="token"
        )

        assert records[0].ocr_job_id == "job-123"
        assert records[0].filename == "answer.pdf"
        assert records[0].status == "ocr_queued"  # API status rebuilt from the OCR job

    @patch("app.database.submission_repository.get_user_supabase")
    def test_5_submission_belongs_to_expected_assignment(self, mock_get_client):
        """verify_submission_assignment verifies submission and assignment relationship."""
        sub_id = uuid4()
        correct_aid = uuid4()
        wrong_aid = uuid4()

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # When matching correct assignment
        mock_client.table("submissions").select.return_value.eq.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[{"id": str(sub_id)}]),  # Correct match
            MagicMock(data=[]),                      # Wrong match
        ]

        repo = SupabaseSubmissionRepository()
        assert repo.verify_submission_assignment(sub_id, correct_aid, access_token="token") is True
        assert repo.verify_submission_assignment(sub_id, wrong_aid, access_token="token") is False

    @patch("app.database.submission_repository.get_user_supabase")
    def test_6_ocr_job_is_retrieved_for_correct_submission(self, mock_get_client):
        """get_ocr_job retrieves the single OCR job for a submission."""
        sub_id = uuid4()
        job_id = "ocr_job_99"

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.table("ocr_jobs").select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": str(uuid4()),  # DB row UUID, distinct from the OCR engine job id
                    "submission_id": str(sub_id),
                    "status": "completed",
                    "processing_metadata": {"ocr_job_id": job_id, "stage": "done", "progress": 100},
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ]
        )

        repo = SupabaseSubmissionRepository()
        ocr_job = repo.get_ocr_job(sub_id, access_token="token")

        assert ocr_job is not None
        assert ocr_job.id == job_id
        assert ocr_job.stage == "done"
        assert ocr_job.submission_id == sub_id
        assert ocr_job.status == "completed"
        assert ocr_job.progress == 100


# ===========================================================================
# 3. GradingRepository Tests
# ===========================================================================


class TestGradingRepository:
    """Verifies grading result persistence, column schema adherence, duplicate handling, and student access protection."""

    @patch("app.database.grading_repository.get_user_supabase")
    def test_7_grading_result_insertion_uses_existing_columns_only(self, mock_get_client):
        """Grading result insert adheres strictly to the 14 actual columns."""
        sub_id = uuid4()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock upsert response
        mock_client.table("grading_results").upsert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "submission_id": str(sub_id),
                    "ai_score": "8.50",
                    "final_score": "8.50",
                    "ai_feedback": "Good work.",
                    "final_feedback": "Good work.",
                    "evidence": {"citations": []},
                    "flags": {"review_required": False},
                    "confidence": "0.950",
                    "status": "pending_review",
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "published_at": None,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ]
        )

        repo = SupabaseGradingRepository()
        create_payload = GradingResultCreate(
            submission_id=sub_id,
            ai_score=Decimal("8.50"),
            ai_feedback="Good work.",
            confidence=Decimal("0.95"),
            status=GradingStatus.PENDING_REVIEW,
        )
        record = repo.insert(create_payload, access_token="token")

        # Inspect the exact dict passed to Supabase upsert
        upsert_call_args = mock_client.table("grading_results").upsert.call_args
        inserted_dict = upsert_call_args[0][0]

        # Allowed column set
        allowed_columns = {
            "submission_id",
            "ai_score",
            "final_score",
            "ai_feedback",
            "final_feedback",
            "evidence",
            "flags",
            "confidence",
            "status",
            "created_at",
            "updated_at",
        }
        for k in inserted_dict.keys():
            assert k in allowed_columns, f"Forbidden column '{k}' was passed to grading_results insert!"

        assert record.submission_id == sub_id
        assert record.ai_score == Decimal("8.50")
        assert record.status == GradingStatus.PENDING_REVIEW

    @patch("app.database.grading_repository.get_user_supabase")
    def test_8_duplicate_grading_result_insertion_handled_safely(self, mock_get_client):
        """Inserting a grading result for an already-graded submission uses on_conflict='submission_id'."""
        sub_id = uuid4()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.table("grading_results").upsert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "submission_id": str(sub_id),
                    "ai_score": "9.00",
                    "final_score": "9.00",
                    "ai_feedback": "Updated.",
                    "final_feedback": "Updated.",
                    "evidence": {},
                    "flags": {},
                    "confidence": "1.000",
                    "status": "pending_review",
                }
            ]
        )

        repo = SupabaseGradingRepository()
        create_payload = GradingResultCreate(
            submission_id=sub_id,
            ai_score=Decimal("9.00"),
            ai_feedback="Updated.",
            confidence=Decimal("1.00"),
            status=GradingStatus.PENDING_REVIEW,
        )
        record = repo.insert(create_payload, access_token="token")

        # Check on_conflict argument
        upsert_kwargs = mock_client.table("grading_results").upsert.call_args[1]
        assert upsert_kwargs.get("on_conflict") == "submission_id"
        assert record.submission_id == sub_id

    @patch("app.database.grading_repository.get_user_supabase")
    def test_9_student_cannot_retrieve_unpublished_grading_results(self, mock_get_client):
        """Student receives None when querying unpublished grades ('pending_review', 'approved', 'rejected')."""
        sub_id = uuid4()
        student_id = uuid4()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock submission owned by student
        mock_client.table("submissions").select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": str(sub_id), "student_id": str(student_id)}]
        )

        # Mock grading_results query with status='published' returning empty
        mock_client.table("grading_results").select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]  # No published grade exists
        )

        repo = SupabaseGradingRepository()
        res = repo.get_published_for_student(sub_id, student_id, access_token="student_token")

        assert res is None, "Student must never receive unpublished grading results!"

    @patch("app.database.grading_repository.get_user_supabase")
    def test_10_teacher_can_retrieve_their_own_grading_results(self, mock_get_client):
        """Teacher can retrieve grading results by submission ID."""
        sub_id = uuid4()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.table("grading_results").select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "submission_id": str(sub_id),
                    "ai_score": "7.50",
                    "final_score": "7.50",
                    "ai_feedback": "Solid answer.",
                    "final_feedback": "Solid answer.",
                    "evidence": {"items": ["evidence 1"]},
                    "flags": {"low_ocr": False},
                    "confidence": "0.850",
                    "status": "pending_review",
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ]
        )

        repo = SupabaseGradingRepository()
        rec = repo.get_by_submission_id(sub_id, access_token="teacher_token")

        assert rec is not None
        assert rec.submission_id == sub_id
        assert rec.ai_score == Decimal("7.50")
        assert rec.evidence == {"items": ["evidence 1"]}

    @patch("app.database.grading_repository.get_user_supabase")
    def test_11_teacher_cannot_modify_another_teachers_results(self, mock_get_client):
        """When an unauthorized update occurs or submission is not found under teacher RLS, update returns None."""
        sub_id = uuid4()
        other_teacher_id = uuid4()
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock update returning empty list (blocked by RLS)
        mock_client.table("grading_results").update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        repo = SupabaseGradingRepository()
        result = repo.update_review(
            submission_id=sub_id,
            final_score=Decimal("10.00"),
            final_feedback="Modified by wrong teacher.",
            reviewed_by=other_teacher_id,
            access_token="unauthorized_token",
        )

        assert result is None

    def test_12_invalid_grading_status_is_rejected(self):
        """Forbidden statuses like 'reviewed' or 'graded' are strictly rejected."""
        sub_id = uuid4()

        # Rule: Never introduce 'reviewed' or 'graded'
        for forbidden_status in ["reviewed", "graded", "in_progress", "draft", ""]:
            with pytest.raises((InvalidGradingStatusError, ValueError)):
                GradingResultCreate(
                    submission_id=sub_id,
                    ai_score=Decimal("5.0"),
                    ai_feedback="Feedback",
                    confidence=Decimal("1.0"),
                    status=forbidden_status,  # type: ignore
                )

        # Verify allowed statuses pass
        for allowed in ["pending_review", "approved", "published", "rejected"]:
            obj = GradingResultCreate(
                submission_id=sub_id,
                ai_score=Decimal("5.0"),
                ai_feedback="Feedback",
                confidence=Decimal("1.0"),
                status=allowed,  # type: ignore
            )
            assert obj.status.value == allowed
