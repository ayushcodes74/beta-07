"""Course material attached while creating an assignment: text extraction + generation grounding."""

import io
import json
import zipfile
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import ai_generation
from app.core.dependencies import get_token_verifier
from app.schemas.ai_generation import AssignmentGenerationRequest
from app.services.ai_generation_service import AIGenerationService, get_ai_generation_service
from app.services.course_material_service import (
    MAX_MATERIAL_CHARS,
    MaterialExtractionError,
    extract_course_material,
)
from app.services.user_service import get_profile_repository
from conftest import bearer

EXTRACT_URL = "/api/v1/assignments/materials/extract"
GENERATE_URL = "/api/v1/assignments/generate-ai"
NOTES = "Newton's first law: an object stays at rest or in uniform motion unless acted on by a net force."


# --------------------------------------------------------------------------
# Test document builders
# --------------------------------------------------------------------------


def make_pdf(text: str | None) -> bytes:
    """Minimal single-page PDF; ``text=None`` produces a page with no text layer (like a scan)."""
    content = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode() if text else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def make_zip(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return buffer.getvalue()


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


def make_docx(paragraphs: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    return make_zip({"word/document.xml": f"<w:document {W}><w:body>{body}</w:body></w:document>"})


def slide_xml(lines: list[str]) -> str:
    paras = "".join(f"<a:p><a:r><a:t>{line}</a:t></a:r></a:p>" for line in lines)
    return f"<p:sld {A} xmlns:p='p'><p:txBody>{paras}</p:txBody></p:sld>"


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def test_extracts_pdf_text_layer():
    # Plain ASCII: a Type1 font's StandardEncoding maps "'" to a curly quote.
    result = extract_course_material("lecture.pdf", make_pdf("First law of motion: inertia keeps objects moving."))
    assert result.text == "First law of motion: inertia keeps objects moving."
    assert result.pages == 1 and not result.truncated
    assert result.characters == len(result.text)


def test_scanned_pdf_without_text_is_rejected_with_guidance():
    with pytest.raises(MaterialExtractionError) as info:
        extract_course_material("scan.pdf", make_pdf(None))
    assert info.value.code == "no_text"
    assert "scan" in info.value.message


def test_extracts_docx_paragraphs():
    result = extract_course_material("notes.docx", make_docx(["Chapter 3: Forces", NOTES]))
    assert result.text.splitlines() == ["Chapter 3: Forces", NOTES]


def test_extracts_pptx_slides_in_order_with_speaker_notes():
    data = make_zip({
        "ppt/slides/slide10.xml": slide_xml(["Third law", "Action and reaction pairs"]),
        "ppt/slides/slide2.xml": slide_xml(["First law", "Inertia keeps objects moving"]),
        "ppt/notesSlides/notesSlide2.xml": slide_xml(["Use the seatbelt example", "2"]),
    })
    result = extract_course_material("slides.pptx", data)
    assert result.pages == 2
    assert result.text.index("Slide 2:") < result.text.index("Slide 10:")  # numeric, not lexical, order
    assert "Speaker notes:\nUse the seatbelt example" in result.text
    assert "\n2\n" not in result.text  # bare slide-number noise from notes is dropped


def test_extracts_plain_text_in_common_encodings():
    assert extract_course_material("a.txt", NOTES.encode("utf-8")).text == NOTES
    assert extract_course_material("b.txt", NOTES.encode("utf-16")).text == NOTES  # with BOM
    assert extract_course_material("c.txt", ("Café " + NOTES).encode("cp1252")).text.startswith("Café")


def test_long_material_is_truncated():
    result = extract_course_material("big.txt", ((NOTES + "\n") * 2000).encode())
    assert result.truncated and result.characters == MAX_MATERIAL_CHARS


@pytest.mark.parametrize(
    ("filename", "data", "code"),
    [
        ("virus.exe", b"MZ....", "unsupported_type"),
        ("notes.txt", b"", "empty_file"),
        ("fake.pdf", b"not a pdf at all", "invalid_file"),
        ("fake.docx", b"plain bytes", "invalid_file"),
        ("binary.txt", b"\x00\x01\x02" * 50, "invalid_file"),
        ("tiny.txt", b"hi", "no_text"),
        ("noslides.pptx", make_zip({"ppt/presentation.xml": "<x/>"}), "invalid_file"),
    ],
)
def test_bad_files_are_rejected(filename, data, code):
    with pytest.raises(MaterialExtractionError) as info:
        extract_course_material(filename, data)
    assert info.value.code == code


def test_xml_entity_declarations_are_rejected():
    evil = '<!DOCTYPE x [<!ENTITY a "aaaa">]><w:document ' + W + "><w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>"
    with pytest.raises(MaterialExtractionError) as info:
        extract_course_material("evil.docx", make_zip({"word/document.xml": evil}))
    assert info.value.code == "invalid_file"


# --------------------------------------------------------------------------
# Generation request carries the material to the AI Engine
# --------------------------------------------------------------------------


def engine_draft():
    return {"title": "Forces", "questions": [{"question_type": "SUBJECTIVE", "question_text": "Explain inertia.", "marks": 10}]}


@pytest.mark.anyio
@pytest.mark.parametrize(("material", "expected", "grounded"), [(NOTES, NOTES, True), ("   ", None, False), (None, None, False)])
async def test_service_sends_course_material_and_reports_grounding(material, expected, grounded):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=engine_draft())

    service = AIGenerationService(base_url="http://ai.test", transport=httpx.MockTransport(handler))
    draft = await service.generate(AssignmentGenerationRequest(topic="Forces", total_marks=10, course_material=material))

    assert seen["body"]["course_materials"] == expected
    assert draft.grounded_in_course_materials is grounded


@pytest.mark.anyio
@pytest.mark.parametrize(("syllabus", "expected"), [("  Unit 2 only. No calculators.  ", "Unit 2 only. No calculators."), ("  ", None), (None, None)])
async def test_service_sends_syllabus_to_engine(syllabus, expected):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=engine_draft())

    service = AIGenerationService(base_url="http://ai.test", transport=httpx.MockTransport(handler))
    await service.generate(AssignmentGenerationRequest(topic="Forces", total_marks=10, syllabus=syllabus))
    assert seen["body"]["syllabus"] == expected


