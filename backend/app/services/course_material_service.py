"""Text extraction for course material attached while creating an assignment.

Teachers attach notes/slides/readings in the assignment editor; the extracted text is sent
with the AI generation request so questions are grounded in that material. Nothing is
stored: the text lives only in the teacher's editor session.

Supported: PDF (text layer via pypdf), DOCX, PPTX (slides + speaker notes), TXT/MD.
DOCX/PPTX are parsed with the standard library (they are zipped XML), with size caps
against zip bombs and DTD/entity declarations rejected outright.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 25 * 1024 * 1024
# Combined course material sent with one generation request. ~25k tokens: large enough for a
# chapter of notes, small enough to stay within free-tier per-minute token limits (the material
# is included in the question prompt and again in each rubric prompt).
MAX_MATERIAL_CHARS = 100_000
MAX_PDF_PAGES = 500
_MAX_XML_PART_BYTES = 30 * 1024 * 1024
_MAX_ZIP_TOTAL_BYTES = 150 * 1024 * 1024

SUPPORTED_EXTENSIONS = {"pdf", "docx", "pptx", "txt", "md"}

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class MaterialExtractionError(Exception):
    """The file can't be used as course material. ``code`` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExtractedMaterial:
    filename: str
    text: str
    characters: int
    truncated: bool
    pages: int | None = None  # PDF pages / PPTX slides


