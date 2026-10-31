"""Unit and integration tests for Module 5 OCR backend integration.

MOCK NOTICE:
These tests use mocked HTTP transports for the OCR service microservice.
They verify API routing, serialization, timeout handling, HTTP error mappings,
student data isolation, and teacher authorization. They do NOT test real
deep-learning OCR model inference on actual GPUs/CPUs.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import assignments, submissions
from app.core.dependencies import get_token_verifier
from app.schemas.assignment import AssignmentContent, AssignmentStatus
from app.schemas.ocr import OCRDocumentResult
from app.schemas.user import Role
from app.services.assignment_service import (
    AssignmentRecord,
    AssignmentService,
    get_assignment_repository,
)
from app.services.ocr_client import OCRServiceClient, get_ocr_client
from app.services.submission_service import (
    SubmissionRecord,
    SubmissionService,
    get_submission_repository,
)
from app.services.user_service import get_profile_repository
from conftest import bearer

VALID_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


class FakeAssignmentRepository:
    """In-memory test double for assignments."""

    def __init__(self) -> None:
        self.records: dict[UUID, AssignmentRecord] = {}

    def add(self, teacher_id: UUID, status: AssignmentStatus = AssignmentStatus.PUBLISHED) -> AssignmentRecord:
        aid = uuid4()
        content = AssignmentContent(
            title="Math & Physics Exam",
            instructions="Solve the equations.",
            due_at=datetime.now(UTC) + timedelta(days=7),
            total_marks=10,
            questions=[],
        )
        rec = AssignmentRecord(id=aid, teacher_id=teacher_id, status=status, content=content)
        self.records[aid] = rec
        return rec

    def get(self, assignment_id: UUID, *, access_token: str) -> AssignmentRecord | None:
        return self.records.get(assignment_id)

    def owns_course(self, course_id: UUID, teacher_id: UUID, *, access_token: str) -> bool:
        return True

    def get_published_for_student(
        self, assignment_id: UUID, student_id: UUID, *, access_token: str
    ) -> AssignmentRecord | None:
        rec = self.records.get(assignment_id)
        if rec and rec.status == AssignmentStatus.PUBLISHED:
            return rec
        return None

    def list_by_teacher(self, teacher_id: UUID, *, access_token: str) -> list[AssignmentRecord]:
        return [record for record in self.records.values() if record.teacher_id == teacher_id]


class FakeSubmissionRepository:
    """In-memory test double for submissions."""

    def __init__(self) -> None:
        self.records: dict[UUID, SubmissionRecord] = {}

    def create(
        self,
        submission_id: UUID,
        assignment_id: UUID,
        student_id: UUID,
        filename: str,
        ocr_job_id: str | None,
        status: str,
        *,
        access_token: str,
    ) -> SubmissionRecord:
        now_str = datetime.now(UTC).isoformat()
        rec = SubmissionRecord(
            id=submission_id,
            assignment_id=assignment_id,
            student_id=student_id,
            filename=filename,
            ocr_job_id=ocr_job_id,
            status=status,
            created_at=now_str,
            updated_at=now_str,
        )
        self.records[submission_id] = rec
        return rec

    def get(self, submission_id: UUID, *, access_token: str) -> SubmissionRecord | None:
        return self.records.get(submission_id)

    def list_by_assignment(self, assignment_id: UUID, *, access_token: str) -> list[SubmissionRecord]:
        return [r for r in self.records.values() if r.assignment_id == assignment_id]

    def list_by_student(self, student_id: UUID, *, access_token: str) -> list[SubmissionRecord]:
        return [r for r in self.records.values() if r.student_id == student_id]

    def update_status(
        self,
        submission_id: UUID,
        status: str,
        ocr_job_id: str | None = None,
        *,
        access_token: str,
    ) -> SubmissionRecord | None:
        rec = self.records.get(submission_id)
        if not rec:
            return None
        now_str = datetime.now(UTC).isoformat()
        updated = rec.model_copy(
            update={
                "status": status,
                "ocr_job_id": ocr_job_id if ocr_job_id is not None else rec.ocr_job_id,
                "updated_at": now_str,
            }
        )
        self.records[submission_id] = updated
        return updated


@pytest.fixture
def assignment_repo() -> FakeAssignmentRepository:
    return FakeAssignmentRepository()


@pytest.fixture
def submission_repo() -> FakeSubmissionRepository:
    return FakeSubmissionRepository()


@pytest.fixture
def sample_ocr_result_dict() -> dict[str, Any]:
    return {
        "job_id": "job-12345",
        "submission_id": "sub-12345",
        "status": "completed",
        "document_metadata": {
            "title": "Student Answer Sheet",
            "author": "Student",
            "creation_date": "2026-10-31T00:00:00Z",
            "page_count": 1,
        },
        "processing_summary": {
            "total_pages": 1,
            "processed_pages": 1,
            "failed_pages": 0,
            "total_processing_time_ms": 150.0,
            "stage_durations_ms": {"ingestion": 20.0, "recognition": 130.0},
        },
        "pages": [
            {
                "page_id": "page-1",
                "page_number": 1,
                "status": "completed",
                "width": 612,
                "height": 792,
                "text_blocks": [
                    {
                        "block_id": "b-1",
                        "sequence": 1,
                        "type": "printed",
                        "text": "Question 1. Solve for x.",
                        "confidence": 0.98,
                        "quality_score": 0.95,
                        "bounding_box": {"x1": 50, "y1": 100, "x2": 400, "y2": 120},
                    }
                ],
                "math_blocks": [
                    {
                        "region_id": "m-1",
                        "bounding_box": {"x1": 50, "y1": 140, "x2": 250, "y2": 170},
                        "recognized_text": "x^2 - 4 = 0",
                        "latex": "x^2 - 4 = 0",
                        "confidence": 0.96,
                        "quality_score": 0.92,
                        "is_readable": True,
                        "is_complete": True,
                        "requires_manual_review": False,
                    }
                ],
                "full_text": "Question 1. Solve for x.",
                "combined_latex": "x^2 - 4 = 0",
                "warnings": [],
                "metadata": {},
            }
        ],
        "warnings": [],
        "errors": [],
    }


def create_mock_transport_client(handler) -> OCRServiceClient:
    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient(base_url="http://127.0.0.1:8001", transport=transport)
    return OCRServiceClient(client=async_client)


@pytest.fixture
def make_user(make_token, profiles):
    def _make(role: str) -> tuple[UUID, dict[str, str]]:
        uid = uuid4()
        profiles.add(uid, role)
        return uid, bearer(make_token(uid))

    return _make


@pytest.fixture
def setup_app(verifier, profiles, assignment_repo, submission_repo):
    def _build_app(custom_ocr_client: OCRServiceClient | None = None) -> TestClient:
        test_app = FastAPI()
        test_app.include_router(assignments.router, prefix="/api/v1")
        test_app.include_router(submissions.router, prefix="/api/v1")

        test_app.dependency_overrides[get_token_verifier] = lambda: verifier
        test_app.dependency_overrides[get_profile_repository] = lambda: profiles
        test_app.dependency_overrides[get_assignment_repository] = lambda: assignment_repo
        test_app.dependency_overrides[get_submission_repository] = lambda: submission_repo

        if custom_ocr_client:
            test_app.dependency_overrides[get_ocr_client] = lambda: custom_ocr_client

        return TestClient(test_app)

    return _build_app


# --------------------------------------------------------------------------
# 1. Successful Upload & Submission
# --------------------------------------------------------------------------
def test_successful_pdf_submission_and_ocr_dispatch(setup_app, assignment_repo, make_user):
    teacher_id, _ = make_user("teacher")
    student_id, student_auth = make_user("student")
    assign = assignment_repo.add(teacher_id)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/ocr/process":
            return httpx.Response(
                202,
                json={
                    "job_id": "ocr-job-999",
                    "submission_id": "sub-test",
                    "status": "queued",
                    "created_at": "2026-10-31T05:00:00Z",
                    "message": "Queued",
                },
            )
        if "/status/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "job_id": "ocr-job-999",
                    "submission_id": "sub-test",
                    "status": "queued",
                    "stage": "queued",
                    "progress": 0,
                    "created_at": "2026-10-31T05:00:00Z",
                    "updated_at": "2026-10-31T05:00:00Z",
                    "warnings": [],
                },
            )
        return httpx.Response(404)

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    resp = client.post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("answers.pdf", VALID_PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ocr_queued"
    assert body["ocr_job_id"] == "ocr-job-999"
    assert body["student_id"] == str(student_id)
    assert body["assignment_id"] == str(assign.id)


# --------------------------------------------------------------------------
# 2. Status Polling & Dynamic Status Update
# --------------------------------------------------------------------------
def test_successful_status_polling(setup_app, submission_repo, make_user):
    student_id, student_auth = make_user("student")
    sub_rec = submission_repo.create(
        submission_id=uuid4(),
        assignment_id=uuid4(),
        student_id=student_id,
        filename="test.pdf",
        ocr_job_id="job-active-123",
        status="ocr_queued",
        access_token="fake-token",
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/ocr/status/job-active-123"
        return httpx.Response(
            200,
            json={
                "job_id": "job-active-123",
                "submission_id": str(sub_rec.id),
                "status": "processing",
                "stage": "recognition",
                "progress": 55,
                "created_at": "2026-10-31T05:00:00Z",
                "updated_at": "2026-10-31T05:00:02Z",
                "warnings": ["Low contrast on page 1"],
            },
        )

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    resp = client.get(f"/api/v1/submissions/{sub_rec.id}/status", headers=student_auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ocr_processing"
    assert body["ocr_stage"] == "recognition"
    assert body["ocr_progress"] == 55
    assert "Low contrast on page 1" in body["warnings"]


# --------------------------------------------------------------------------
# 3. Successful Result Retrieval
# --------------------------------------------------------------------------
def test_successful_ocr_result_retrieval(setup_app, submission_repo, make_user, sample_ocr_result_dict):
    student_id, student_auth = make_user("student")
    sub_rec = submission_repo.create(
        submission_id=uuid4(),
        assignment_id=uuid4(),
        student_id=student_id,
        filename="test.pdf",
        ocr_job_id="job-done-123",
        status="ocr_completed",
        access_token="fake-token",
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/ocr/result/job-done-123"
        return httpx.Response(200, json=sample_ocr_result_dict)

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    resp = client.get(f"/api/v1/submissions/{sub_rec.id}/ocr-result", headers=student_auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == "job-12345"
    assert data["pages"][0]["text_blocks"][0]["confidence"] == 0.98
    assert data["pages"][0]["math_blocks"][0]["latex"] == "x^2 - 4 = 0"


# --------------------------------------------------------------------------
# 4. Result Retrieval Returning 202 While Still Processing
# --------------------------------------------------------------------------
def test_result_retrieval_202_processing(setup_app, submission_repo, make_user):
    student_id, student_auth = make_user("student")
    sub_rec = submission_repo.create(
        submission_id=uuid4(),
        assignment_id=uuid4(),
        student_id=student_id,
        filename="test.pdf",
        ocr_job_id="job-processing-123",
        status="ocr_processing",
        access_token="fake-token",
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/ocr/result/job-processing-123"
        return httpx.Response(
            202,
            json={
                "job_id": "job-processing-123",
                "status": "processing",
                "stage": "math_recognition",
                "progress": 75,
                "message": "Job is currently in stage 'math_recognition' (75%). Retry shortly.",
            },
        )

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    resp = client.get(f"/api/v1/submissions/{sub_rec.id}/ocr-result", headers=student_auth)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "processing"
    assert data["stage"] == "math_recognition"
    assert data["progress"] == 75


# --------------------------------------------------------------------------
# 5. Failed and Cancelled OCR Jobs
# --------------------------------------------------------------------------
def test_failed_ocr_job_result_mapping(setup_app, submission_repo, make_user):
    student_id, student_auth = make_user("student")
    sub_rec = submission_repo.create(
        submission_id=uuid4(),
        assignment_id=uuid4(),
        student_id=student_id,
        filename="test.pdf",
        ocr_job_id="job-failed-123",
        status="ocr_failed",
        access_token="fake-token",
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/ocr/result/job-failed-123"
        return httpx.Response(
            400,
            json={
                "detail": {
                    "job_id": "job-failed-123",
                    "status": "failed",
                    "error": "Corrupted PDF cross-reference table",
                    "warnings": [],
                }
            },
        )

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    resp = client.get(f"/api/v1/submissions/{sub_rec.id}/ocr-result", headers=student_auth)
    assert resp.status_code == 400
    assert "Corrupted PDF" in str(resp.json())


def test_cancelled_ocr_job_endpoint(setup_app, submission_repo, make_user):
    student_id, student_auth = make_user("student")
    sub_rec = submission_repo.create(
        submission_id=uuid4(),
        assignment_id=uuid4(),
        student_id=student_id,
        filename="test.pdf",
        ocr_job_id="job-cancel-123",
        status="ocr_queued",
        access_token="fake-token",
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/ocr/jobs/job-cancel-123"
        assert request.method == "DELETE"
        return httpx.Response(
            200,
            json={"job_id": "job-cancel-123", "status": "cancelled", "message": "Cleaned up"},
        )

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    resp = client.delete(f"/api/v1/submissions/{sub_rec.id}/ocr-job", headers=student_auth)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    # Verify repository updated
    updated_rec = submission_repo.get(sub_rec.id, access_token="test")
    assert updated_rec.status == "ocr_cancelled"


# --------------------------------------------------------------------------
# 6. Service Unavailable & Timeout Mappings
# --------------------------------------------------------------------------
def test_ocr_service_unavailable(setup_app, assignment_repo, make_user):
    teacher_id, _ = make_user("teacher")
    student_id, student_auth = make_user("student")
    assign = assignment_repo.add(teacher_id)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused on 127.0.0.1:8001")

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    resp = client.post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("answers.pdf", VALID_PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "service_unavailable"


def test_ocr_timeout_mapping(setup_app, assignment_repo, make_user):
    teacher_id, _ = make_user("teacher")
    student_id, student_auth = make_user("student")
    assign = assignment_repo.add(teacher_id)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timeout waiting for OCR Engine response")

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    resp = client.post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("answers.pdf", VALID_PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 504
    assert resp.json()["detail"]["code"] == "ocr_timeout"


# --------------------------------------------------------------------------
# 7. PDF Validation Guards
# --------------------------------------------------------------------------
def test_invalid_pdf_rejected_before_forwarding(setup_app, assignment_repo, make_user):
    teacher_id, _ = make_user("teacher")
    student_id, student_auth = make_user("student")
    assign = assignment_repo.add(teacher_id)

    client = setup_app()

    # Case A: Non-PDF extension
    resp1 = client.post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("answers.txt", b"%PDF-1.4 valid header", "text/plain")},
    )
    assert resp1.status_code == 422
    assert "PDF document" in str(resp1.json())

    # Case B: Invalid magic bytes
    resp2 = client.post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("answers.pdf", b"NOT_A_PDF_STREAM", "application/pdf")},
    )
    assert resp2.status_code == 422
    assert "magic bytes" in str(resp2.json())

    # Case C: File too small / empty
    resp3 = client.post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("answers.pdf", b"", "application/pdf")},
    )
    assert resp3.status_code == 422
    assert "empty or truncated" in str(resp3.json())

    # Case D: File exceeding 20 MB limit
    huge_pdf = b"%PDF-1.4" + (b"0" * (20 * 1024 * 1024 + 10))
    resp4 = client.post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("huge.pdf", huge_pdf, "application/pdf")},
    )
    assert resp4.status_code == 422
    assert "exceeds maximum allowed limit" in str(resp4.json())


# --------------------------------------------------------------------------
# 8. Unconfigured Submission Repository Returns 503
# --------------------------------------------------------------------------
def test_unconfigured_submission_repository_returns_503(
    verifier, profiles, assignment_repo, make_user
):
    teacher_id, _ = make_user("teacher")
    student_id, student_auth = make_user("student")
    assign = assignment_repo.add(teacher_id)

    test_app = FastAPI()
    test_app.include_router(submissions.router, prefix="/api/v1")
    test_app.dependency_overrides[get_token_verifier] = lambda: verifier
    test_app.dependency_overrides[get_profile_repository] = lambda: profiles
    test_app.dependency_overrides[get_assignment_repository] = lambda: assignment_repo
    # DO NOT override get_submission_repository: uses UnconfiguredSubmissionRepository

    client = TestClient(test_app)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"job_id": "job-1", "status": "queued", "created_at": ""})

    test_app.dependency_overrides[get_ocr_client] = lambda: create_mock_transport_client(mock_handler)

    resp = client.post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("answers.pdf", VALID_PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "service_unavailable"


# --------------------------------------------------------------------------
# 9. Student Data Isolation (Cross-Student Access Prevention)
# --------------------------------------------------------------------------
def test_student_cannot_access_another_students_submission(setup_app, submission_repo, make_user):
    student_a, _ = make_user("student")
    student_b, student_b_auth = make_user("student")

    sub_rec = submission_repo.create(
        submission_id=uuid4(),
        assignment_id=uuid4(),
        student_id=student_a,
        filename="test.pdf",
        ocr_job_id="job-1",
        status="ocr_completed",
        access_token="fake",
    )

    client = setup_app()

    # Student B queries status of Student A's submission -> 404 (privacy convention)
    resp_status = client.get(f"/api/v1/submissions/{sub_rec.id}/status", headers=student_b_auth)
    assert resp_status.status_code == 404

    # Student B queries result of Student A's submission -> 404
    resp_result = client.get(f"/api/v1/submissions/{sub_rec.id}/ocr-result", headers=student_b_auth)
    assert resp_result.status_code == 404


# --------------------------------------------------------------------------
# 10. Teacher Course-Level Ownership Authorization
# --------------------------------------------------------------------------
def test_teacher_course_level_authorization(
    setup_app, assignment_repo, submission_repo, make_user, sample_ocr_result_dict
):
    teacher_owner, teacher_owner_auth = make_user("teacher")
    teacher_other, teacher_other_auth = make_user("teacher")
    student_id, _ = make_user("student")

    assign = assignment_repo.add(teacher_owner)

    sub_rec = submission_repo.create(
        submission_id=uuid4(),
        assignment_id=assign.id,
        student_id=student_id,
        filename="test.pdf",
        ocr_job_id="job-teach-123",
        status="ocr_completed",
        access_token="fake",
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if "/status/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "job_id": "job-teach-123",
                    "submission_id": str(sub_rec.id),
                    "status": "completed",
                    "stage": "done",
                    "progress": 100,
                    "created_at": "2026-10-31T05:00:00Z",
                    "updated_at": "2026-10-31T05:00:02Z",
                    "warnings": [],
                },
            )
        return httpx.Response(200, json=sample_ocr_result_dict)

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    # 1. Owning teacher CAN access submission status and OCR result
    resp_owner_status = client.get(f"/api/v1/submissions/{sub_rec.id}/status", headers=teacher_owner_auth)
    assert resp_owner_status.status_code == 200

    resp_owner_result = client.get(f"/api/v1/submissions/{sub_rec.id}/ocr-result", headers=teacher_owner_auth)
    assert resp_owner_result.status_code == 200

    # 2. Other teacher (does NOT own assignment) CANNOT access submission status or OCR result -> 404
    resp_other_status = client.get(f"/api/v1/submissions/{sub_rec.id}/status", headers=teacher_other_auth)
    assert resp_other_status.status_code == 404

    resp_other_result = client.get(f"/api/v1/submissions/{sub_rec.id}/ocr-result", headers=teacher_other_auth)
    assert resp_other_result.status_code == 404


def test_integrity_comparison_is_teacher_only_and_scoped_to_same_assignment(
    setup_app, assignment_repo, submission_repo, make_user, sample_ocr_result_dict
):
    teacher_id, teacher_auth = make_user("teacher")
    other_teacher_id, other_teacher_auth = make_user("teacher")
    student_id, student_auth = make_user("student")
    assignment = assignment_repo.add(teacher_id)
    other_assignment = assignment_repo.add(other_teacher_id)

    current = submission_repo.create(
        uuid4(), assignment.id, student_id, "current.pdf", "current-job", "ocr_completed", access_token="test"
    )
    source = submission_repo.create(
        uuid4(), assignment.id, uuid4(), "source.pdf", "source-job", "ocr_completed", access_token="test"
    )
    unrelated = submission_repo.create(
        uuid4(), other_assignment.id, uuid4(), "unrelated.pdf", "unrelated-job", "ocr_completed", access_token="test"
    )
    current_text = (
        "Cells convert glucose into usable energy through cellular respiration "
        "within the mitochondria of the cell."
    )
    source_text = (
        "Cells convert glucose into usable energy through cellular respiration "
        "inside the mitochondria of the cell."
    )
    requested_jobs: list[str] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        job_id = request.url.path.rsplit("/", 1)[-1]
        if "/handwriting/" in request.url.path:
            # Within-submission handwriting check (only for the submission under review).
            assert job_id == "current-job"
            return httpx.Response(404, json={"detail": "not found"})
        requested_jobs.append(job_id)
        payload = deepcopy(sample_ocr_result_dict)
        payload["job_id"] = job_id
        text = current_text if job_id == "current-job" else source_text
        payload["pages"][0]["text_blocks"][0]["text"] = text
        payload["pages"][0]["text_blocks"][0]["confidence"] = 0.96
        payload["pages"][0]["text_blocks"][0]["type"] = "handwritten"
        payload["pages"][0]["full_text"] = text
        return httpx.Response(200, json=payload)

    client = setup_app(create_mock_transport_client(mock_handler))

    student_response = client.get(
        f"/api/v1/submissions/{current.id}/integrity",
        headers=student_auth,
    )
    other_teacher_response = client.get(
        f"/api/v1/submissions/{current.id}/integrity",
        headers=other_teacher_auth,
    )
    owner_response = client.get(
        f"/api/v1/submissions/{current.id}/integrity",
        headers=teacher_auth,
    )

    assert student_response.status_code == 403
    assert other_teacher_response.status_code == 404
    assert owner_response.status_code == 200
    report = owner_response.json()
    assert report["review_status"] == "needs_teacher_review"
    assert report["comparison_scope"] == "same_assignment"
    assert report["comparisons_completed"] == 1
    assert report["comparison_complete"] is True
    assert report["handwriting_analysis"]["status"] == "unavailable"
    assert report["handwriting_analysis"]["calibrated_score"] is None
    assert report["evidence"][0]["source_submission_id"] == str(source.id)
    assert report["evidence"][0]["ocr_uncertain"] is False
    assert "not a finding of misconduct" in " ".join(report["notes"])
    assert unrelated.id != source.id
    assert "unrelated-job" not in requested_jobs
    assert requested_jobs == ["current-job", "source-job"]


def test_integrity_analysis_reports_pending_ocr_without_comparing_sources(
    setup_app, assignment_repo, submission_repo, make_user
):
    teacher_id, teacher_auth = make_user("teacher")
    student_id, _ = make_user("student")
    assignment = assignment_repo.add(teacher_id)
    current = submission_repo.create(
        uuid4(), assignment.id, student_id, "current.pdf", "pending-job", "ocr_processing", access_token="test"
    )
    requested_jobs: list[str] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        requested_jobs.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(
            202,
            json={"job_id": "pending-job", "status": "processing", "stage": "recognition", "progress": 55},
        )

    client = setup_app(create_mock_transport_client(mock_handler))
    response = client.get(f"/api/v1/submissions/{current.id}/integrity", headers=teacher_auth)

    assert response.status_code == 200
    assert response.json()["review_status"] == "processing"
    assert response.json()["evidence"] == []
    assert requested_jobs == ["pending-job"]


def test_submission_listing_is_scoped_for_students_and_assignment_owners(
    setup_app, assignment_repo, submission_repo, make_user
):
    teacher_id, teacher_auth = make_user("teacher")
    other_teacher_id, _ = make_user("teacher")
    student_a, student_a_auth = make_user("student")
    student_b, student_b_auth = make_user("student")
    owned_assignment = assignment_repo.add(teacher_id)
    other_assignment = assignment_repo.add(other_teacher_id)

    own = submission_repo.create(
        uuid4(), owned_assignment.id, student_a, "own.pdf", "own-job", "ocr_queued", access_token="test"
    )
    peer = submission_repo.create(
        uuid4(), owned_assignment.id, student_b, "peer.pdf", "peer-job", "ocr_queued", access_token="test"
    )
    unrelated = submission_repo.create(
        uuid4(), other_assignment.id, student_a, "other.pdf", "other-job", "ocr_queued", access_token="test"
    )
    client = setup_app()

    teacher_response = client.get("/api/v1/submissions", headers=teacher_auth)
    student_a_response = client.get("/api/v1/submissions", headers=student_a_auth)
    student_b_response = client.get("/api/v1/submissions", headers=student_b_auth)

    assert teacher_response.status_code == 200
    assert {item["submission_id"] for item in teacher_response.json()} == {str(own.id), str(peer.id)}
    assert {item["submission_id"] for item in student_a_response.json()} == {str(own.id), str(unrelated.id)}
    assert {item["submission_id"] for item in student_b_response.json()} == {str(peer.id)}


# --------------------------------------------------------------------------
# 11. Role Restrictions (Teachers Cannot Submit Assignments)
# --------------------------------------------------------------------------
def test_teacher_cannot_submit_assignment(setup_app, assignment_repo, make_user):
    teacher_id, teacher_auth = make_user("teacher")
    assign = assignment_repo.add(teacher_id)

    client = setup_app()

    resp = client.post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=teacher_auth,
        files={"file": ("answers.pdf", VALID_PDF_BYTES, "application/pdf")},
    )
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# 12. Honest Technical Diagnostics (No Fake OCR Output)
# --------------------------------------------------------------------------
def test_no_fabricated_ocr_output_on_degraded_model(setup_app, submission_repo, make_user):
    student_id, student_auth = make_user("student")
    sub_rec = submission_repo.create(
        submission_id=uuid4(),
        assignment_id=uuid4(),
        student_id=student_id,
        filename="test.pdf",
        ocr_job_id="job-degraded-123",
        status="ocr_degraded",
        access_token="fake-token",
    )

    degraded_ocr_dict = {
        "job_id": "job-degraded-123",
        "submission_id": str(sub_rec.id),
        "status": "degraded",
        "document_metadata": {"title": None, "page_count": 1},
        "processing_summary": {
            "total_pages": 1,
            "processed_pages": 1,
            "failed_pages": 0,
            "total_processing_time_ms": 80.0,
            "stage_durations_ms": {},
        },
        "pages": [
            {
                "page_id": "page-1",
                "page_number": 1,
                "status": "degraded",
                "width": 612,
                "height": 792,
                "text_blocks": [
                    {
                        "block_id": "b-1",
                        "sequence": 1,
                        "type": "handwritten",
                        "text": "[UNCERTAIN: Handwriting model unavailable]",
                        "confidence": 0.0,
                        "quality_score": 0.50,
                        "bounding_box": {"x1": 50, "y1": 100, "x2": 400, "y2": 120},
                        "warnings": ["Handwriting model unavailable; bounding box detected."],
                    }
                ],
                "math_blocks": [],
                "full_text": "[UNCERTAIN: Handwriting model unavailable]",
                "combined_latex": "",
                "warnings": ["Mathematical recognition model unavailable."],
                "metadata": {},
            }
        ],
        "warnings": ["Handwriting model unavailable.", "Mathematical recognition model unavailable."],
        "errors": [],
    }

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=degraded_ocr_dict)

    ocr_client = create_mock_transport_client(mock_handler)
    client = setup_app(ocr_client)

    resp = client.get(f"/api/v1/submissions/{sub_rec.id}/ocr-result", headers=student_auth)
    assert resp.status_code == 200
    data = resp.json()

    # Verifications: Zero fake answers, honest 0.0 confidence, degraded status preserved
    assert data["status"] == "degraded"
    tb = data["pages"][0]["text_blocks"][0]
    assert tb["confidence"] == 0.0
    assert tb["text"] == "[UNCERTAIN: Handwriting model unavailable]"
    assert "Handwriting model unavailable" in data["warnings"][0]


# --------------------------------------------------------------------------
# Replacing a submission
# --------------------------------------------------------------------------
def _existing_submission(submission_repo, student_id, assignment_id, status, ocr_job_id="old-job"):
    now = datetime.now(UTC).isoformat()
    rec = SubmissionRecord(
        id=uuid4(), assignment_id=assignment_id, student_id=student_id, filename="old.pdf",
        ocr_job_id=ocr_job_id, status=status, created_at=now, updated_at=now,
    )
    submission_repo.records[rec.id] = rec
    return rec


def _recording_ocr(calls, *, cancel_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/v1/ocr/process":
            return httpx.Response(202, json={"job_id": "new-job", "submission_id": "s", "status": "queued",
                                             "created_at": "2026-10-31T05:00:00Z", "message": "Queued"})
        if request.method == "DELETE":
            return httpx.Response(cancel_status, json={"status": "cancelled"})
        return httpx.Response(404)
    return create_mock_transport_client(handler)


def test_replacing_submission_cancels_previous_ocr_job(setup_app, assignment_repo, submission_repo, make_user):
    teacher_id, _ = make_user("teacher")
    student_id, student_auth = make_user("student")
    assign = assignment_repo.add(teacher_id)
    _existing_submission(submission_repo, student_id, assign.id, "ocr_processing")
    calls: list[tuple[str, str]] = []

    resp = setup_app(_recording_ocr(calls)).post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("new.pdf", VALID_PDF_BYTES, "application/pdf")},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["ocr_job_id"] == "new-job"
    assert ("DELETE", "/api/v1/ocr/jobs/old-job") in calls


@pytest.mark.parametrize("status", ["under_review", "graded", "published"])
def test_submission_under_review_is_refused_before_any_ocr_work(
    setup_app, assignment_repo, submission_repo, make_user, status
):
    teacher_id, _ = make_user("teacher")
    student_id, student_auth = make_user("student")
    assign = assignment_repo.add(teacher_id)
    _existing_submission(submission_repo, student_id, assign.id, status)
    calls: list[tuple[str, str]] = []

    resp = setup_app(_recording_ocr(calls)).post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("new.pdf", VALID_PDF_BYTES, "application/pdf")},
    )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "already_submitted"
    assert calls == []  # the PDF was never sent to the OCR engine


def test_failed_cancel_of_old_job_does_not_fail_the_upload(setup_app, assignment_repo, submission_repo, make_user):
    teacher_id, _ = make_user("teacher")
    student_id, student_auth = make_user("student")
    assign = assignment_repo.add(teacher_id)
    _existing_submission(submission_repo, student_id, assign.id, "ocr_queued")
    calls: list[tuple[str, str]] = []

    resp = setup_app(_recording_ocr(calls, cancel_status=500)).post(
        f"/api/v1/assignments/{assign.id}/submissions",
        headers=student_auth,
        files={"file": ("new.pdf", VALID_PDF_BYTES, "application/pdf")},
    )

    assert resp.status_code == 201
    assert ("DELETE", "/api/v1/ocr/jobs/old-job") in calls


# --------------------------------------------------------------------------
# Database calls must not block the event loop
# --------------------------------------------------------------------------
@pytest.mark.anyio
async def test_slow_database_calls_do_not_serialize_concurrent_requests():
    """Repository calls are synchronous (Supabase over HTTPS). Run on the event loop, two
    concurrent requests would take the sum of their DB time; offloaded, they overlap."""
    import asyncio
    import time

    from app.services.auth_service import CurrentUser
    from app.services.submission_service import SubmissionService

    student = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)
    now = datetime.now(UTC).isoformat()
    record = SubmissionRecord(id=uuid4(), assignment_id=uuid4(), student_id=student.id, filename="a.pdf",
                              ocr_job_id="job-1", status="ocr_processing", created_at=now, updated_at=now)

    class SlowRepo:
        def get(self, submission_id, *, access_token):
            time.sleep(0.3)  # one blocking round trip to the database
            return record

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"job_id": "job-1", "submission_id": "s", "status": "processing",
                                         "stage": "recognition", "progress": 50,
                                         "created_at": now, "updated_at": now, "warnings": []})

    service = SubmissionService(SlowRepo(), assignment_service=None, ocr_client=create_mock_transport_client(handler))

    started = time.perf_counter()
    await asyncio.gather(*(service.get_submission_ocr_result(student, record.id, access_token="t") for _ in range(2)))
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5, f"requests ran one after another ({elapsed:.2f}s): DB calls are blocking the event loop"
