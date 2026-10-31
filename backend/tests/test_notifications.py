"""Dashboard notifications: who gets told what (service, faked storage) and the /notifications API."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.database.notification_repository import NotificationRepositoryError
from app.main import app
from app.schemas.notification import NotificationResponse
from app.schemas.user import Role
from app.services.auth_service import CurrentUser
from app.services.notification_service import NotificationService, get_notification_repository
from tests.conftest import bearer

TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER, display_name="Dr. Rao")
STUDENT = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT, display_name="Asha")
OTHER_STUDENT = uuid4()
COURSE = uuid4()
OTHER_COURSE = uuid4()
ASSIGNMENT = uuid4()
SUBMISSION = uuid4()
TOKEN = "token"


class FakeRepo:
    def __init__(self, *, assignment_status="published", course_id=COURSE, submission_status="ocr_completed", fail=False):
        self.inserted: list[dict] = []
        self.read_calls: list[tuple] = []
        self.assignment = {
            "id": str(ASSIGNMENT), "teacher_id": str(TEACHER.id), "course_id": str(course_id) if course_id else None,
            "title": "Boolean Algebra HW", "status": assignment_status,
        }
        self.submission = {
            "id": str(SUBMISSION), "student_id": str(STUDENT.id), "assignment_id": str(ASSIGNMENT),
            "status": submission_status,
        }
        self.enrolled = {COURSE: [STUDENT.id, OTHER_STUDENT], OTHER_COURSE: [OTHER_STUDENT]}
        self.fail = fail
        self.items: list[NotificationResponse] = []

    def insert_many(self, rows, *, access_token):
        if self.fail:
            raise NotificationRepositoryError("relation public.notifications does not exist")
        self.inserted.extend(rows)

    def list_for_recipient(self, recipient_id, limit, *, access_token):
        return self.items[:limit]

    def count_unread(self, recipient_id, *, access_token):
        return sum(1 for item in self.items if item.read_at is None)

    def mark_read(self, recipient_id, ids, *, access_token):
        self.read_calls.append((recipient_id, ids))

    def active_student_ids(self, course_ids, *, access_token):
        return list(dict.fromkeys(s for c in course_ids for s in self.enrolled.get(c, [])))

    def course_ids_for_teacher(self, teacher_id, *, access_token):
        return [COURSE, OTHER_COURSE]

    def assignment_info(self, assignment_id, *, access_token):
        return self.assignment if assignment_id == ASSIGNMENT else None

    def submission_info(self, submission_id, *, access_token):
        return self.submission if submission_id == SUBMISSION else None


def _recipients(repo):
    return {UUID(row["recipient_id"]) for row in repo.inserted}


# ---------------------------------------------------------------- teacher -> students


def test_publishing_notifies_every_enrolled_student():
    repo = FakeRepo()
    NotificationService(repo).notify_assignment_published(TEACHER, ASSIGNMENT, updated=False, access_token=TOKEN)
    assert _recipients(repo) == {STUDENT.id, OTHER_STUDENT}
    row = repo.inserted[0]
    assert row["type"] == "assignment_published"
    assert row["title"] == "New assignment: Boolean Algebra HW"
    assert "Dr. Rao" in row["body"]
    assert row["actor_id"] == str(TEACHER.id)
    assert row["link"] == f"/app/student/submit/{ASSIGNMENT}"


def test_editing_a_published_assignment_sends_an_update():
    repo = FakeRepo()
    NotificationService(repo).notify_assignment_published(TEACHER, ASSIGNMENT, updated=True, access_token=TOKEN)
    assert {row["type"] for row in repo.inserted} == {"assignment_updated"}
    assert repo.inserted[0]["title"].startswith("Assignment updated:")


def test_drafts_are_never_announced():
    repo = FakeRepo(assignment_status="draft")
    NotificationService(repo).notify_assignment_published(TEACHER, ASSIGNMENT, updated=False, access_token=TOKEN)
    assert repo.inserted == []


def test_assignment_without_course_reaches_all_of_the_teachers_students_once():
    repo = FakeRepo(course_id=None)
    NotificationService(repo).notify_assignment_published(TEACHER, ASSIGNMENT, updated=False, access_token=TOKEN)
    assert sorted(row["recipient_id"] for row in repo.inserted) == sorted([str(STUDENT.id), str(OTHER_STUDENT)])


@pytest.mark.parametrize(("updated", "kind", "heading"), [
    (False, "result_published", "Result published: Boolean Algebra HW"),
    (True, "result_updated", "Result updated: Boolean Algebra HW"),
])
def test_result_goes_to_the_submitting_student(updated, kind, heading):
    repo = FakeRepo()
    NotificationService(repo).notify_result_published(
        TEACHER, SUBMISSION, updated=updated, final_score=17.50, max_score=20, access_token=TOKEN
    )
    assert _recipients(repo) == {STUDENT.id}
    row = repo.inserted[0]
    assert (row["type"], row["title"]) == (kind, heading)
    assert "17.5/20" in row["body"]
    assert row["submission_id"] == str(SUBMISSION)


def test_late_decision_accepted_mentions_penalty_and_note():
    repo = FakeRepo()
    NotificationService(repo).notify_late_decision(
        TEACHER, submission_id=SUBMISSION, assignment_id=ASSIGNMENT, student_id=STUDENT.id,
        decision="accepted", penalty_percent=10, note="Medical leave", access_token=TOKEN,
    )
    body = repo.inserted[0]["body"]
    assert "10% penalty" in body and "Medical leave" in body


def test_reopening_a_late_decision_is_silent():
    repo = FakeRepo()
    NotificationService(repo).notify_late_decision(
        TEACHER, submission_id=SUBMISSION, assignment_id=ASSIGNMENT, student_id=STUDENT.id,
        decision="pending", penalty_percent=0, note=None, access_token=TOKEN,
    )
    assert repo.inserted == []


def test_review_resolution_includes_teacher_reply():
    repo = FakeRepo()
    NotificationService(repo).notify_review_resolved(
        TEACHER, submission_id=SUBMISSION, student_id=STUDENT.id, status="resolved",
        teacher_response="Q3 re-marked.", access_token=TOKEN,
    )
    row = repo.inserted[0]
    assert row["title"] == "Review request resolved: Boolean Algebra HW"
    assert "Q3 re-marked." in row["body"]


# ---------------------------------------------------------------- student -> teacher


@pytest.mark.parametrize(("late", "heading", "link"), [
    (False, "New submission: Boolean Algebra HW", "/app/submissions"),
    (True, "Late submission: Boolean Algebra HW", "/app/late-submissions"),
])
def test_submission_notifies_the_owning_teacher(late, heading, link):
    repo = FakeRepo()
    NotificationService(repo).notify_submission_received(
        STUDENT, assignment_id=ASSIGNMENT, submission_id=SUBMISSION, late=late, access_token=TOKEN
    )
    assert _recipients(repo) == {TEACHER.id}
    row = repo.inserted[0]
    assert (row["type"], row["title"], row["link"]) == ("submission_received", heading, link)
    assert "Asha" in row["body"]


def test_review_request_notifies_teacher():
    repo = FakeRepo()
    NotificationService(repo).notify_review_requested(
        STUDENT, submission_id=SUBMISSION, reason="Question 2 was marked wrong.", access_token=TOKEN
    )
    assert _recipients(repo) == {TEACHER.id}
    assert repo.inserted[0]["link"] == "/app/reviews?tab=requests"


# ---------------------------------------------------------------- robustness


def test_storage_failure_never_raises():
    repo = FakeRepo(fail=True)
    service = NotificationService(repo)
    service.notify_assignment_published(TEACHER, ASSIGNMENT, updated=False, access_token=TOKEN)
    service.notify_submission_received(STUDENT, assignment_id=ASSIGNMENT, submission_id=SUBMISSION, late=False, access_token=TOKEN)


def test_actor_is_never_its_own_recipient():
    repo = FakeRepo()
    repo.enrolled[COURSE].append(TEACHER.id)
    NotificationService(repo).notify_assignment_published(TEACHER, ASSIGNMENT, updated=False, access_token=TOKEN)
    assert TEACHER.id not in _recipients(repo)


def test_status_lookup_failure_returns_none():
    class Broken(FakeRepo):
        def assignment_info(self, assignment_id, *, access_token):
            raise NotificationRepositoryError("down")

    assert NotificationService(Broken()).assignment_status(ASSIGNMENT, access_token=TOKEN) is None


# ---------------------------------------------------------------- API


@pytest.fixture
def repo():
    fake = FakeRepo()
    app.dependency_overrides[get_notification_repository] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_notification_repository, None)


def test_list_and_mark_read_endpoints(client, profiles, make_token, repo):
    user_id = uuid4()
    profiles.add(user_id, "student")
    token = make_token(user_id)
    now = datetime.now(UTC)
    repo.items = [
        NotificationResponse(id=uuid4(), type="result_published", title="Result published: HW", created_at=now),
        NotificationResponse(id=uuid4(), type="assignment_published", title="New assignment: HW", created_at=now,
                             read_at=now),
    ]

    response = client.get("/api/v1/notifications", headers=bearer(token))
    assert response.status_code == 200
    data = response.json()
    assert data["unread_count"] == 1
    assert [item["type"] for item in data["items"]] == ["result_published", "assignment_published"]

    first = data["items"][0]["id"]
    assert client.post("/api/v1/notifications/read", json={"ids": [first]}, headers=bearer(token)).status_code == 204
    assert client.post("/api/v1/notifications/read", json={}, headers=bearer(token)).status_code == 204
    assert repo.read_calls == [(user_id, [UUID(first)]), (user_id, None)]


def test_notifications_require_authentication(client):
    assert client.get("/api/v1/notifications").status_code == 401


# ---------------------------------------------------------------- endpoint wiring


class RecordingNotifier:
    """Stands in for NotificationService in the assignment endpoints; records what would be sent."""

    def __init__(self, repo):
        self.repo = repo
        self.sent: list[tuple[UUID, bool]] = []

    def assignment_status(self, assignment_id, *, access_token):
        record = self.repo.get(assignment_id, access_token=access_token)
        return record.status.value if record else None

    def notify_assignment_published(self, teacher, assignment_id, *, updated, access_token):
        self.sent.append((assignment_id, updated))


def test_assignment_endpoints_announce_publish_once_and_published_edits(verifier, profiles, make_token):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.endpoints import assignments
    from app.api.v1.endpoints.notifications import get_notification_service
    from app.core.dependencies import get_token_verifier
    from app.services.assignment_service import get_assignment_repository
    from app.services.user_service import get_profile_repository
    from tests.test_assignments import BASE, FakeAssignmentRepository, assignment_body

    assignment_repo = FakeAssignmentRepository()
    notifier = RecordingNotifier(assignment_repo)
    test_app = FastAPI()
    test_app.include_router(assignments.router, prefix="/api/v1")
    test_app.dependency_overrides[get_token_verifier] = lambda: verifier
    test_app.dependency_overrides[get_profile_repository] = lambda: profiles
    test_app.dependency_overrides[get_assignment_repository] = lambda: assignment_repo
    test_app.dependency_overrides[get_notification_service] = lambda: notifier
    api = TestClient(test_app)
    teacher_id = uuid4()
    profiles.add(teacher_id, "teacher")
    headers = bearer(make_token(teacher_id))

    draft = api.post(BASE, json=assignment_body(), headers=headers).json()
    api.patch(f"{BASE}/{draft['id']}", json={"title": "Draft edit"}, headers=headers)
    assert notifier.sent == []  # creating and editing a draft: students cannot see it yet

    api.post(f"{BASE}/{draft['id']}/publish", headers=headers)
    api.post(f"{BASE}/{draft['id']}/publish", headers=headers)  # idempotent re-publish
    api.patch(f"{BASE}/{draft['id']}", json={"title": "Published edit"}, headers=headers)
    assert notifier.sent == [(UUID(draft["id"]), False), (UUID(draft["id"]), True)]
