"""Course-material RAG ingestion (backend side) and evidence pass-through in AI answer checks.

The AI Engine and OCR service are mocked; the AI Engine's own tests cover embeddings/retrieval.
"""

import json
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import course_materials
from app.api.v1.endpoints.courses import get_course_service
from app.core.dependencies import get_token_verifier
from app.schemas.ocr import OCRDocumentResult
from app.services.course_material_index_service import CourseMaterialIndexService
from app.services.course_material_service import extract_course_material_pages
from app.services.course_service import CourseNotFoundError
from app.services.user_service import get_profile_repository
from conftest import bearer
from test_course_materials import make_pdf, make_zip, slide_xml
from test_grading_service import AI_RESULT, TEACHER, _service, run

NOTES = "The Toranas are four ornamental gateways at the cardinal directions with sculpted panels."


# --------------------------------------------------------------------------
# Page-level extraction
# --------------------------------------------------------------------------


def test_pages_from_text_pdf_pptx_and_scan():
    txt = extract_course_material_pages("notes.txt", NOTES.encode())
    assert txt.pages == [{"page_number": 1, "text": NOTES}] and not txt.needs_ocr

    pdf = extract_course_material_pages("notes.pdf", make_pdf("Stupa notes about the hemispherical dome"))
    assert pdf.pages[0]["page_number"] == 1 and "hemispherical dome" in pdf.pages[0]["text"]

    pptx = extract_course_material_pages("deck.pptx", make_zip({
        "ppt/slides/slide1.xml": slide_xml(["Slide one about the stupa dome structure"]),
        "ppt/slides/slide2.xml": slide_xml(["Slide two about the Torana gateways"]),
    }))
    assert [p["page_number"] for p in pptx.pages] == [1, 2]
    assert "Torana" in pptx.pages[1]["text"]

    scan = extract_course_material_pages("scan.pdf", make_pdf(None))
    assert scan.needs_ocr and scan.pages == []


# --------------------------------------------------------------------------
# Upload / list / delete endpoints
# --------------------------------------------------------------------------


class FakeCourses:
    def __init__(self, owner_id: UUID):
        self.owner_id = owner_id

    def get_for(self, user, course_id, *, access_token):
        if user.id != self.owner_id:
            raise CourseNotFoundError
        return object()


class FakeOCR:
    def __init__(self):
        self.submitted = []

    async def submit_pdf(self, data, filename="submission.pdf", submission_id=None, run_async=True):
        self.submitted.append(filename)
        return type("Job", (), {"job_id": "job-1"})()

    async def poll_until_complete(self, job_id, poll_interval=None, timeout=None):
        return OCRDocumentResult.model_validate({
            "job_id": job_id, "submission_id": "s",
            "pages": [{"page_id": "p1", "page_number": 1, "width": 10, "height": 10,
                       "full_text": "Handwritten notes: the stupa has a harmika and a chatra on top."}],
        })


