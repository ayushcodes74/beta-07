"""Files attached to assignment questions: validation, storage calls, text extraction, listing, grading."""

import asyncio
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.database.attachment_repository import SupabaseAttachmentRepository
from app.schemas.attachment import AttachmentRecord
from app.schemas.user import Role
from app.services.assignment_service import AssignmentNotFoundError
from app.services.attachment_service import (
    MAX_FILES_PER_QUESTION,
    AttachmentService,
    AttachmentValidationError,
    image_to_pdf,
    sniff_content_type,
)
from app.services.auth_service import CurrentUser
from app.services.grading_service import _question_payload

TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
STUDENT = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)
ASSIGNMENT_ID = uuid4()
PDF = b"%PDF-1.4\n%fake"


def _png() -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (220, 60), "white")
    ImageDraw.Draw(image).text((10, 20), "y = x^2", fill="black")
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class Assignments:
    """get_for: teacher owns it; STUDENT sees it only when `published_for_student`."""

    def __init__(self, questions=2, published_for_student=True):
        self.questions = questions
        self.published_for_student = published_for_student

    def get_for(self, user, assignment_id, *, access_token):
        if assignment_id != ASSIGNMENT_ID or (user.role is Role.STUDENT and not self.published_for_student):
            raise AssignmentNotFoundError
        return SimpleNamespace(id=ASSIGNMENT_ID, content=SimpleNamespace(questions=[object()] * self.questions))


class Repo:
    def __init__(self, fail_insert=False):
        self.rows: dict = {}
        self.files: dict = {}
        self.fail_insert = fail_insert
        self.extraction: dict = {}

    def upload_file(self, path, data, content_type, *, access_token):
        self.files[path] = (data, content_type, access_token)

    def delete_file(self, path, *, access_token):
        self.files.pop(path, None)

    def signed_urls(self, paths, *, access_token):
        return {p: f"https://signed/{p}" for p in paths}

    def insert(self, record, *, access_token):
        if self.fail_insert:
            raise RuntimeError("RLS")
        row = AttachmentRecord.model_validate({**record, "id": uuid4(), "created_at": datetime.now(UTC)})
        self.rows[row.id] = row
        return row

    def get(self, attachment_id, *, access_token):
        return self.rows.get(attachment_id)

    def list_for_assignment(self, assignment_id, *, access_token):
        return [r for r in self.rows.values() if r.assignment_id == assignment_id]

    def set_extraction(self, attachment_id, status, text, error, *, access_token):
        self.extraction[attachment_id] = (status, text, error)
        self.rows[attachment_id] = self.rows[attachment_id].model_copy(
            update={"extraction_status": status, "extracted_text": text, "extraction_error": error}
        )

    def delete(self, attachment_id, *, access_token):
        self.rows.pop(attachment_id, None)


class OCR:
    def __init__(self, text="OCR TEXT", fail=False):
        self.text, self.fail, self.submitted = text, fail, []

    async def submit_pdf(self, data, filename="x.pdf", submission_id=None):
        if self.fail:
            raise RuntimeError("ocr down")
        self.submitted.append(data)
        return SimpleNamespace(job_id="job-1")

    async def poll_until_complete(self, job_id, poll_interval=None, timeout=None):
        return SimpleNamespace(pages=[SimpleNamespace(page_number=1, full_text=self.text)])


def _service(repo=None, ocr=None, **kw):
    return AttachmentService(repo or Repo(), Assignments(**kw), ocr or OCR())


def _upload(service, data, question=1, name="figure.png", user=TEACHER):
    return asyncio.run(service.upload(user, ASSIGNMENT_ID, question, name, data, access_token="teacher-token"))


# ---- validation ---------------------------------------------------------------------------------


def test_file_type_comes_from_the_bytes_not_the_name():
    assert sniff_content_type(PDF) == "application/pdf"
    assert sniff_content_type(_png()) == "image/png"
    assert sniff_content_type(b"\xff\xd8\xff\xe0jpeg") == "image/jpeg"
    assert sniff_content_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_content_type(b"MZ\x90\x00 an .exe renamed to .png") is None


@pytest.mark.parametrize(
    "data, question, code",
    [
        (b"MZ not a picture", 1, "unsupported_type"),
        (PDF, 3, "invalid_question"),
        (PDF, 0, "invalid_question"),
        (b"", 1, "empty_file"),
        (b"%PDF-" + b"x" * (10 * 1024 * 1024), 1, "file_too_large"),
    ],
    # Short ids: the 10 MB payload must not end up in the test name (env var length limit on Windows).
    ids=["not-a-picture", "question-too-high", "question-zero", "empty", "over-10mb"],
)
def test_upload_rejects_bad_files(data, question, code):
    with pytest.raises(AttachmentValidationError) as error:
        _upload(_service(), data, question=question)
    assert error.value.code == code


