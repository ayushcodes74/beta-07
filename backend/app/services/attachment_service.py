"""Files attached to assignment questions: upload, view, delete, and text extraction for AI grading.

Text extraction reuses the existing pipeline: PDFs with a text layer are read directly (pypdf, as for
course materials); scanned PDFs and pictures go through the OCR engine (pictures are wrapped into a
one-page PDF first, since the OCR engine takes PDFs). The extracted text is given to the AI as that
question's material when checking answers (see GradingService).
"""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
import logging
from typing import Optional
from uuid import UUID, uuid4

from app.database.attachment_repository import AttachmentRepository
from app.schemas.attachment import AttachmentRecord, AttachmentResponse
from app.schemas.user import Role
from app.services.assignment_service import AssignmentService
from app.services.auth_service import CurrentUser
from app.services.course_material_service import MaterialExtractionError, extract_course_material_pages

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_QUESTION = 5
MAX_TEXT_CHARS = 60_000
# Per-question material sent to the AI (all of the question's files together).
MAX_MATERIAL_CHARS = 20_000
_PREVIEW_CHARS = 400
# Pictures sent to the grading model (per question), downscaled above these limits.
MAX_GRADING_IMAGES_PER_QUESTION = 4
MAX_GRADING_IMAGE_BYTES = 3 * 1024 * 1024
MAX_GRADING_IMAGE_SIDE = 1600

_EXTENSIONS = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class AttachmentValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AttachmentNotFoundError(Exception):
    pass


def sniff_content_type(data: bytes) -> Optional[str]:
    """Real file type from the first bytes (the browser-supplied type and file name are not trusted)."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def grading_image(data: bytes, content_type: str) -> tuple[str, bytes]:
    """The picture as sent to the grading model: unchanged when small, else downscaled to a JPEG so a
    question's figures stay well within model request limits."""
    if len(data) <= MAX_GRADING_IMAGE_BYTES:
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            if max(image.size) <= MAX_GRADING_IMAGE_SIDE:
                return content_type, data
    from PIL import Image

    with Image.open(BytesIO(data)) as image:
        image.load()
        page = image.convert("RGB")
        page.thumbnail((MAX_GRADING_IMAGE_SIDE, MAX_GRADING_IMAGE_SIDE))
        out = BytesIO()
        page.save(out, format="JPEG", quality=85)
        return "image/jpeg", out.getvalue()


def image_to_pdf(data: bytes) -> bytes:
    from PIL import Image

    with Image.open(BytesIO(data)) as image:
        image.load()
        page = image.convert("RGB")
        out = BytesIO()
        page.save(out, format="PDF", resolution=200.0)
        return out.getvalue()