def test_syllabus_length_is_limited():
    with pytest.raises(ValueError):
        AssignmentGenerationRequest(topic="Forces", total_marks=10, syllabus="x" * 50_001)


def test_request_rejects_material_over_limit():
    with pytest.raises(ValueError):
        AssignmentGenerationRequest(topic="Forces", course_material="x" * (MAX_MATERIAL_CHARS + 1))


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------


@pytest.fixture
def api(verifier, profiles) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(ai_generation.router, prefix="/api/v1")
    test_app.dependency_overrides[get_token_verifier] = lambda: verifier
    test_app.dependency_overrides[get_profile_repository] = lambda: profiles
    return test_app


@pytest.fixture
def make_user(make_token, profiles):
    def _make(role: str) -> dict[str, str]:
        user_id = uuid4()
        profiles.add(user_id, role)
        return bearer(make_token(user_id))

    return _make


def test_teacher_extracts_material(api, make_user):
    client = TestClient(api)
    response = client.post(
        EXTRACT_URL, files={"file": ("notes.docx", make_docx([NOTES]), "application/octet-stream")},
        headers=make_user("teacher"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filename"] == "notes.docx" and body["text"] == NOTES and body["truncated"] is False


def test_student_cannot_extract_material(api, make_user):
    response = TestClient(api).post(
        EXTRACT_URL, files={"file": ("notes.txt", NOTES.encode(), "text/plain")}, headers=make_user("student")
    )
    assert response.status_code == 403


def test_extract_requires_authentication(api):
    response = TestClient(api).post(EXTRACT_URL, files={"file": ("notes.txt", NOTES.encode(), "text/plain")})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("filename", "data", "status_code", "code"),
    [
        ("virus.exe", b"MZ" * 20, 415, "unsupported_type"),
        ("scan.pdf", make_pdf(None), 422, "no_text"),
    ],
)
def test_extract_errors_map_to_http(api, make_user, filename, data, status_code, code):
    response = TestClient(api).post(
        EXTRACT_URL, files={"file": (filename, data, "application/octet-stream")}, headers=make_user("teacher")
    )
    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code


def test_generate_endpoint_forwards_course_material(api, make_user):
    seen = {}

    class CapturingService:
        async def generate(self, request):
            seen["material"] = request.course_material
            return await AIGenerationService(
                base_url="http://ai.test",
                transport=httpx.MockTransport(lambda r: httpx.Response(200, json=engine_draft())),
            ).generate(request)

    api.dependency_overrides[get_ai_generation_service] = lambda: CapturingService()
    response = TestClient(api).post(
        GENERATE_URL,
        json={"topic": "Forces", "question_count": 1, "total_marks": 10, "course_material": NOTES},
        headers=make_user("teacher"),
    )

    assert response.status_code == 200, response.text
    assert seen["material"] == NOTES
    assert response.json()["grounded_in_course_materials"] is True