def test_students_cannot_upload():
    with pytest.raises(AttachmentValidationError) as error:
        _upload(_service(), PDF, user=STUDENT)
    assert error.value.code == "forbidden"


def test_upload_stores_file_under_the_assignment_folder_with_the_teachers_token():
    repo = Repo()
    record = _upload(_service(repo), _png(), question=2, name="../../etc/graph.png")

    path, (data, content_type, token) = next(iter(repo.files.items()))
    assert path.startswith(f"{ASSIGNMENT_ID}/") and path.endswith(".png")
    assert content_type == "image/png" and token == "teacher-token"
    assert record.question_number == 2 and record.storage_path == path
    assert "/" not in record.filename  # no path tricks in the stored name
    assert record.extraction_status == "pending"


def test_at_most_five_files_per_question():
    service = _service()
    for _ in range(MAX_FILES_PER_QUESTION):
        _upload(service, PDF)
    with pytest.raises(AttachmentValidationError) as error:
        _upload(service, PDF)
    assert error.value.code == "too_many_files"
    _upload(service, PDF, question=2)  # other questions are unaffected


def test_file_is_removed_again_when_the_row_cannot_be_saved():
    repo = Repo(fail_insert=True)
    with pytest.raises(RuntimeError):
        _upload(_service(repo), PDF)
    assert repo.files == {}


# ---- text extraction ----------------------------------------------------------------------------


def test_picture_is_wrapped_in_a_pdf_and_read_by_ocr():
    repo, ocr = Repo(), OCR(text="y = x^2")
    service = _service(repo, ocr)
    record = _upload(service, _png())

    asyncio.run(service.extract_text(record, _png(), access_token="t"))

    assert ocr.submitted and ocr.submitted[0].startswith(b"%PDF")
    assert repo.extraction[record.id] == ("ready", "y = x^2", None)


def test_pdf_with_a_text_layer_is_read_without_ocr(monkeypatch):
    repo, ocr = Repo(), OCR()
    service = _service(repo, ocr)
    record = _upload(service, PDF, name="source.pdf")
    monkeypatch.setattr(
        "app.services.attachment_service.extract_course_material_pages",
        lambda name, data: SimpleNamespace(needs_ocr=False, pages=["Passage text", "page two"]),
    )

    asyncio.run(service.extract_text(record, PDF, access_token="t"))

    assert ocr.submitted == []
    assert repo.extraction[record.id][:2] == ("ready", "Passage text\n\npage two")


def test_unreadable_and_failed_extraction_are_recorded_not_raised():
    repo = Repo()
    service = _service(repo, OCR(text="   "))
    blank = _upload(service, _png())
    asyncio.run(service.extract_text(blank, _png(), access_token="t"))
    assert repo.extraction[blank.id][0] == "no_text"

    failing = _service(repo, OCR(fail=True))
    broken = _upload(failing, _png(), question=2)
    asyncio.run(failing.extract_text(broken, _png(), access_token="t"))
    assert repo.extraction[broken.id][0] == "failed"


# ---- listing + grading --------------------------------------------------------------------------


def test_students_get_urls_but_never_the_extracted_text():
    repo = Repo()
    service = _service(repo, OCR(text="secret-ish OCR text"))
    record = _upload(service, _png())
    asyncio.run(service.extract_text(record, _png(), access_token="t"))

    as_student = asyncio.run(service.list_for(STUDENT, ASSIGNMENT_ID, access_token="s"))
    as_teacher = asyncio.run(service.list_for(TEACHER, ASSIGNMENT_ID, access_token="t"))

    assert as_student[0].url == f"https://signed/{record.storage_path}" and as_student[0].text_preview is None
    assert as_teacher[0].text_preview == "secret-ish OCR text"


def test_students_without_access_get_not_found():
    with pytest.raises(AssignmentNotFoundError):
        asyncio.run(_service(published_for_student=False).list_for(STUDENT, ASSIGNMENT_ID, access_token="s"))


def test_question_material_groups_ready_files_per_question():
    repo = Repo()
    service = _service(repo, OCR(text="diagram text"))
    first = _upload(service, _png(), question=1, name="diagram.png")
    _upload(service, _png(), question=2)  # still pending: not used
    asyncio.run(service.extract_text(first, _png(), access_token="t"))

    material = service.question_material(ASSIGNMENT_ID, access_token="t")

    assert material == {1: "[File: diagram.png]\ndiagram text"}


