"""Listing pages must cost a fixed number of Supabase queries, not one (or more) per assignment.

Each query is a network round trip to the hosted project (~100-500 ms), so per-assignment queries made
the dashboard, assignments and submissions pages slower with every assignment a teacher created.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from app.database.assignment_repository import SupabaseAssignmentRepository
from app.database.submission_repository import SupabaseSubmissionRepository


class _Query:
    def __init__(self, client: "_CountingClient", table: str) -> None:
        self.client, self.table, self.filters = client, table, {}

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters[column] = [value]
        return self

    def in_(self, column, values):
        self.filters[column] = list(values)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        self.client.queries.append(self.table)
        rows = self.client.tables.get(self.table, [])
        for column, allowed in self.filters.items():
            rows = [r for r in rows if str(r.get(column)) in {str(v) for v in allowed}]

        class _Response:
            data = rows

        return _Response()


class _CountingClient:
    def __init__(self, tables: dict) -> None:
        self.tables, self.queries = tables, []

    def table(self, name: str) -> _Query:
        return _Query(self, name)


def _tables(n_assignments: int, *, course_id: str | None = None):
    teacher = str(uuid4())
    due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    assignments, questions, keys, submissions = [], [], [], []
    for i in range(n_assignments):
        aid = str(uuid4())
        assignments.append({
            "id": aid, "teacher_id": teacher, "course_id": course_id, "title": f"A{i}", "description": None,
            "due_at": due, "total_marks": "5", "status": "published",
        })
        for pos in (2, 1):  # stored out of order on purpose
            qid = str(uuid4())
            questions.append({
                "id": qid, "assignment_id": aid, "position": pos, "question_type": "subjective",
                "question_text": f"A{i} Q{pos}", "marks": "2", "instructions": None, "options": None,
            })
            keys.append({"question_id": qid, "correct_option_id": None, "expected_answer": f"key {i}.{pos}"})
        submissions.append({"id": str(uuid4()), "assignment_id": aid, "student_id": str(uuid4()),
                            "status": "submitted", "created_at": due, "updated_at": due})
    return teacher, {
        "assignments": assignments, "assignment_questions": questions, "question_answer_keys": keys,
        "submissions": submissions, "ocr_jobs": [],
    }


def test_teacher_assignment_list_uses_a_fixed_number_of_queries():
    for n in (1, 12):
        teacher, tables = _tables(n)
        client = _CountingClient(tables)
        with patch("app.database.assignment_repository.get_user_supabase", return_value=client):
            records = SupabaseAssignmentRepository().list_by_teacher(teacher, access_token="t")
        assert len(records) == n
        assert client.queries == ["assignments", "assignment_questions", "question_answer_keys"]
        first = records[0].content.questions
        assert [q.text for q in first] == ["A0 Q1", "A0 Q2"]  # position order per assignment
        assert first[0].expected_answer == "key 0.1"


def test_student_assignment_list_never_reads_answer_keys_and_is_batched():
    course = str(uuid4())
    student = str(uuid4())
    _, tables = _tables(10, course_id=course)
    tables["course_enrollments"] = [{"course_id": course, "student_id": student}]
    client = _CountingClient(tables)
    with patch("app.database.assignment_repository.get_user_supabase", return_value=client):
        records = SupabaseAssignmentRepository().list_published_for_student(student, access_token="t")
    assert len(records) == 10
    assert client.queries == ["assignments", "course_enrollments", "assignment_questions"]
    assert all(q.expected_answer is None for r in records for q in r.content.questions)

    # Not enrolled: nothing listed, and no question query at all.
    client = _CountingClient({**tables, "course_enrollments": []})
    with patch("app.database.assignment_repository.get_user_supabase", return_value=client):
        assert SupabaseAssignmentRepository().list_published_for_student(student, access_token="t") == []


def test_submissions_for_many_assignments_is_one_query_plus_ocr_jobs():
    _, tables = _tables(15)
    client = _CountingClient(tables)
    ids = [a["id"] for a in tables["assignments"]]
    with patch("app.database.submission_repository.get_user_supabase", return_value=client):
        records = SupabaseSubmissionRepository().list_by_assignments(ids, access_token="t")
    assert len(records) == 15
    assert client.queries == ["submissions", "ocr_jobs"]