class AttachmentService:
    def __init__(self, repository: AttachmentRepository, assignments: AssignmentService, ocr_client) -> None:
        self.repository = repository
        self.assignments = assignments
        self.ocr_client = ocr_client

    # ---- teacher: upload / delete ---------------------------------------------------------

    async def upload(
        self,
        teacher: CurrentUser,
        assignment_id: UUID,
        question_number: int,
        filename: str,
        data: bytes,
        *,
        access_token: str,
    ) -> AttachmentRecord:
        if teacher.role is not Role.TEACHER:
            raise AttachmentValidationError("forbidden", "Only the assignment's teacher can attach files.")
        assignment = await asyncio.to_thread(self.assignments.get_for, teacher, assignment_id, access_token=access_token)
        count = len(assignment.content.questions)
        if not 1 <= question_number <= count:
            raise AttachmentValidationError("invalid_question", f"This assignment has {count} question(s).")
        if not data:
            raise AttachmentValidationError("empty_file", "The file is empty.")
        if len(data) > MAX_FILE_BYTES:
            raise AttachmentValidationError("file_too_large", "Files can be at most 10 MB.")
        content_type = sniff_content_type(data)
        if content_type is None:
            raise AttachmentValidationError("unsupported_type", "Attach a PDF or a picture (PNG, JPG or WEBP).")
        existing = await asyncio.to_thread(
            self.repository.list_for_assignment, assignment_id, access_token=access_token
        )
        if sum(1 for a in existing if a.question_number == question_number) >= MAX_FILES_PER_QUESTION:
            raise AttachmentValidationError(
                "too_many_files", f"A question can have at most {MAX_FILES_PER_QUESTION} files."
            )

        path = f"{assignment_id}/{uuid4()}.{_EXTENSIONS[content_type]}"
        safe_name = (filename or "attachment").replace("/", "_").replace("\\", "_")[:255]
        await asyncio.to_thread(self.repository.upload_file, path, data, content_type, access_token=access_token)
        try:
            return await asyncio.to_thread(
                self.repository.insert,
                {
                    "assignment_id": str(assignment_id),
                    "question_number": question_number,
                    "storage_path": path,
                    "filename": safe_name,
                    "content_type": content_type,
                    "size_bytes": len(data),
                    "uploaded_by": str(teacher.id),
                },
                access_token=access_token,
            )
        except Exception:
            # Don't leave an orphan file in the bucket if the row could not be saved.
            try:
                await asyncio.to_thread(self.repository.delete_file, path, access_token=access_token)
            except Exception:
                logger.warning("Could not remove orphaned attachment file")
            raise

    async def delete(
        self, teacher: CurrentUser, assignment_id: UUID, attachment_id: UUID, *, access_token: str
    ) -> None:
        await asyncio.to_thread(self.assignments.get_for, teacher, assignment_id, access_token=access_token)
        if teacher.role is not Role.TEACHER:
            raise AttachmentValidationError("forbidden", "Only the assignment's teacher can remove files.")
        record = await asyncio.to_thread(self.repository.get, attachment_id, access_token=access_token)
        if record is None or record.assignment_id != assignment_id:
            raise AttachmentNotFoundError
        await asyncio.to_thread(self.repository.delete, attachment_id, access_token=access_token)
        try:
            await asyncio.to_thread(self.repository.delete_file, record.storage_path, access_token=access_token)
        except Exception:
            logger.warning("Attachment row deleted but its file could not be removed from storage")

    async def move(
        self, teacher: CurrentUser, assignment_id: UUID, attachment_id: UUID, question_number: int, *, access_token: str
    ) -> None:
        """Re-point a file at another question (the teacher reordered or edited the questions)."""
        if teacher.role is not Role.TEACHER:
            raise AttachmentValidationError("forbidden", "Only the assignment's teacher can move files.")
        assignment = await asyncio.to_thread(self.assignments.get_for, teacher, assignment_id, access_token=access_token)
        count = len(assignment.content.questions)
        if not 1 <= question_number <= count:
            raise AttachmentValidationError("invalid_question", f"This assignment has {count} question(s).")
        record = await asyncio.to_thread(self.repository.get, attachment_id, access_token=access_token)
        if record is None or record.assignment_id != assignment_id:
            raise AttachmentNotFoundError
        if record.question_number != question_number:
            await asyncio.to_thread(
                self.repository.set_question_number, attachment_id, question_number, access_token=access_token
            )

    # ---- text extraction (runs after the upload response) ---------------------------------

    async def extract_text(self, record: AttachmentRecord, data: bytes, *, access_token: str) -> None:
        """Extract the file's text and store it on the record. Never raises (status records the outcome)."""
        try:
            text = await self._text_of(record, data)
            status, error = ("ready", None) if text.strip() else ("no_text", "No readable text was found in this file.")
        except Exception as exc:
            logger.warning("Attachment text extraction failed: %s", type(exc).__name__)
            text, status, error = None, "failed", f"Text extraction failed ({type(exc).__name__})."
        try:
            await asyncio.to_thread(
                self.repository.set_extraction,
                record.id,
                status,
                (text or "").strip()[:MAX_TEXT_CHARS] or None,
                error,
                access_token=access_token,
            )
        except Exception:
            logger.warning("Could not store extracted attachment text")

    async def _text_of(self, record: AttachmentRecord, data: bytes) -> str:
        if record.content_type == "application/pdf":
            try:
                extracted = extract_course_material_pages(record.filename if record.filename.lower().endswith(".pdf") else "file.pdf", data)
                if not extracted.needs_ocr:
                    return "\n\n".join(page for page in extracted.pages if page)
            except MaterialExtractionError:
                pass  # e.g. no text layer: fall through to OCR
            pdf = data
        else:
            pdf = await asyncio.to_thread(image_to_pdf, data)
        job = await self.ocr_client.submit_pdf(pdf, filename=f"attachment-{record.id}.pdf")
        document = await self.ocr_client.poll_until_complete(job.job_id)
        pages = sorted(document.pages, key=lambda page: page.page_number)
        return "\n\n".join(page.full_text.strip() for page in pages if page.full_text and page.full_text.strip())

    # ---- listing (teacher or enrolled student) -------------------------------------------

    async def list_for(self, user: CurrentUser, assignment_id: UUID, *, access_token: str) -> list[AttachmentResponse]:
        # Owning teacher, or a student with access to the published assignment (else 404).
        await asyncio.to_thread(self.assignments.get_for, user, assignment_id, access_token=access_token)
        records = await asyncio.to_thread(self.repository.list_for_assignment, assignment_id, access_token=access_token)
        try:
            urls = await asyncio.to_thread(
                self.repository.signed_urls, [r.storage_path for r in records], access_token=access_token
            )
        except Exception:
            logger.warning("Could not sign attachment URLs")
            urls = {}
        is_teacher = user.role is Role.TEACHER
        return [
            AttachmentResponse(
                id=r.id,
                assignment_id=r.assignment_id,
                question_number=r.question_number,
                filename=r.filename,
                content_type=r.content_type,
                size_bytes=r.size_bytes,
                url=urls.get(r.storage_path),
                extraction_status=r.extraction_status,
                text_preview=((r.extracted_text or "")[:_PREVIEW_CHARS] or None) if is_teacher else None,
                created_at=r.created_at,
            )
            for r in records
        ]

    # ---- grading -------------------------------------------------------------------------

    def question_images(self, assignment_id: UUID, *, access_token: str) -> dict[int, list[dict]]:
        """{question number: [{mime_type, data_base64}]} for the pictures attached to each question, so a
        multimodal grader can look at them (graphs, diagrams) and not only their OCR text. Best-effort."""
        try:
            records = self.repository.list_for_assignment(assignment_id, access_token=access_token)
        except Exception as exc:
            logger.warning("Attachment pictures unavailable for grading: %s", type(exc).__name__)
            return {}
        images: dict[int, list[dict]] = {}
        for record in records:
            if not record.content_type.startswith("image/"):
                continue
            if len(images.get(record.question_number, [])) >= MAX_GRADING_IMAGES_PER_QUESTION:
                continue
            try:
                data = self.repository.download_file(record.storage_path, access_token=access_token)
                mime, data = grading_image(data, record.content_type)
            except Exception as exc:
                logger.warning("Could not load an attached picture for grading: %s", type(exc).__name__)
                continue
            images.setdefault(record.question_number, []).append(
                {"mime_type": mime, "data_base64": base64.b64encode(data).decode("ascii")}
            )
        return images

    def question_material(self, assignment_id: UUID, *, access_token: str) -> dict[int, str]:
        """{question number: text of its attached files} for AI grading (ready files only). Best-effort."""
        try:
            records = self.repository.list_for_assignment(assignment_id, access_token=access_token)
        except Exception as exc:
            logger.warning("Attachment text unavailable for grading: %s", type(exc).__name__)
            return {}
        material: dict[int, list[str]] = {}
        for record in records:
            if record.extraction_status == "ready" and record.extracted_text:
                material.setdefault(record.question_number, []).append(
                    f"[File: {record.filename}]\n{record.extracted_text.strip()}"
                )
        return {number: "\n\n".join(parts)[:MAX_MATERIAL_CHARS] for number, parts in material.items()}