def test_grading_payload_carries_the_question_material():
    question = SimpleNamespace(type="subjective", text="Describe the figure.", marks=5, expected_answer="A parabola",
                               instructions=None)
    assert _question_payload(question, 1, [], "[File: f.png]\ny = x^2")["reference_material"] == "[File: f.png]\ny = x^2"
    assert "reference_material" not in _question_payload(question, 1, [], None)


# ---- storage REST calls -------------------------------------------------------------------------


def test_storage_calls_use_the_users_token_and_return_absolute_signed_urls(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    # The real setting is a SecretStr (a plain str here once hid a crash on every upload).
    monkeypatch.setattr(settings, "SUPABASE_KEY", SecretStr("anon-key"))
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("authorization"), request.headers.get("apikey")))
        if request.url.path.endswith("/object/sign/assignment-files"):
            return httpx.Response(200, json=[{"path": "a/1.png", "signedURL": "/object/sign/assignment-files/a/1.png?token=x"},
                                             {"path": "a/2.png", "error": "not found", "signedURL": None}])
        return httpx.Response(200, json={})

    repo = SupabaseAttachmentRepository(transport=httpx.MockTransport(handler))
    repo.upload_file("a/1.png", b"png", "image/png", access_token="user-jwt")
    urls = repo.signed_urls(["a/1.png", "a/2.png"], access_token="user-jwt")

    assert seen[0] == ("POST", "/storage/v1/object/assignment-files/a/1.png", "Bearer user-jwt", "anon-key")
    assert urls == {"a/1.png": "https://proj.supabase.co/storage/v1/object/sign/assignment-files/a/1.png?token=x"}


def test_files_follow_their_question_when_questions_are_reordered():
    repo = Repo()
    repo.set_question_number = lambda attachment_id, number, *, access_token: repo.rows.__setitem__(
        attachment_id, repo.rows[attachment_id].model_copy(update={"question_number": number})
    )
    service = _service(repo)
    record = _upload(service, PDF, question=1)

    asyncio.run(service.move(TEACHER, ASSIGNMENT_ID, record.id, 2, access_token="t"))
    assert repo.rows[record.id].question_number == 2

    with pytest.raises(AttachmentValidationError):
        asyncio.run(service.move(TEACHER, ASSIGNMENT_ID, record.id, 9, access_token="t"))


# ---- pictures sent to the grading model -------------------------------------------------------

from app.services.attachment_service import MAX_GRADING_IMAGES_PER_QUESTION, grading_image  # noqa: E402


class DownloadRepo(Repo):
    def download_file(self, path, *, access_token):
        assert access_token == "teacher-token"
        return self.files[path][0]


def test_question_pictures_are_sent_to_the_grader_but_pdfs_are_not():
    import base64 as b64

    repo = DownloadRepo()
    service = _service(repo)
    png = _png()
    _upload(service, png, question=1, name="graph.png")
    _upload(service, PDF, question=1, name="notes.pdf")
    _upload(service, png, question=2)

    images = service.question_images(ASSIGNMENT_ID, access_token="teacher-token")

    assert sorted(images) == [1, 2]
    assert [i["mime_type"] for i in images[1]] == ["image/png"]  # the PDF is used as text only
    assert b64.b64decode(images[1][0]["data_base64"]) == png


def test_at_most_four_pictures_per_question_reach_the_grader():
    repo = DownloadRepo()
    service = _service(repo)
    for _ in range(MAX_FILES_PER_QUESTION):
        _upload(service, _png(), question=1)
    assert len(service.question_images(ASSIGNMENT_ID, access_token="teacher-token")[1]) == MAX_GRADING_IMAGES_PER_QUESTION


def test_large_pictures_are_downscaled_to_jpeg():
    from PIL import Image

    big = BytesIO()
    Image.new("RGB", (4000, 3000), "white").save(big, format="PNG")
    mime, data = grading_image(big.getvalue(), "image/png")
    assert mime == "image/jpeg"
    with Image.open(BytesIO(data)) as image:
        assert max(image.size) == 1600

    small = _png()
    assert grading_image(small, "image/png") == ("image/png", small)


def test_grading_payload_carries_the_pictures():
    question = SimpleNamespace(type="subjective", text="Describe the figure.", marks=5, expected_answer="A parabola",
                               instructions=None)
    image = {"mime_type": "image/png", "data_base64": "aGk="}
    assert _question_payload(question, 1, [], None, [image])["reference_images"] == [image]
    assert "reference_images" not in _question_payload(question, 1, [], None, None)
