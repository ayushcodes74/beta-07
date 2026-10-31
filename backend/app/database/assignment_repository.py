"""Supabase implementation of AssignmentRepository and related models.

Maps to existing Supabase tables:
- assignments (id, teacher_id, course_id, title, instructions, due_at, total_marks, status, timestamps)
- assignment_questions (id [UUID], assignment_id, position, question_type, question_text, marks, instructions, options, timestamps)
- question_answer_keys (id, question_id, correct_option_id, expected_answer, teacher_notes, timestamps)

Enforces:
- Real question UUIDs (never generates IDs from question positions).
- Nullable course_id (never substitutes teacher_id for course_id).
- Separation of answer keys (students never retrieve answer keys).
- Questions ordered by position asc.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.database.supabase import get_user_supabase
from app.schemas.assignment import (
    AssignmentContent,
    AssignmentStatus,
    Marks,
    McqOption,
    McqQuestion,
    SubjectiveQuestion,
)
from app.services.assignment_service import (
    AssignmentInUseError,
    AssignmentIntegrationNotConfiguredError,
    AssignmentRecord,
    AssignmentRepository,
    AssignmentRepositoryError,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Database Record Models
# --------------------------------------------------------------------------


class AssignmentQuestionRecord(BaseModel):
    """Database representation of a question in assignment_questions."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    assignment_id: UUID
    position: int
    question_type: str  # 'mcq' or 'subjective'
    question_text: str
    marks: Decimal
    instructions: Optional[str] = None
    options: Optional[List[Dict[str, Any]]] = None


