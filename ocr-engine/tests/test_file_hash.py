"""GET /api/v1/ocr/file-hash/{job_id}: SHA-256 of the stored submission PDF (exact-duplicate detection)."""

import hashlib
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.app import app
from app.jobs.job_manager import JobManager


def _client(monkeypatch, jobs):
    store = JobManager.get_instance().store
    monkeypatch.setattr(store, "get_job", lambda job_id: jobs.get(job_id))
    return TestClient(app)


def test_returns_sha256_of_the_uploaded_pdf_and_caches_it(monkeypatch, tmp_path):
    pdf = b"%PDF-1.4 same bytes for two students"
    (tmp_path / "submission.pdf").write_bytes(pdf)
    client = _client(monkeypatch, {"job-1": SimpleNamespace(temp_dir=str(tmp_path))})

    response = client.get("/api/v1/ocr/file-hash/job-1")

    assert response.status_code == 200
    assert response.json() == {"job_id": "job-1", "sha256": hashlib.sha256(pdf).hexdigest()}
    assert (tmp_path / "submission.sha256").read_text() == hashlib.sha256(pdf).hexdigest()


def test_identical_files_get_identical_hashes_and_different_files_do_not(monkeypatch, tmp_path):
    dirs = {}
    for name, content in (("a", b"%PDF answer"), ("b", b"%PDF answer"), ("c", b"%PDF other answer")):
        d = tmp_path / name
        d.mkdir()
        (d / "submission.pdf").write_bytes(content)
        dirs[name] = SimpleNamespace(temp_dir=str(d))
    client = _client(monkeypatch, dirs)

    hashes = {name: client.get(f"/api/v1/ocr/file-hash/{name}").json()["sha256"] for name in dirs}

    assert hashes["a"] == hashes["b"] != hashes["c"]


def test_unknown_job_is_404_and_missing_file_is_null(monkeypatch, tmp_path):
    client = _client(monkeypatch, {"gone": SimpleNamespace(temp_dir=str(tmp_path))})

    assert client.get("/api/v1/ocr/file-hash/nope").status_code == 404
    assert client.get("/api/v1/ocr/file-hash/gone").json() == {"job_id": "gone", "sha256": None}
