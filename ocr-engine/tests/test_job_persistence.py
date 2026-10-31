"""Job persistence: OCR jobs survive a service restart.

Covers restoring finished jobs from job.json/result.json, re-running unfinished/legacy workspaces
from their saved submission.pdf, refusing unsafe job IDs, and shutdown keeping workspaces on disk.
"""

from pathlib import Path

import pytest

from app.api.config import APIConfig
from app.jobs.job_manager import JobManager
from app.jobs.job_store import JOB_META_FILENAME, JOB_RESULT_FILENAME, JobStore


@pytest.fixture
def storage(tmp_path: Path):
    JobManager.reset_instance()
    cfg = APIConfig(storage_root=str(tmp_path / "storage"))
    yield cfg
    JobManager.reset_instance()


def test_finished_job_is_restored_after_restart(storage: APIConfig, sample_single_page_pdf: Path):
    mgr = JobManager.get_instance(storage)
    job = mgr.submit_job(sample_single_page_pdf.read_bytes(), "a.pdf", submission_id="sub-persist", run_async=False)
    original = mgr.get_job_result(job.job_id)
    assert original is not None
    job_dir = Path(job.temp_dir)
    assert (job_dir / JOB_META_FILENAME).is_file()
    assert (job_dir / JOB_RESULT_FILENAME).is_file()

    JobManager.shutdown()  # simulated service stop: memory gone, files kept
    assert job_dir.is_dir()

    restarted = JobManager.get_instance(storage)
    status = restarted.get_job_status(job.job_id)
    assert status is not None
    assert status.status == original.status
    assert status.submission_id == "sub-persist"
    assert restarted.get_job_result(job.job_id) == original


def test_unfinished_legacy_workspace_is_rerun(storage: APIConfig, sample_single_page_pdf: Path, monkeypatch):
    """A workspace from before persistence (PDF + artifacts/<submission_id>/, no job.json) is re-run."""
    job_id = "job-" + "ab" * 16
    job_dir = Path(storage.storage_root) / job_id
    (job_dir / "artifacts" / "5ded445b-2efa-47c8-91ac-bc1cadbfe562").mkdir(parents=True)
    (job_dir / "submission.pdf").write_bytes(sample_single_page_pdf.read_bytes())

    mgr = JobManager.get_instance(storage)
    dispatched = []
    monkeypatch.setattr(mgr, "_dispatch", lambda job, run_async=True: dispatched.append((job.job_id, job.submission_id)))

    status = mgr.get_job_status(job_id)
    assert status is not None
    assert status.status == "queued"
    assert dispatched == [(job_id, "5ded445b-2efa-47c8-91ac-bc1cadbfe562")]

    # Second lookup uses the registered record; no duplicate run.
    mgr.get_job_result(job_id)
    assert len(dispatched) == 1
    assert (job_dir / JOB_META_FILENAME).is_file()


def test_rerun_actually_completes(storage: APIConfig, sample_single_page_pdf: Path):
    job_id = "job-" + "cd" * 16
    job_dir = Path(storage.storage_root) / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "submission.pdf").write_bytes(sample_single_page_pdf.read_bytes())

    mgr = JobManager.get_instance(storage)
    record = mgr._get_or_recover(job_id)
    assert record is not None and record._future is not None
    record._future.result(timeout=300)

    status = mgr.get_job_status(job_id)
    assert status.status not in ("queued", "processing", "failed")
    assert mgr.get_job_result(job_id) is not None
    assert (job_dir / JOB_RESULT_FILENAME).is_file()


@pytest.mark.parametrize("bad_id", ["../etc", "job-../../x", "job-XYZ", "", "job-" + "a" * 31])
def test_unsafe_or_unknown_job_ids_are_not_found(storage: APIConfig, bad_id: str):
    mgr = JobManager.get_instance(storage)
    assert mgr.get_job_status(bad_id) is None
    assert mgr.get_job_status("job-" + "0" * 32) is None  # well-formed but no workspace


def test_reset_instance_still_cleans_workspaces(storage: APIConfig, sample_single_page_pdf: Path):
    mgr = JobManager.get_instance(storage)
    job = mgr.submit_job(sample_single_page_pdf.read_bytes(), "a.pdf", run_async=False)
    job_dir = Path(job.temp_dir)
    JobManager.reset_instance()
    assert not job_dir.exists()
    assert JobStore.get_instance().get_job(job.job_id) is None
