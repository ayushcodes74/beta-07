"""Student <-> teacher chat: access rules in MessageService, plus the HTTP layer (repositories faked)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.api.v1.endpoints.messages import get_message_service
from app.database.message_repository import MessageRepositoryError
from app.main import app
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.user import Role
from app.services.auth_service import CurrentUser
from app.services.course_service import CourseNotFoundError, CourseRecord, CourseService, CourseValidationError
from app.services.message_service import MessageService
from tests.conftest import bearer

TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
OTHER_TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
STUDENT = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)
CLASSMATE = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)
OUTSIDER = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)
COURSE = CourseRecord(id=uuid4(), teacher_id=TEACHER.id, name="Digital Logic", created_at=datetime.now(UTC))
ENROLLED = {STUDENT.id, CLASSMATE.id}


class CourseRepo:
    def get(self, course_id, *, access_token):
        return COURSE if course_id == COURSE.id else None

    def is_student_enrolled(self, course_id, student_id, *, access_token):
        return course_id == COURSE.id and student_id in ENROLLED


class MessageRepo:
    """In-memory course_messages table."""

    def __init__(self, fail=False):
        self.rows: list[MessageResponse] = []
        self.fail = fail
        self.thread_rows: list[dict] = []
        self.calls = 0

    def _check(self):
        self.calls += 1
        if self.fail:
            raise MessageRepositoryError("relation course_messages does not exist")

    def list_thread(self, course_id, student_id, *, after, limit, access_token):
        self._check()
        rows = [r for r in self.rows if r.course_id == course_id and r.student_id == student_id]
        if after is not None:
            rows = [r for r in rows if r.created_at > after]
        return sorted(rows, key=lambda r: r.created_at)[-limit:]

    def create(self, course_id, student_id, sender_id, body, *, access_token):
        self._check()
        row = MessageResponse(
            id=uuid4(), course_id=course_id, student_id=student_id, sender_id=sender_id, body=body,
            created_at=datetime.now(UTC) + timedelta(microseconds=len(self.rows)),
        )
        self.rows.append(row)
        return row

    def mark_read(self, course_id, student_id, reader_id, *, access_token):
        self._check()
        updated = 0
        for i, r in enumerate(self.rows):
            if r.course_id == course_id and r.student_id == student_id and r.sender_id != reader_id and not r.read_at:
                self.rows[i] = r.model_copy(update={"read_at": datetime.now(UTC)})
                updated += 1
        return updated

    def list_threads(self, *, access_token):
        self._check()
        return self.thread_rows


def _service(repo):
    return MessageService(CourseService(CourseRepo()), CourseRepo(), repo)


# ---- service: access rules ------------------------------------------------------------


def test_student_and_teacher_share_one_thread():
    repo = MessageRepo()
    svc = _service(repo)

    svc.send(STUDENT, COURSE.id, "Can I get an extension?", access_token="t")
    svc.send(TEACHER, COURSE.id, "Yes, until Friday.", STUDENT.id, access_token="t")

    as_student = svc.get_messages(STUDENT, COURSE.id, access_token="t")
    as_teacher = svc.get_messages(TEACHER, COURSE.id, STUDENT.id, access_token="t")
    assert [m.body for m in as_student] == ["Can I get an extension?", "Yes, until Friday."]
    assert [m.is_mine for m in as_student] == [True, False]
    assert [m.is_mine for m in as_teacher] == [False, True]
    assert {m.student_id for m in repo.rows} == {STUDENT.id}


def test_student_messages_always_go_to_their_own_thread():
    repo = MessageRepo()
    message = _service(repo).send(STUDENT, COURSE.id, "Hello", access_token="t")
    assert message.student_id == STUDENT.id and message.sender_id == STUDENT.id and message.is_mine


def test_student_cannot_read_a_classmates_thread():
    repo = MessageRepo()
    svc = _service(repo)
    svc.send(CLASSMATE, COURSE.id, "private", access_token="t")
    with pytest.raises(CourseNotFoundError):
        svc.get_messages(STUDENT, COURSE.id, CLASSMATE.id, access_token="t")
    with pytest.raises(CourseNotFoundError):
        svc.send(STUDENT, COURSE.id, "spoof", CLASSMATE.id, access_token="t")
    assert all(r.sender_id == CLASSMATE.id for r in repo.rows)


@pytest.mark.parametrize("user", [OTHER_TEACHER, OUTSIDER])
def test_non_members_get_404_before_storage_is_touched(user):
    repo = MessageRepo()
    with pytest.raises(CourseNotFoundError):
        _service(repo).send(user, COURSE.id, "hi", STUDENT.id, access_token="t")
    with pytest.raises(CourseNotFoundError):
        _service(repo).get_messages(user, COURSE.id, STUDENT.id, access_token="t")
    assert repo.calls == 0


def test_teacher_must_choose_an_enrolled_student():
    svc = _service(MessageRepo())
    with pytest.raises(CourseValidationError) as missing:
        svc.send(TEACHER, COURSE.id, "hi", access_token="t")
    assert missing.value.code == "student_required"
    with pytest.raises(CourseValidationError) as stranger:
        svc.send(TEACHER, COURSE.id, "hi", OUTSIDER.id, access_token="t")
    assert stranger.value.code == "student_not_enrolled"


def test_polling_with_after_returns_only_newer_messages():
    repo = MessageRepo()
    svc = _service(repo)
    first = svc.send(STUDENT, COURSE.id, "one", access_token="t")
    svc.send(TEACHER, COURSE.id, "two", STUDENT.id, access_token="t")
    newer = svc.get_messages(STUDENT, COURSE.id, after=first.created_at, access_token="t")
    assert [m.body for m in newer] == ["two"]


def test_mark_read_only_marks_messages_received():
    repo = MessageRepo()
    svc = _service(repo)
    svc.send(STUDENT, COURSE.id, "question", access_token="t")
    svc.send(TEACHER, COURSE.id, "answer", STUDENT.id, access_token="t")

    assert svc.mark_read(TEACHER, COURSE.id, STUDENT.id, access_token="t") == 1
    by_body = {r.body: r for r in repo.rows}
    assert by_body["question"].read_at is not None and by_body["answer"].read_at is None
    assert svc.mark_read(TEACHER, COURSE.id, STUDENT.id, access_token="t") == 0


def test_threads_are_mapped_with_fallback_names_and_sorted_newest_first():
    repo = MessageRepo()
    older, newer = "2026-10-30T10:00:00+00:00", "2026-10-31T09:30:00Z"
    repo.thread_rows = [
        {"course_id": str(COURSE.id), "course_name": "Digital Logic", "student_id": str(STUDENT.id),
         "student_name": None, "teacher_id": str(TEACHER.id), "teacher_name": "Dr. Rao",
         "last_body": "See you", "last_sender_id": str(TEACHER.id), "last_at": older, "unread_count": 0},
        {"course_id": str(COURSE.id), "course_name": "Digital Logic", "student_id": str(CLASSMATE.id),
         "student_name": "Asha", "teacher_id": str(TEACHER.id), "teacher_name": "Dr. Rao",
         "last_body": "Thanks!", "last_sender_id": str(CLASSMATE.id), "last_at": newer, "unread_count": 2},
    ]
    threads = _service(repo).list_threads(TEACHER, access_token="t")
    assert [t.student_name for t in threads] == ["Asha", "Student"]
    assert threads[0].unread_count == 2 and not threads[0].last_message_is_mine
    assert threads[1].last_message_is_mine


def test_message_body_is_trimmed_and_blank_rejected():
    assert MessageCreate(body="  hi  ").body == "hi"
    with pytest.raises(ValueError):
        MessageCreate(body="   ")
    with pytest.raises(ValueError):
        MessageCreate(body="x" * 4001)


# ---- HTTP layer -----------------------------------------------------------------------


@pytest.fixture
def chat_api(client, profiles, make_token):
    """Real auth (signed test tokens + fake profiles); MessageService built on in-memory fakes."""
    repo = MessageRepo()
    app.dependency_overrides[get_message_service] = lambda: _service(repo)

    def headers(user: CurrentUser) -> dict[str, str]:
        profiles.add(user.id, user.role.value)
        return bearer(make_token(user.id))

    return client, repo, headers


def test_http_send_and_read_conversation(chat_api):
    client, repo, headers = chat_api
    url = f"/api/v1/courses/{COURSE.id}/messages"

    sent = client.post(url, json={"body": " Is Q3 graded? "}, headers=headers(STUDENT))
    assert sent.status_code == 201, sent.text
    assert sent.json()["body"] == "Is Q3 graded?" and sent.json()["is_mine"] is True

    reply = client.post(url, json={"body": "Yes", "student_id": str(STUDENT.id)}, headers=headers(TEACHER))
    assert reply.status_code == 201, reply.text

    thread = client.get(url, headers=headers(STUDENT))
    assert thread.status_code == 200
    assert [m["body"] for m in thread.json()] == ["Is Q3 graded?", "Yes"]

    read = client.post(f"{url}/read", json={}, headers=headers(STUDENT))
    assert read.status_code == 200 and read.json() == {"updated": 1}


def test_http_errors(chat_api):
    client, repo, headers = chat_api
    url = f"/api/v1/courses/{COURSE.id}/messages"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(OUTSIDER)).status_code == 404
    missing_student = client.post(url, json={"body": "hi"}, headers=headers(TEACHER))
    assert missing_student.status_code == 422
    assert missing_student.json()["detail"]["code"] == "student_required"
    assert client.post(url, json={"body": "  "}, headers=headers(STUDENT)).status_code == 422

    repo.fail = True
    down = client.get("/api/v1/messages/threads", headers=headers(STUDENT))
    assert down.status_code == 503 and down.json()["detail"]["code"] == "messages_unavailable"


def test_http_after_parameter_filters(chat_api):
    client, repo, headers = chat_api
    url = f"/api/v1/courses/{COURSE.id}/messages"
    first = client.post(url, json={"body": "one"}, headers=headers(STUDENT)).json()
    client.post(url, json={"body": "two"}, headers=headers(STUDENT))
    newer = client.get(url, params={"after": first["created_at"]}, headers=headers(STUDENT))
    assert newer.status_code == 200 and [m["body"] for m in newer.json()] == ["two"]
    assert UUID(newer.json()[0]["id"])