class QuestionAnswerKeyRecord(BaseModel):
    """Database representation of an answer key in question_answer_keys."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    question_id: UUID
    correct_option_id: Optional[str] = None
    expected_answer: Optional[str] = None
    teacher_notes: Optional[str] = None


# --------------------------------------------------------------------------
# Supabase Repository Implementation
# --------------------------------------------------------------------------


class SupabaseAssignmentRepository:
    """Supabase-backed assignment repository operating under the caller's JWT/RLS context."""

    @staticmethod
    def _client(access_token: str):
        try:
            return get_user_supabase(access_token)
        except Exception as exc:
            raise AssignmentIntegrationNotConfiguredError(str(exc)) from exc

    def create(
        self, teacher_id: UUID, content: AssignmentContent, *, access_token: str
    ) -> AssignmentRecord:
        """Store a new assignment as a draft owned by teacher_id."""
        client = self._client(access_token)
        assignment_id = uuid4()
        now_str = datetime.now(UTC).isoformat()

        try:
            # 1. Insert into assignments table (nullable course_id preserved)
            assignment_payload = {
                "id": str(assignment_id),
                "teacher_id": str(teacher_id),
                "course_id": None,
                "title": content.title,
                "instructions": content.instructions,
                "due_at": content.due_at.isoformat(),
                "total_marks": float(content.total_marks),
                "status": AssignmentStatus.DRAFT.value,
                "created_at": now_str,
                "updated_at": now_str,
            }
            client.table("assignments").insert(assignment_payload).execute()

            # 2. Insert questions with real UUIDs and position ordering
            for position, question in enumerate(content.questions, start=1):
                question_id = uuid4()
                q_payload: Dict[str, Any] = {
                    "id": str(question_id),
                    "assignment_id": str(assignment_id),
                    "position": position,
                    "question_type": question.type,
                    "question_text": question.text,
                    "marks": float(question.marks),
                    "instructions": getattr(question, "instructions", None),
                    "options": [opt.model_dump() for opt in question.options]
                    if isinstance(question, McqQuestion)
                    else None,
                    "created_at": now_str,
                    "updated_at": now_str,
                }
                client.table("assignment_questions").insert(q_payload).execute()

                # 3. Store answer key separately in question_answer_keys
                correct_opt = getattr(question, "correct_option_id", None)
                expected_ans = getattr(question, "expected_answer", None)
                if correct_opt is not None or expected_ans is not None:
                    ak_payload = {
                        "id": str(uuid4()),
                        "question_id": str(question_id),
                        "correct_option_id": correct_opt,
                        "expected_answer": expected_ans,
                        "teacher_notes": None,
                        "created_at": now_str,
                        "updated_at": now_str,
                    }
                    client.table("question_answer_keys").insert(ak_payload).execute()

            return AssignmentRecord(
                id=assignment_id,
                teacher_id=teacher_id,
                status=AssignmentStatus.DRAFT,
                content=content,
            )
        except AssignmentRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to create assignment in Supabase: %s", exc)
            raise AssignmentRepositoryError("Failed to create assignment") from exc

    def get(self, assignment_id: UUID, *, access_token: str) -> AssignmentRecord | None:
        """Fetch assignment by ID with full questions and teacher answer keys."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("assignments")
                .select("id, teacher_id, course_id, title, instructions, due_at, total_marks, status")
                .eq("id", str(assignment_id))
                .execute()
            )
            data = resp.data
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data

            # Fetch questions in position order
            questions = self._fetch_questions_with_keys(client, assignment_id)

            content = AssignmentContent(
                title=row["title"],
                instructions=row.get("instructions"),
                due_at=datetime.fromisoformat(row["due_at"]),
                total_marks=Decimal(str(row["total_marks"])),
                questions=questions,
            )

            return AssignmentRecord(
                id=UUID(str(row["id"])),
                teacher_id=UUID(str(row["teacher_id"])),
                status=AssignmentStatus(row["status"]),
                content=content,
            )
        except AssignmentRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to fetch assignment from Supabase: %s", exc)
            raise AssignmentRepositoryError("Failed to fetch assignment") from exc

    def list_by_teacher(self, teacher_id: UUID, *, access_token: str) -> list[AssignmentRecord]:
        """List all assignments belonging to a teacher."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("assignments")
                .select("id, teacher_id, course_id, title, instructions, due_at, total_marks, status")
                .eq("teacher_id", str(teacher_id))
                .execute()
            )
            rows = resp.data or []
            records: list[AssignmentRecord] = []

            for row in rows:
                assignment_id = UUID(str(row["id"]))
                questions = self._fetch_questions_with_keys(client, assignment_id)
                content = AssignmentContent(
                    title=row["title"],
                    instructions=row.get("instructions"),
                    due_at=datetime.fromisoformat(row["due_at"]),
                    total_marks=Decimal(str(row["total_marks"])),
                    questions=questions,
                )
                records.append(
                    AssignmentRecord(
                        id=assignment_id,
                        teacher_id=UUID(str(row["teacher_id"])),
                        status=AssignmentStatus(row["status"]),
                        content=content,
                    )
                )

            return records
        except AssignmentRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list assignments by teacher: %s", exc)
            raise AssignmentRepositoryError("Failed to list assignments") from exc

    def get_published_for_student(
        self, assignment_id: UUID, student_id: UUID, *, access_token: str
    ) -> AssignmentRecord | None:
        """Fetch published assignment for a student. Answer keys are strictly omitted."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("assignments")
                .select("id, teacher_id, course_id, title, instructions, due_at, total_marks, status")
                .eq("id", str(assignment_id))
                .eq("status", AssignmentStatus.PUBLISHED.value)
                .execute()
            )
            data = resp.data
            if not data:
                return None
            row = data[0] if isinstance(data, list) else data

            # Check course enrollment if course_id is set
            course_id = row.get("course_id")
            if course_id:
                enroll_resp = (
                    client.table("course_enrollments")
                    .select("id")
                    .eq("course_id", str(course_id))
                    .eq("student_id", str(student_id))
                    .execute()
                )
                if not enroll_resp.data:
                    return None

            # Fetch questions WITHOUT answer keys
            questions = self._fetch_questions_student_safe(client, assignment_id)

            content = AssignmentContent(
                title=row["title"],
                instructions=row.get("instructions"),
                due_at=datetime.fromisoformat(row["due_at"]),
                total_marks=Decimal(str(row["total_marks"])),
                questions=questions,
            )

            return AssignmentRecord(
                id=UUID(str(row["id"])),
                teacher_id=UUID(str(row["teacher_id"])),
                status=AssignmentStatus.PUBLISHED,
                content=content,
            )
        except AssignmentRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to fetch published assignment for student: %s", exc)
            raise AssignmentRepositoryError("Failed to fetch published assignment") from exc

    def list_published_for_student(
        self, student_id: UUID, *, access_token: str
    ) -> list[AssignmentRecord]:
        """List published assignments accessible to this student without answer keys."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("assignments")
                .select("id, teacher_id, course_id, title, instructions, due_at, total_marks, status")
                .eq("status", AssignmentStatus.PUBLISHED.value)
                .execute()
            )
            rows = resp.data or []
            records: list[AssignmentRecord] = []

            for row in rows:
                assignment_id = UUID(str(row["id"]))
                course_id = row.get("course_id")

                if course_id:
                    enroll_resp = (
                        client.table("course_enrollments")
                        .select("id")
                        .eq("course_id", str(course_id))
                        .eq("student_id", str(student_id))
                        .execute()
                    )
                    if not enroll_resp.data:
                        continue

                questions = self._fetch_questions_student_safe(client, assignment_id)
                content = AssignmentContent(
                    title=row["title"],
                    instructions=row.get("instructions"),
                    due_at=datetime.fromisoformat(row["due_at"]),
                    total_marks=Decimal(str(row["total_marks"])),
                    questions=questions,
                )
                records.append(
                    AssignmentRecord(
                        id=assignment_id,
                        teacher_id=UUID(str(row["teacher_id"])),
                        status=AssignmentStatus.PUBLISHED,
                        content=content,
                    )
                )

            return records
        except AssignmentRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list published assignments for student: %s", exc)
            raise AssignmentRepositoryError("Failed to list published assignments") from exc

    def replace_content(
        self, assignment_id: UUID, content: AssignmentContent, *, access_token: str
    ) -> AssignmentRecord | None:
        """Replace assignment content, questions, and answer keys."""
        client = self._client(access_token)
        now_str = datetime.now(UTC).isoformat()

        try:
            # 1. Update assignment record
            update_payload = {
                "title": content.title,
                "instructions": content.instructions,
                "due_at": content.due_at.isoformat(),
                "total_marks": float(content.total_marks),
                "updated_at": now_str,
            }
            update_resp = (
                client.table("assignments")
                .update(update_payload)
                .eq("id", str(assignment_id))
                .execute()
            )
            if not update_resp.data:
                return None
            row = update_resp.data[0] if isinstance(update_resp.data, list) else update_resp.data

            # 2. Remove old questions (and cascading answer keys)
            client.table("assignment_questions").delete().eq("assignment_id", str(assignment_id)).execute()

            # 3. Insert new questions and answer keys
            for position, question in enumerate(content.questions, start=1):
                question_id = uuid4()
                q_payload: Dict[str, Any] = {
                    "id": str(question_id),
                    "assignment_id": str(assignment_id),
                    "position": position,
                    "question_type": question.type,
                    "question_text": question.text,
                    "marks": float(question.marks),
                    "instructions": getattr(question, "instructions", None),
                    "options": [opt.model_dump() for opt in question.options]
                    if isinstance(question, McqQuestion)
                    else None,
                    "created_at": now_str,
                    "updated_at": now_str,
                }
                client.table("assignment_questions").insert(q_payload).execute()

                correct_opt = getattr(question, "correct_option_id", None)
                expected_ans = getattr(question, "expected_answer", None)
                if correct_opt is not None or expected_ans is not None:
                    ak_payload = {
                        "id": str(uuid4()),
                        "question_id": str(question_id),
                        "correct_option_id": correct_opt,
                        "expected_answer": expected_ans,
                        "teacher_notes": None,
                        "created_at": now_str,
                        "updated_at": now_str,
                    }
                    client.table("question_answer_keys").insert(ak_payload).execute()

            return AssignmentRecord(
                id=assignment_id,
                teacher_id=UUID(str(row["teacher_id"])),
                status=AssignmentStatus(row["status"]),
                content=content,
            )
        except AssignmentRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to replace assignment content: %s", exc)
            raise AssignmentRepositoryError("Failed to replace assignment content") from exc

    def set_status(
        self, assignment_id: UUID, status: AssignmentStatus, *, access_token: str
    ) -> AssignmentRecord | None:
        """Update assignment status (draft/published)."""
        client = self._client(access_token)
        now_str = datetime.now(UTC).isoformat()
        try:
            resp = (
                client.table("assignments")
                .update({"status": status.value, "updated_at": now_str})
                .eq("id", str(assignment_id))
                .execute()
            )
            if not resp.data:
                return None
            return self.get(assignment_id, access_token=access_token)
        except AssignmentRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to update assignment status: %s", exc)
            raise AssignmentRepositoryError("Failed to update assignment status") from exc

    def delete(self, assignment_id: UUID, *, access_token: str) -> bool:
        """Delete assignment. Refuses with AssignmentInUseError if submissions exist."""
        client = self._client(access_token)
        try:
            # Check for existing submissions
            sub_resp = (
                client.table("submissions")
                .select("id")
                .eq("assignment_id", str(assignment_id))
                .execute()
            )
            if sub_resp.data:
                raise AssignmentInUseError("This assignment cannot be deleted because submissions depend on it.")

            del_resp = client.table("assignments").delete().eq("id", str(assignment_id)).execute()
            return bool(del_resp.data)
        except AssignmentInUseError:
            raise
        except Exception as exc:
            logger.exception("Failed to delete assignment: %s", exc)
            raise AssignmentRepositoryError("Failed to delete assignment") from exc

    def get_questions(
        self, assignment_id: UUID, *, access_token: str
    ) -> list[AssignmentQuestionRecord]:
        """Retrieve assignment questions ordered strictly by position asc."""
        client = self._client(access_token)
        try:
            q_resp = (
                client.table("assignment_questions")
                .select("id, assignment_id, position, question_type, question_text, marks, instructions, options")
                .eq("assignment_id", str(assignment_id))
                .order("position")
                .execute()
            )
            rows = q_resp.data or []
            return [
                AssignmentQuestionRecord(
                    id=UUID(str(r["id"])),
                    assignment_id=UUID(str(r["assignment_id"])),
                    position=int(r["position"]),
                    question_type=str(r["question_type"]),
                    question_text=str(r["question_text"]),
                    marks=Decimal(str(r["marks"])),
                    instructions=r.get("instructions"),
                    options=r.get("options"),
                )
                for r in rows
            ]
        except Exception as exc:
            logger.exception("Failed to get questions for assignment: %s", exc)
            raise AssignmentRepositoryError("Failed to get assignment questions") from exc

    def get_answer_keys(
        self, assignment_id: UUID, *, access_token: str
    ) -> dict[UUID, QuestionAnswerKeyRecord]:
        """Retrieve answer keys for assignment questions (authorized teacher logic only)."""
        client = self._client(access_token)
        try:
            questions = self.get_questions(assignment_id, access_token=access_token)
            if not questions:
                return {}

            q_ids = [str(q.id) for q in questions]
            ak_resp = (
                client.table("question_answer_keys")
                .select("id, question_id, correct_option_id, expected_answer, teacher_notes")
                .in_("question_id", q_ids)
                .execute()
            )
            rows = ak_resp.data or []
            return {
                UUID(str(r["question_id"])): QuestionAnswerKeyRecord(
                    id=UUID(str(r["id"])),
                    question_id=UUID(str(r["question_id"])),
                    correct_option_id=r.get("correct_option_id"),
                    expected_answer=r.get("expected_answer"),
                    teacher_notes=r.get("teacher_notes"),
                )
                for r in rows
            }
        except Exception as exc:
            logger.exception("Failed to get answer keys for assignment: %s", exc)
            raise AssignmentRepositoryError("Failed to get answer keys") from exc

    def verify_ownership(
        self, assignment_id: UUID, teacher_id: UUID, *, access_token: str
    ) -> bool:
        """Verify that an assignment is owned by the specified teacher."""
        client = self._client(access_token)
        try:
            resp = (
                client.table("assignments")
                .select("id")
                .eq("id", str(assignment_id))
                .eq("teacher_id", str(teacher_id))
                .execute()
            )
            return bool(resp.data)
        except Exception as exc:
            logger.exception("Failed to verify assignment ownership: %s", exc)
            return False

    # ---- Internal Helpers -------------------------------------------------

    def _fetch_questions_with_keys(
        self, client: Any, assignment_id: UUID
    ) -> list[Any]:
        """Fetch questions in position order with teacher-only answer keys attached."""
        q_resp = (
            client.table("assignment_questions")
            .select("id, assignment_id, position, question_type, question_text, marks, instructions, options")
            .eq("assignment_id", str(assignment_id))
            .order("position")
            .execute()
        )
        q_rows = q_resp.data or []
        if not q_rows:
            return []

        q_ids = [str(r["id"]) for r in q_rows]
        ak_resp = (
            client.table("question_answer_keys")
            .select("question_id, correct_option_id, expected_answer")
            .in_("question_id", q_ids)
            .execute()
        )
        ak_map = {str(r["question_id"]): r for r in (ak_resp.data or [])}

        questions: list[Any] = []
        for r in q_rows:
            qid = str(r["id"])
            ak = ak_map.get(qid, {})
            if r["question_type"] == "mcq":
                raw_options = r.get("options") or []
                options = [
                    McqOption(id=opt["id"], text=opt["text"])
                    for opt in raw_options
                ]
                questions.append(
                    McqQuestion(
                        type="mcq",
                        text=r["question_text"],
                        marks=Decimal(str(r["marks"])),
                        options=options,
                        correct_option_id=ak.get("correct_option_id") or (options[0].id if options else "A"),
                    )
                )
            else:
                questions.append(
                    SubjectiveQuestion(
                        type="subjective",
                        text=r["question_text"],
                        marks=Decimal(str(r["marks"])),
                        instructions=r.get("instructions"),
                        expected_answer=ak.get("expected_answer"),
                    )
                )
        return questions

    def _fetch_questions_student_safe(
        self, client: Any, assignment_id: UUID
    ) -> list[Any]:
        """Fetch questions in position order. Answer keys are strictly omitted from DB queries."""
        q_resp = (
            client.table("assignment_questions")
            .select("id, assignment_id, position, question_type, question_text, marks, instructions, options")
            .eq("assignment_id", str(assignment_id))
            .order("position")
            .execute()
        )
        q_rows = q_resp.data or []
        questions: list[Any] = []

        for r in q_rows:
            if r["question_type"] == "mcq":
                raw_options = r.get("options") or []
                options = [
                    McqOption(id=opt["id"], text=opt["text"])
                    for opt in raw_options
                ]
                # Placeholder so McqQuestion model passes internal validation
                # (student_view serializer strips this field before returning to client)
                first_opt_id = options[0].id if options else "PROTECTED"
                questions.append(
                    McqQuestion(
                        type="mcq",
                        text=r["question_text"],
                        marks=Decimal(str(r["marks"])),
                        options=options,
                        correct_option_id=first_opt_id,
                    )
                )
            else:
                questions.append(
                    SubjectiveQuestion(
                        type="subjective",
                        text=r["question_text"],
                        marks=Decimal(str(r["marks"])),
                        instructions=r.get("instructions"),
                        expected_answer=None,  # Never populated for students
                    )
                )
        return questions

