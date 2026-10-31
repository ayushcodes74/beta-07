"""Submission/OCR status mapping onto the live database CHECK constraints (no database).

submissions.status IN (submitted, late_pending, late_accepted, late_rejected, under_review, graded, published)
ocr_jobs.status    IN (pending, processing, completed, failed, needs_review)
"""

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.database.submission_repository import SupabaseSubmissionRepository
from app.services.submission_service import SubmissionValidationError

DB_SUBMISSION_STATUSES = {"submitted", "late_pending", "late_accepted", "late_rejected", "under_review", "graded", "published"}
DB_OCR_STATUSES = {"pending", "processing", "completed", "failed", "needs_review"}


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Records one chained PostgREST call and returns preset data on execute()."""

    def __init__(self, client: "FakeClient", table: str) -> None:
        self.client, self.table = client, table
        self.op: str | None = None
        self.payload: Any = None
        self.filters: dict[str, Any] = {}

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload, **_):
        self.op, self.payload = "upsert", payload
        return self

    def select(self, *_):
        self.op = "select"
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def in_(self, column, values):
        self.filters[column] = values
        return self

    def execute(self):
        self.client.calls.append(self)
        error = self.client.failures.get((self.table, self.op))
        if error is not None:
            raise error
        return _Result(self.client.responses.get((self.table, self.op), [{"ok": True}]))


class FakeClient:
    def __init__(self, responses: dict[tuple[str, str], list] | None = None,
                 failures: dict[tuple[str, str], Exception] | None = None) -> None:
        self.responses = responses or {}
        self.failures = failures or {}
        self.calls: list[_Query] = []

    def table(self, name):
        return _Query(self, name)

    def writes(self, table):
        return [c for c in self.calls if c.table == table and c.op in ("insert", "update", "upsert")]


def _repo(client):
    patcher = patch("app.database.submission_repository.get_user_supabase", return_value=client)
    patcher.start()
    return SupabaseSubmissionRepository(), patcher


def test_create_writes_only_allowed_statuses_and_inserts_ocr_job():
    client = FakeClient({("ocr_jobs", "update"): []})  # new submission: no job row yet
    repo, patcher = _repo(client)
    try:
        record = repo.create(uuid4(), uuid4(), uuid4(), "answer.pdf", "job-abc", "ocr_queued", access_token="t")
    finally:
        patcher.stop()

    (submission_write,) = client.writes("submissions")
    job_update, job_write = client.writes("ocr_jobs")
    assert submission_write.payload["status"] == "submitted"
    assert (job_update.op, job_write.op) == ("update", "insert")  # no ON CONFLICT dependency
    assert job_write.payload["status"] == "pending"
    assert job_write.payload["processing_metadata"]["ocr_job_id"] == "job-abc"
    assert job_write.payload["processing_metadata"]["engine_status"] == "queued"
    assert record.status == "ocr_queued"  # API contract unchanged


@pytest.mark.parametrize(
    ("api_status", "db_ocr_status"),
    [
        ("ocr_processing", "processing"),
        ("ocr_completed", "completed"),
        ("ocr_completed_with_warnings", "completed"),
        ("ocr_degraded", "needs_review"),
        ("ocr_failed", "failed"),
        ("ocr_cancelled", "failed"),
    ],
)
def test_update_status_maps_every_ocr_state(api_status, db_ocr_status):
    sid = uuid4()
    client = FakeClient({("ocr_jobs", "update"): [{"submission_id": str(sid)}]})
    repo, patcher = _repo(client)
    try:
        with patch.object(SupabaseSubmissionRepository, "get", return_value=None):
            repo.update_status(sid, api_status, "job-abc", access_token="t")
    finally:
        patcher.stop()

    (submission_write,) = client.writes("submissions")
    job_writes = client.writes("ocr_jobs")
    assert submission_write.payload["status"] in DB_SUBMISSION_STATUSES
    assert submission_write.payload["status"] == "submitted"
    assert [w.op for w in job_writes] == ["update"]  # row existed: no insert
    assert job_writes[0].payload["status"] == db_ocr_status
    assert job_writes[0].payload["status"] in DB_OCR_STATUSES
    assert job_writes[0].payload["processing_metadata"]["engine_status"] == api_status.removeprefix("ocr_")


def test_update_status_inserts_job_row_when_missing():
    sid = uuid4()
    client = FakeClient({("ocr_jobs", "update"): []})
    repo, patcher = _repo(client)
    try:
        with patch.object(SupabaseSubmissionRepository, "get", return_value=None):
            repo.update_status(sid, "ocr_processing", "job-abc", access_token="t")
    finally:
        patcher.stop()

    assert [w.op for w in client.writes("ocr_jobs")] == ["update", "insert"]
    assert client.writes("ocr_jobs")[1].payload["submission_id"] == str(sid)


def test_lifecycle_statuses_pass_through_unchanged():
    sid = uuid4()
    client = FakeClient()
    repo, patcher = _repo(client)
    try:
        with patch.object(SupabaseSubmissionRepository, "get", return_value=None):
            repo.update_status(sid, "under_review", access_token="t")
    finally:
        patcher.stop()

    (submission_write,) = client.writes("submissions")
    assert submission_write.payload["status"] == "under_review"
    assert client.writes("ocr_jobs") == []


@pytest.mark.parametrize(
    ("job_row", "expected"),
    [
        ({"status": "needs_review", "processing_metadata": {"engine_status": "degraded"}}, "ocr_degraded"),
        ({"status": "completed", "processing_metadata": {"engine_status": "completed_with_warnings"}},
         "ocr_completed_with_warnings"),
        ({"status": "processing", "processing_metadata": {}}, "ocr_processing"),  # older rows: map from DB status
    ],
)
def test_reads_rebuild_api_status_from_ocr_job(job_row, expected):
    sid = uuid4()
    sub_row = {"id": str(sid), "assignment_id": str(uuid4()), "student_id": str(uuid4()),
               "pdf_path": None, "status": "submitted", "created_at": "", "updated_at": ""}
    client = FakeClient({
        ("submissions", "select"): [sub_row],
        ("ocr_jobs", "select"): [{"submission_id": str(sid), **job_row}],
    })
    repo, patcher = _repo(client)
    try:
        record = repo.get(sid, access_token="t")
    finally:
        patcher.stop()

    assert record.status == expected


def test_reads_keep_lifecycle_status_after_ocr():
    sid = uuid4()
    sub_row = {"id": str(sid), "assignment_id": str(uuid4()), "student_id": str(uuid4()),
               "pdf_path": None, "status": "graded", "created_at": "", "updated_at": ""}
    client = FakeClient({
        ("submissions", "select"): [sub_row],
        ("ocr_jobs", "select"): [{"submission_id": str(sid), "status": "completed", "processing_metadata": {}}],
    })
    repo, patcher = _repo(client)
    try:
        record = repo.get(sid, access_token="t")
    finally:
        patcher.stop()

    assert record.status == "graded"


class _Duplicate(Exception):
    code = "23505"


def test_resubmission_reuses_editable_submission_and_replaces_ocr_job():
    existing_id = uuid4()
    client = FakeClient(
        responses={("submissions", "select"): [{"id": str(existing_id), "status": "submitted"}],
                   ("ocr_jobs", "update"): []},  # e.g. the earlier attempt never got an OCR job
        failures={("submissions", "insert"): _Duplicate("duplicate key value violates unique constraint")},
    )
    repo, patcher = _repo(client)
    try:
        record = repo.create(uuid4(), uuid4(), uuid4(), "answer.pdf", "job-new", "ocr_queued", access_token="t")
    finally:
        patcher.stop()

    assert record.id == existing_id
    submission_update = [w for w in client.writes("submissions") if w.op == "update"][0]
    assert submission_update.filters["id"] == str(existing_id)
    assert submission_update.payload["status"] == "submitted"
    job_insert = [w for w in client.writes("ocr_jobs") if w.op == "insert"][0]
    assert job_insert.payload["submission_id"] == str(existing_id)
    assert job_insert.payload["processing_metadata"]["ocr_job_id"] == "job-new"


@pytest.mark.parametrize("status", ["under_review", "graded", "published"])
def test_resubmission_refused_once_grading_started(status):
    client = FakeClient(
        responses={("submissions", "select"): [{"id": str(uuid4()), "status": status}]},
        failures={("submissions", "insert"): _Duplicate("duplicate key value violates unique constraint")},
    )
    repo, patcher = _repo(client)
    try:
        with pytest.raises(SubmissionValidationError) as err:
            repo.create(uuid4(), uuid4(), uuid4(), "answer.pdf", "job-new", "ocr_queued", access_token="t")
    finally:
        patcher.stop()

    assert err.value.code == "already_submitted"
    assert client.writes("ocr_jobs") == []
