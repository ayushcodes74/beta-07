"""Integrity report: within-submission handwriting consistency (teacher-only review signal)."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.schemas.ocr import OCRDocumentResult
from app.schemas.user import Role
from app.services.auth_service import CurrentUser
from app.services.ocr_client import OCRServiceClient, OCRServiceUnavailableError
from app.services.submission_service import SubmissionRecord, SubmissionService

TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)

FLAGGED = {
    "version": "hw-consistency-1",
    "status": "possible_different_handwriting",
    "method": "within-submission style comparison (unvalidated heuristic)",
    "threshold": 0.9,
    "lines_analyzed": 40,
    "segments": [{"segment_id": "page-3", "kind": "page", "label": "Page 3", "page_numbers": [3],
                  "line_count": 12, "difference_score": 1.21, "p_value": 0.003, "flagged": True}],
    "flagged": [{
        "segment_id": "page-3", "kind": "page", "label": "Page 3", "page_numbers": [3],
        "difference_score": 1.21, "p_value": 0.003, "compared_with": "Page 1",
        "samples": [{"page_number": 3, "bounding_box": {"x1": 1, "y1": 2, "x2": 300, "y2": 40},
                     "text": "the stupa", "image": "data:image/png;base64,AAA"}],
        "reference_samples": [{"page_number": 1, "text": "relics", "image": "data:image/png;base64,BBB"}],
    }],
    "limitations": "Unvalidated heuristic ... not evidence of misconduct.",
}


class Repo:
    def __init__(self, record):
        self.record = record

    def get(self, submission_id, *, access_token):
        return self.record

    def list_by_assignment(self, assignment_id, *, access_token):
        return [self.record]


class Assignments:
    def require_owned(self, teacher, assignment_id, *, access_token):
        return None


class FakeOCR:
    def __init__(self, handwriting=None, error=None):
        self.handwriting = handwriting
        self.error = error

    async def get_job_result(self, job_id):
        return OCRDocumentResult.model_validate({"job_id": job_id, "submission_id": "s", "pages": []})

    async def get_handwriting_analysis(self, job_id):
        if self.error:
            raise self.error
        return self.handwriting


def _report(ocr):
    now = datetime.now(UTC).isoformat()
    record = SubmissionRecord(id=uuid4(), assignment_id=uuid4(), student_id=uuid4(), filename="a.pdf",
                              ocr_job_id="job-1", status="ocr_completed", created_at=now, updated_at=now)
    service = SubmissionService(Repo(record), Assignments(), ocr)
    return asyncio.run(service.analyze_submission_integrity(TEACHER, record.id, access_token="t"))


def test_flag_is_reported_for_teacher_review():
    report = _report(FakeOCR(handwriting=FLAGGED))
    hw = report.handwriting_analysis
    assert hw.status == "possible_different_handwriting" and hw.validated is False
    assert hw.flagged[0].label == "Page 3" and hw.flagged[0].samples[0].image.startswith("data:image/png")
    assert report.review_status == "needs_teacher_review"  # even with no text matches
    assert any("Possible different handwriting" in note for note in report.notes)


@pytest.mark.parametrize("status", ["consistent", "insufficient_handwriting"])
def test_no_flag_keeps_no_matches(status):
    report = _report(FakeOCR(handwriting={"status": status, "flagged": [], "segments": []}))
    assert report.handwriting_analysis.status == status
    assert report.review_status == "no_matches"


def test_ocr_failure_degrades_to_unavailable():
    report = _report(FakeOCR(error=OCRServiceUnavailableError("down")))
    assert report.handwriting_analysis.status == "unavailable"
    assert report.review_status == "no_matches"


def test_client_maps_statuses():
    def handler(request):
        job = request.url.path.rsplit("/", 1)[-1]
        return {"job-ok": httpx.Response(200, json=FLAGGED),
                "job-busy": httpx.Response(202, json={"detail": "processing"}),
                "job-gone": httpx.Response(404, json={"detail": "not found"})}[job]

    client = OCRServiceClient(client=httpx.AsyncClient(base_url="http://ocr", transport=httpx.MockTransport(handler)))
    assert asyncio.run(client.get_handwriting_analysis("job-ok"))["status"] == "possible_different_handwriting"
    assert asyncio.run(client.get_handwriting_analysis("job-busy"))["status"] == "processing"
    assert asyncio.run(client.get_handwriting_analysis("job-gone"))["status"] == "unavailable"