def extract_course_material(filename: str, data: bytes) -> ExtractedMaterial:
    """Extract plain text from an uploaded course-material file."""
    name = (filename or "material").strip()[:255] or "material"
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise MaterialExtractionError(
            "unsupported_type", "Unsupported file type. Attach a PDF, DOCX, PPTX or TXT file."
        )
    if not data:
        raise MaterialExtractionError("empty_file", "The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise MaterialExtractionError("file_too_large", "The file is larger than 25 MB.")

    pages: int | None = None
    if extension == "pdf":
        text, pages = _pdf_text(data)
    elif extension == "docx":
        text = _docx_text(data)
    elif extension == "pptx":
        text, pages = _pptx_text(data)
    else:
        text = _plain_text(data)

    text = _normalise(text)
    if len(text) < 20:
        if extension == "pdf":
            raise MaterialExtractionError(
                "no_text",
                "No selectable text found in this PDF (it may be a scan). Attach a text-based PDF, "
                "DOCX or TXT, or paste the material instead.",
            )
        raise MaterialExtractionError("no_text", "No readable text found in this file.")

    truncated = len(text) > MAX_MATERIAL_CHARS
    if truncated:
        text = text[:MAX_MATERIAL_CHARS]
    return ExtractedMaterial(filename=name, text=text, characters=len(text), truncated=truncated, pages=pages)


# --------------------------------------------------------------------------
# Format handlers
# --------------------------------------------------------------------------


def _pdf_text(data: bytes) -> tuple[str, int]:
    if not data.startswith(b"%PDF"):
        raise MaterialExtractionError("invalid_file", "This file is not a valid PDF.")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - dependency listed in requirements.txt
        raise MaterialExtractionError("unavailable", "PDF support is not installed on the server.") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise MaterialExtractionError("encrypted", "This PDF is password-protected. Remove the password and retry.")
        page_count = len(reader.pages)
        parts: list[str] = []
        total = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            page_text = page.extract_text() or ""
            parts.append(page_text)
            total += len(page_text)
            if total > MAX_MATERIAL_CHARS * 2:  # enough text; skip parsing the rest
                break
        return "\n\n".join(parts), page_count
    except MaterialExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        logger.info("Could not parse PDF course material: %s", type(exc).__name__)
        raise MaterialExtractionError("invalid_file", "This PDF could not be read. It may be corrupted.") from exc


def _open_office_zip(data: bytes, kind: str) -> zipfile.ZipFile:
    if not data.startswith(b"PK"):
        raise MaterialExtractionError("invalid_file", f"This file is not a valid {kind} document.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise MaterialExtractionError("invalid_file", f"This file is not a valid {kind} document.") from exc
    if sum(info.file_size for info in archive.infolist()) > _MAX_ZIP_TOTAL_BYTES:
        raise MaterialExtractionError("file_too_large", "The document expands to an unreasonably large size.")
    return archive


def _read_xml(archive: zipfile.ZipFile, part: str) -> ElementTree.Element | None:
    try:
        info = archive.getinfo(part)
    except KeyError:
        return None
    if info.file_size > _MAX_XML_PART_BYTES:
        raise MaterialExtractionError("file_too_large", "The document contains an unreasonably large section.")
    raw = archive.read(info)
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise MaterialExtractionError("invalid_file", "The document contains unsupported XML declarations.")
    try:
        return ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise MaterialExtractionError("invalid_file", "The document could not be read. It may be corrupted.") from exc


def _paragraphs(root: ElementTree.Element, ns: str) -> list[str]:
    lines = []
    for paragraph in root.iter(f"{ns}p"):
        line = "".join(node.text or "" for node in paragraph.iter(f"{ns}t")).strip()
        if line:
            lines.append(line)
    return lines


def _docx_text(data: bytes) -> str:
    with _open_office_zip(data, "DOCX") as archive:
        root = _read_xml(archive, "word/document.xml")
        if root is None:
            raise MaterialExtractionError("invalid_file", "This file is not a valid DOCX document.")
        return "\n".join(_paragraphs(root, _W_NS))


def _slide_number(part: str) -> int:
    match = re.search(r"(\d+)\.xml$", part)
    return int(match.group(1)) if match else 0


def _pptx_text(data: bytes) -> tuple[str, int]:
    with _open_office_zip(data, "PPTX") as archive:
        names = archive.namelist()
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_slide_number)
        if not slides:
            raise MaterialExtractionError("invalid_file", "This file is not a valid PPTX presentation.")
        sections = []
        for part in slides:
            number = _slide_number(part)
            root = _read_xml(archive, part)
            lines = _paragraphs(root, _A_NS) if root is not None else []
            notes_root = _read_xml(archive, f"ppt/notesSlides/notesSlide{number}.xml")
            # Notes slides repeat the slide number as a bare digit; drop that noise.
            notes = [l for l in _paragraphs(notes_root, _A_NS) if not l.isdigit()] if notes_root is not None else []
            if lines or notes:
                block = [f"Slide {number}:", *lines]
                if notes:
                    block += ["Speaker notes:", *notes]
                sections.append("\n".join(block))
        return "\n\n".join(sections), len(slides)


def _plain_text(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):  # UTF-16 with BOM (e.g. Windows Notepad "Unicode")
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise MaterialExtractionError("invalid_file", "This text file could not be decoded.") from exc
    if b"\x00" in data[:8192]:
        raise MaterialExtractionError("invalid_file", "This doesn't look like a text file.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _normalise(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n[ ]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------
# Page-level extraction for the course-material RAG index
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedPages:
    """Course material split into pages (PDF pages / PPTX slides; DOCX and TXT are one page)."""

    filename: str
    pages: list[dict]  # [{"page_number": int, "text": str}], only pages with text
    page_count: int
    needs_ocr: bool = False  # PDF without a text layer (e.g. a scan): send it to the OCR service


def extract_course_material_pages(filename: str, data: bytes) -> ExtractedPages:
    """Like ``extract_course_material`` but keeps page numbers for evidence citations.

    A PDF with no selectable text is returned with ``needs_ocr=True`` instead of failing, so the
    caller can run it through the OCR service.
    """
    name = (filename or "material").strip()[:255] or "material"
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise MaterialExtractionError(
            "unsupported_type", "Unsupported file type. Upload a PDF, DOCX, PPTX or TXT file."
        )
    if not data:
        raise MaterialExtractionError("empty_file", "The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise MaterialExtractionError("file_too_large", "The file is larger than 25 MB.")

    if extension == "pdf":
        raw_pages = _pdf_page_texts(data)
    elif extension == "pptx":
        text, _ = _pptx_text(data)
        raw_pages = [block for block in text.split("\n\n")]  # one block per slide
    elif extension == "docx":
        raw_pages = [_docx_text(data)]
    else:
        raw_pages = [_plain_text(data)]

    pages = [
        {"page_number": number, "text": _normalise(page)}
        for number, page in enumerate(raw_pages, start=1)
        if len(_normalise(page)) >= 20
    ]
    if not pages:
        if extension == "pdf":
            return ExtractedPages(filename=name, pages=[], page_count=len(raw_pages), needs_ocr=True)
        raise MaterialExtractionError("no_text", "No readable text found in this file.")
    return ExtractedPages(filename=name, pages=pages, page_count=len(raw_pages))


def _pdf_page_texts(data: bytes) -> list[str]:
    if not data.startswith(b"%PDF"):
        raise MaterialExtractionError("invalid_file", "This file is not a valid PDF.")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - dependency listed in requirements.txt
        raise MaterialExtractionError("unavailable", "PDF support is not installed on the server.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise MaterialExtractionError("encrypted", "This PDF is password-protected. Remove the password and retry.")
        return [(page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES]]
    except MaterialExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        logger.info("Could not parse PDF course material: %s", type(exc).__name__)
        raise MaterialExtractionError("invalid_file", "This PDF could not be read. It may be corrupted.") from exc
