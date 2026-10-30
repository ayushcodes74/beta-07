"""Module 2: assignment management (mocked repository; no database)."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.endpoints import assignments
from app.core.dependencies import get_token_verifier
from app.schemas.assignment import AssignmentContent, AssignmentCreate, AssignmentStatus
from app.schemas.user import Role
from app.services.assignment_service import (
    AssignmentInUseError,
    AssignmentRecord,
    AssignmentRepositoryError,
    AssignmentService,
    AssignmentValidationError,
    get_assignment_repository,
)
from app.services.auth_service import CurrentUser
from app.services.user_service import get_profile_repository
from conftest import bearer

BASE = "/api/v1/assignments"


class FakeAssignmentRepository:
    """Test double for the pending Supabase repository. Not used in production."""

    def __init__(self) -> None:
        self.records: dict[UUID, AssignmentRecord] = {}
        self.tokens: list[str] = []
        self.in_use: set[UUID] = set()
        self.student_access: dict[UUID, set[UUID]] | None = None  # None = all published

    def _save(self, record: AssignmentRecord) -> AssignmentRecord:
        self.records[record.id] = record
        return record

    def create(self, teacher_id, content, *, access_token):
        self.tokens.append(access_token)
        record = AssignmentRecord(id=uuid4(), teacher_id=teacher_id, status=AssignmentStatus.DRAFT, content=content)
        return self._save(record)

    def get(self, assignment_id, *, access_token):
        self.tokens.append(access_token)
        return self.records.get(assignment_id)

    def list_by_teacher(self, teacher_id, *, access_token):
        self.tokens.append(access_token)
        return [r for r in self.records.values() if r.teacher_id == teacher_id]

    def _student_can_see(self, record, student_id):
        allowed = self.student_access is None or record.id in self.student_access.get(student_id, set())
        return allowed and record.status is AssignmentStatus.PUBLISHED

    def list_published_for_student(self, student_id, *, access_token):
        self.tokens.append(access_token)
        return [r for r in self.records.values() if self._student_can_see(r, student_id)]

    def get_published_for_student(self, assignment_id, student_id, *, access_token):
        self.tokens.append(access_token)
        record = self.records.get(assignment_id)
        return record if record and self._student_can_see(record, student_id) else None

    def replace_content(self, assignment_id, content, *, access_token):
        self.tokens.append(access_token)
        record = self.records.get(assignment_id)
        return record and self._save(record.model_copy(update={"content": content}))

    def set_status(self, assignment_id, status, *, access_token):
        self.tokens.append(access_token)
        record = self.records.get(assignment_id)
        return record and self._save(record.model_copy(update={"status": status}))

    def delete(self, assignment_id, *, access_token):
        self.tokens.append(access_token)
        if assignment_id in self.in_use:
            raise AssignmentInUseError
        return self.records.pop(assignment_id, None) is not None


def future(days: int = 7) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def mcq(**overrides: Any) -> dict[str, Any]:
    question = {
        "type": "mcq",
        "text": "2 + 2 = ?",
        "marks": 2,
        "options": [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}],
        "correct_option_id": "B",
    }
    question.update(overrides)
    return question


def subjective(**overrides: Any) -> dict[str, Any]:
    question = {
        "type": "subjective",
        "text": "Explain photosynthesis.",
        "marks": 8,
        "instructions": "Max 200 words.",
        "expected_answer": "SECRET-EXPECTED-ANSWER",
    }
    question.update(overrides)
    return question


def assignment_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "title": "Biology quiz",
        "instructions": "Answer all questions.",
        "due_at": future(),
        "total_marks": 10,
        "questions": [mcq(), subjective()],
    }
    body.update(overrides)
    return body


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def repo() -> FakeAssignmentRepository:
    return FakeAssignmentRepository()


@pytest.fixture
def api(verifier, profiles, repo) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(assignments.router, prefix="/api/v1")
    test_app.dependency_overrides[get_token_verifier] = lambda: verifier
    test_app.dependency_overrides[get_profile_repository] = lambda: profiles
    test_app.dependency_overrides[get_assignment_repository] = lambda: repo
    return TestClient(test_app)


@pytest.fixture
def make_user(make_token, profiles):
    def _make(role: str) -> tuple[UUID, dict[str, str]]:
        user_id = uuid4()
        profiles.add(user_id, role)
        return user_id, bearer(make_token(user_id))

    return _make


@pytest.fixture
def teacher(make_user):
    return make_user("teacher")


@pytest.fixture
def other_teacher(make_user):
    return make_user("teacher")


@pytest.fixture
def student(make_user):
    return make_user("student")


@pytest.fixture
def draft(api, teacher) -> dict[str, Any]:
    response = api.post(BASE, json=assignment_body(), headers=teacher[1])
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def published(api, teacher, draft) -> dict[str, Any]:
    response = api.post(f"{BASE}/{draft['id']}/publish", headers=teacher[1])
    assert response.status_code == 200, response.text
    return response.json()


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_contains_key(v, key) for v in value)
    return False


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


ALL_ROUTES = [
    ("post", BASE),
    ("get", BASE),
    ("get", f"{BASE}/{uuid4()}"),
    ("patch", f"{BASE}/{uuid4()}"),
    ("delete", f"{BASE}/{uuid4()}"),
    ("post", f"{BASE}/{uuid4()}/publish"),
    ("post", f"{BASE}/{uuid4()}/unpublish"),
]


class TestAuthentication:
    @pytest.mark.parametrize(("method", "path"), ALL_ROUTES)
    def test_unauthenticated_rejected(self, api, repo, method, path):
        response = api.request(method, path, json=assignment_body())
        assert response.status_code == 401
        assert repo.tokens == []

    @pytest.mark.parametrize(("method", "path"), ALL_ROUTES)
    def test_invalid_token_rejected(self, api, repo, method, path):
        response = api.request(method, path, json=assignment_body(), headers=bearer("not-a-jwt"))
        assert response.status_code == 401
        assert repo.tokens == []

    def test_unconfigured_repository_returns_503(self, verifier, profiles, teacher):
        test_app = FastAPI()
        test_app.include_router(assignments.router, prefix="/api/v1")
        test_app.dependency_overrides[get_token_verifier] = lambda: verifier
        test_app.dependency_overrides[get_profile_repository] = lambda: profiles
        response = TestClient(test_app).get(BASE, headers=teacher[1])
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "assignment_service_unavailable"


# --------------------------------------------------------------------------
# Authorization
# --------------------------------------------------------------------------


class TestAuthorization:
    def test_student_cannot_create(self, api, repo, student):
        response = api.post(BASE, json=assignment_body(), headers=student[1])
        assert response.status_code == 403
        assert repo.records == {}

    @pytest.mark.parametrize(
        ("method", "suffix", "body"),
        [
            ("patch", "", {"title": "Hacked"}),
            ("delete", "", None),
            ("post", "/publish", None),
            ("post", "/unpublish", None),
        ],
    )
    def test_student_cannot_modify(self, api, repo, student, published, method, suffix, body):
        response = api.request(method, f"{BASE}/{published['id']}{suffix}", json=body, headers=student[1])
        assert response.status_code == 403
        assert repo.records[UUID(published["id"])].content.title == "Biology quiz"
        assert repo.records[UUID(published["id"])].status is AssignmentStatus.PUBLISHED

    @pytest.mark.parametrize(
        ("method", "suffix", "body"),
        [
            ("get", "", None),
            ("patch", "", {"title": "Hijacked"}),
            ("delete", "", None),
            ("post", "/publish", None),
            ("post", "/unpublish", None),
        ],
    )
    def test_teacher_cannot_touch_another_teachers_assignment(
        self, api, repo, other_teacher, draft, method, suffix, body
    ):
        response = api.request(method, f"{BASE}/{draft['id']}{suffix}", json=body, headers=other_teacher[1])
        assert response.status_code == 404
        record = repo.records[UUID(draft["id"])]
        assert record.content.title == "Biology quiz"
        assert record.status is AssignmentStatus.DRAFT

    def test_teacher_list_excludes_other_teachers(self, api, other_teacher, draft):
        assert api.get(BASE, headers=other_teacher[1]).json() == []

    def test_student_cannot_see_draft_in_list(self, api, student, draft):
        assert api.get(BASE, headers=student[1]).json() == []

    def test_student_cannot_get_draft(self, api, student, draft):
        response = api.get(f"{BASE}/{draft['id']}", headers=student[1])
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "assignment_not_found"

    def test_student_without_access_cannot_get_published(self, api, repo, student, published):
        repo.student_access = {}  # repository/RLS grants this student nothing
        assert api.get(f"{BASE}/{published['id']}", headers=student[1]).status_code == 404
        assert api.get(BASE, headers=student[1]).json() == []

    def test_unpublished_assignment_disappears_for_students(self, api, teacher, student, published):
        api.post(f"{BASE}/{published['id']}/unpublish", headers=teacher[1])
        assert api.get(f"{BASE}/{published['id']}", headers=student[1]).status_code == 404

    def test_owner_cannot_be_set_from_body(self, api, teacher, other_teacher):
        body = assignment_body(teacher_id=str(other_teacher[0]))
        assert api.post(BASE, json=body, headers=teacher[1]).status_code == 422

    def test_repository_receives_callers_token(self, api, repo, teacher, draft):
        assert set(repo.tokens) == {teacher[1]["Authorization"].removeprefix("Bearer ")}


class TestStudentViewHidesAnswers:
    def test_student_get_has_no_answers(self, api, student, published):
        response = api.get(f"{BASE}/{published['id']}", headers=student[1])
        assert response.status_code == 200
        body = response.json()
        assert not _contains_key(body, "correct_option_id")
        assert not _contains_key(body, "expected_answer")
        assert not _contains_key(body, "teacher_id")
        assert "SECRET-EXPECTED-ANSWER" not in response.text
        assert body["questions"][0]["options"] == [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}]
        assert body["questions"][1]["instructions"] == "Max 200 words."

    def test_student_list_has_no_answers(self, api, student, published):
        response = api.get(BASE, headers=student[1])
        assert len(response.json()) == 1
        assert "correct_option_id" not in response.text
        assert "SECRET-EXPECTED-ANSWER" not in response.text

    def test_teacher_sees_answers(self, api, teacher, published):
        body = api.get(f"{BASE}/{published['id']}", headers=teacher[1]).json()
        assert body["questions"][0]["correct_option_id"] == "B"
        assert body["questions"][1]["expected_answer"] == "SECRET-EXPECTED-ANSWER"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({k: v for k, v in assignment_body().items() if k != "title"}, id="missing-title"),
            pytest.param(assignment_body(title="   "), id="blank-title"),
            pytest.param(assignment_body(total_marks=0), id="zero-total"),
            pytest.param(assignment_body(total_marks=-5), id="negative-total"),
            pytest.param(assignment_body(total_marks="lots"), id="non-numeric-total"),
            pytest.param(assignment_body(total_marks=10.555), id="too-many-decimals"),
            pytest.param(assignment_body(questions=[mcq(marks=-1)]), id="negative-question-marks"),
            pytest.param(assignment_body(questions=[mcq(marks=0)]), id="zero-question-marks"),
            pytest.param(assignment_body(questions=[subjective(marks=None)]), id="missing-question-marks"),
            pytest.param(assignment_body(questions=[mcq(options=[{"id": "A", "text": "x"}])]), id="one-option"),
            pytest.param(assignment_body(questions=[mcq(options=[])]), id="no-options"),
            pytest.param(assignment_body(questions=[mcq(correct_option_id="Z")]), id="bad-correct-option"),
            pytest.param(
                assignment_body(questions=[mcq(options=[{"id": "A", "text": "x"}, {"id": "A", "text": "y"}])]),
                id="duplicate-option-ids",
            ),
            pytest.param(assignment_body(questions=[{**mcq(), "type": "essay"}]), id="unknown-type"),
            pytest.param(assignment_body(questions=[{k: v for k, v in mcq().items() if k != "type"}]), id="no-type"),
            pytest.param(assignment_body(questions=[subjective(options=mcq()["options"])]), id="subjective-options"),
            pytest.param(assignment_body(questions=[mcq(), "not-an-object"]), id="malformed-question"),
            pytest.param(assignment_body(total_marks=5), id="question-marks-exceed-total"),
            pytest.param(assignment_body(due_at="2026-13-45T25:00:00Z"), id="invalid-date"),
            pytest.param(assignment_body(due_at="next friday"), id="non-date"),
            pytest.param(assignment_body(due_at="2030-01-01T10:00:00"), id="naive-datetime"),
            pytest.param(assignment_body(status="published"), id="status-on-create"),
            pytest.param(assignment_body(id=str(uuid4())), id="id-on-create"),
        ],
    )
    def test_invalid_create_rejected(self, api, repo, teacher, body):
        response = api.post(BASE, json=body, headers=teacher[1])
        assert response.status_code == 422, response.text
        assert repo.records == {}

    def test_past_deadline_rejected(self, api, repo, teacher):
        response = api.post(BASE, json=assignment_body(due_at="2020-01-01T00:00:00Z"), headers=teacher[1])
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "due_date_in_past"
        assert repo.records == {}

    def test_deadline_normalised_to_utc_without_shifting(self, api, teacher):
        ist = timezone(timedelta(hours=5, minutes=30))
        local = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0).astimezone(ist)
        response = api.post(BASE, json=assignment_body(due_at=local.isoformat()), headers=teacher[1])
        returned = datetime.fromisoformat(response.json()["due_at"])
        assert returned == local
        assert returned.utcoffset() == timedelta(0)

    def test_marks_equal_to_total_allowed(self, api, teacher):
        body = assignment_body(total_marks=10, questions=[mcq(marks=2.5), subjective(marks=7.5)])
        response = api.post(BASE, json=body, headers=teacher[1])
        assert response.status_code == 201
        assert response.json()["total_marks"] == 10.0

    def test_decimal_marks_sum_exactly(self):
        content = AssignmentContent.model_validate(
            assignment_body(total_marks=0.3, questions=[subjective(marks=0.1), subjective(marks=0.2)])
        )
        assert sum(q.marks for q in content.questions) == Decimal("0.3")


# --------------------------------------------------------------------------
# CRUD and publication
# --------------------------------------------------------------------------


class TestCrud:
    def test_create_is_draft_owned_by_caller(self, api, teacher, draft):
        assert draft["status"] == "draft"
        assert draft["teacher_id"] == str(teacher[0])
        assert [q["position"] for q in draft["questions"]] == [1, 2]

    def test_create_without_questions(self, api, teacher):
        response = api.post(BASE, json=assignment_body(questions=[]), headers=teacher[1])
        assert response.status_code == 201

    def test_teacher_retrieves_and_lists_own(self, api, teacher, draft):
        assert api.get(f"{BASE}/{draft['id']}", headers=teacher[1]).json() == draft
        assert api.get(BASE, headers=teacher[1]).json() == [draft]

    def test_unknown_assignment_404(self, api, teacher):
        assert api.get(f"{BASE}/{uuid4()}", headers=teacher[1]).status_code == 404

    def test_invalid_assignment_id_422(self, api, teacher):
        assert api.get(f"{BASE}/not-a-uuid", headers=teacher[1]).status_code == 422

    def test_update_fields(self, api, teacher, draft):
        response = api.patch(
            f"{BASE}/{draft['id']}",
            json={"title": "Updated", "instructions": None, "total_marks": 20},
            headers=teacher[1],
        )
        assert response.status_code == 200
        body = response.json()
        assert (body["title"], body["instructions"], body["total_marks"]) == ("Updated", None, 20.0)
        assert body["questions"] == draft["questions"]

    def test_update_replaces_questions(self, api, teacher, draft):
        response = api.patch(f"{BASE}/{draft['id']}", json={"questions": [subjective(marks=5)]}, headers=teacher[1])
        assert response.status_code == 200
        assert len(response.json()["questions"]) == 1

    def test_update_validates_whole_assignment(self, api, repo, teacher, draft):
        # Lowering total marks below the existing question total must fail.
        response = api.patch(f"{BASE}/{draft['id']}", json={"total_marks": 5}, headers=teacher[1])
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_assignment"
        assert repo.records[UUID(draft["id"])].content.total_marks == 10

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"status": "published"},
            {"teacher_id": str(uuid4())},
            {"id": str(uuid4())},
            {"title": None},
            {"total_marks": None},
            {"due_at": "2030-01-01T10:00:00"},
            {"questions": [mcq(correct_option_id="Z")]},
        ],
    )
    def test_invalid_update_rejected(self, api, repo, teacher, draft, body):
        response = api.patch(f"{BASE}/{draft['id']}", json=body, headers=teacher[1])
        assert response.status_code == 422
        record = repo.records[UUID(draft["id"])]
        assert record.status is AssignmentStatus.DRAFT
        assert record.content.title == "Biology quiz"

    def test_update_past_deadline_rejected(self, api, teacher, draft):
        response = api.patch(f"{BASE}/{draft['id']}", json={"due_at": "2020-01-01T00:00:00Z"}, headers=teacher[1])
        assert response.json()["detail"]["code"] == "due_date_in_past"

    def test_delete(self, api, repo, teacher, draft):
        response = api.delete(f"{BASE}/{draft['id']}", headers=teacher[1])
        assert response.status_code == 204
        assert repo.records == {}
        assert api.get(f"{BASE}/{draft['id']}", headers=teacher[1]).status_code == 404

    def test_delete_refused_when_in_use(self, api, repo, teacher, draft):
        repo.in_use.add(UUID(draft["id"]))
        response = api.delete(f"{BASE}/{draft['id']}", headers=teacher[1])
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "assignment_in_use"
        assert UUID(draft["id"]) in repo.records


class TestPublication:
    def test_publish_makes_visible_to_students(self, api, student, published):
        assert published["status"] == "published"
        assert api.get(f"{BASE}/{published['id']}", headers=student[1]).status_code == 200

    def test_publish_is_idempotent(self, api, teacher, published):
        response = api.post(f"{BASE}/{published['id']}/publish", headers=teacher[1])
        assert response.status_code == 200
        assert response.json()["status"] == "published"

    def test_unpublish(self, api, teacher, published):
        response = api.post(f"{BASE}/{published['id']}/unpublish", headers=teacher[1])
        assert response.status_code == 200
        assert response.json()["status"] == "draft"

    def test_unpublish_draft_is_noop(self, api, teacher, draft):
        response = api.post(f"{BASE}/{draft['id']}/unpublish", headers=teacher[1])
        assert response.json()["status"] == "draft"

    def test_cannot_publish_without_questions(self, api, repo, teacher):
        created = api.post(BASE, json=assignment_body(questions=[]), headers=teacher[1]).json()
        response = api.post(f"{BASE}/{created['id']}/publish", headers=teacher[1])
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "not_publishable"
        assert repo.records[UUID(created["id"])].status is AssignmentStatus.DRAFT

    def test_cannot_publish_after_deadline(self, repo):
        teacher = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
        now = datetime.now(UTC)
        record = repo.create(
            teacher.id, AssignmentCreate.model_validate(assignment_body(due_at=future(1))), access_token="t"
        )
        late_service = AssignmentService(repo, clock=lambda: now + timedelta(days=2))
        with pytest.raises(AssignmentValidationError) as exc_info:
            late_service.publish(teacher, record.id, access_token="t")
        assert exc_info.value.code == "due_date_in_past"
        assert repo.records[record.id].status is AssignmentStatus.DRAFT


class TestServiceDefenceInDepth:
    def test_repository_returning_other_owner_is_rejected(self, repo):
        teacher = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)

        class WrongOwnerRepo(FakeAssignmentRepository):
            def create(self, teacher_id, content, *, access_token):
                return super().create(uuid4(), content, access_token=access_token)

        with pytest.raises(AssignmentRepositoryError):
            AssignmentService(WrongOwnerRepo()).create(
                teacher, AssignmentCreate.model_validate(assignment_body()), access_token="t"
            )

    def test_student_list_drops_drafts_even_if_repository_returns_them(self, repo):
        student = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)
        draft = repo.create(
            uuid4(), AssignmentCreate.model_validate(assignment_body()), access_token="t"
        )

        class LeakyRepo(FakeAssignmentRepository):
            def list_published_for_student(self, student_id, *, access_token):
                return [draft]

        assert AssignmentService(LeakyRepo()).list_for(student, access_token="t") == []

    def test_schema_rejects_mcq_with_wrong_answer(self):
        with pytest.raises(ValidationError):
            AssignmentCreate.model_validate(assignment_body(questions=[mcq(correct_option_id="C")]))