@pytest.fixture
def setup(verifier, profiles, make_token):
    owner = uuid4()
    profiles.add(owner, "teacher")
    other = uuid4()
    profiles.add(other, "teacher")
    student = uuid4()
    profiles.add(student, "student")

    calls: list[httpx.Request] = []
    state = {"status": 200, "body": {"material_id": "mat_1", "duplicate": False, "chunks_indexed": 2}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(state["status"], json=state["body"])

    ocr = FakeOCR()
    app = FastAPI()
    app.include_router(course_materials.router, prefix="/api/v1")
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    app.dependency_overrides[get_profile_repository] = lambda: profiles
    app.dependency_overrides[get_course_service] = lambda: FakeCourses(owner)
    app.dependency_overrides[course_materials.get_material_index_service] = lambda: CourseMaterialIndexService(
        ocr, ai_base_url="http://ai", transport=httpx.MockTransport(handler)
    )
    return {
        "client": TestClient(app),
        "owner": bearer(make_token(owner)),
        "other": bearer(make_token(other)),
        "student": bearer(make_token(student)),
        "calls": calls,
        "state": state,
        "ocr": ocr,
    }


def _url(course_id, suffix=""):
    return f"/api/v1/courses/{course_id}/materials{suffix}"


def test_owner_uploads_notes_and_pages_are_indexed(setup):
    course = uuid4()
    response = setup["client"].post(
        _url(course), files={"file": ("notes.txt", NOTES.encode(), "text/plain")}, headers=setup["owner"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["material_id"] == "mat_1" and body["extraction"] == "text_layer" and body["pages_indexed"] == 1

    sent = json.loads(setup["calls"][0].content)
    assert setup["calls"][0].url.path == "/v1/materials/index"
    assert sent == {"course_id": str(course), "filename": "notes.txt", "pages": [{"page_number": 1, "text": NOTES}]}


def test_other_teacher_and_student_are_rejected(setup):
    course = uuid4()
    files = {"file": ("notes.txt", NOTES.encode(), "text/plain")}
    assert setup["client"].post(_url(course), files=files, headers=setup["other"]).status_code == 404
    assert setup["client"].post(_url(course), files=files, headers=setup["student"]).status_code == 403
    assert setup["client"].get(_url(course), headers=setup["student"]).status_code == 403
    assert setup["calls"] == []  # AI Engine never contacted


def test_scanned_pdf_goes_through_ocr(setup):
    response = setup["client"].post(
        _url(uuid4()), files={"file": ("scan.pdf", make_pdf(None), "application/pdf")}, headers=setup["owner"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["extraction"] == "ocr"
    assert setup["ocr"].submitted == ["scan.pdf"]
    sent = json.loads(setup["calls"][0].content)
    assert "harmika" in sent["pages"][0]["text"]


def test_embeddings_unavailable_maps_to_503(setup):
    setup["state"].update(status=503, body={"detail": "Semantic embeddings unavailable"})
    response = setup["client"].post(
        _url(uuid4()), files={"file": ("notes.txt", NOTES.encode(), "text/plain")}, headers=setup["owner"]
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "rag_unavailable"


def test_unsupported_file_rejected_before_indexing(setup):
    response = setup["client"].post(
        _url(uuid4()), files={"file": ("virus.exe", b"MZ" * 20, "application/octet-stream")}, headers=setup["owner"]
    )
    assert response.status_code == 415
    assert setup["calls"] == []


def test_list_and_delete(setup):
    course = uuid4()
    setup["state"]["body"] = {"course_id": str(course), "materials": [{"material_id": "mat_1"}], "chunk_count": 2}
    listing = setup["client"].get(_url(course), headers=setup["owner"])
    assert listing.status_code == 200 and listing.json()["chunk_count"] == 2
    assert setup["calls"][-1].url.params["course_id"] == str(course)

    setup["state"].update(status=404, body={"detail": "Material not found"})
    missing = setup["client"].delete(_url(course, "/mat_x"), headers=setup["owner"])
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "material_not_found"


# --------------------------------------------------------------------------
# Evidence pass-through in the AI answer check
# --------------------------------------------------------------------------


def test_answer_check_returns_course_evidence():
    q1, q2 = AI_RESULT["question_results"]
    body = {
        **AI_RESULT,
        "rag": {"status": "partial", "course_id": "c1", "materials_indexed": 1, "embedding_model": "all-MiniLM-L6-v2"},
        "question_results": [
            {**q1, "evidence_status": "available", "evidence": [{
                "document_id": "mat_1", "title": "notes.pdf", "page_number": 2,
                "snippet": "Binary conversion by repeated division by 2.", "similarity_score": 0.71,
            }]},
            {**q2, "evidence_status": "unavailable",
             "evidence_unavailable_reason": "No passage in this course's materials was relevant enough."},
        ],
    }
    service, submission, _ = _service(ai_body=body)

    result = run(service.grade_submission(TEACHER, submission.id, access_token="t"))

    first, second = result.questions
    assert first.evidence_status == "available"
    assert first.evidence[0].filename == "notes.pdf" and first.evidence[0].page_number == 2
    assert first.evidence[0].similarity == 0.71 and "repeated division" in first.evidence[0].content
    assert second.evidence_status == "unavailable" and second.evidence == []
    assert "relevant enough" in second.evidence_unavailable_reason
    assert result.rag["status"] == "partial" and result.rag["embedding_model"] == "all-MiniLM-L6-v2"
