"""Shared test fixtures for TrustGrade OCR Ingestion Module tests."""

import os
import tempfile
from pathlib import Path
import pytest
import pymupdf

# Don't spawn the background model-preload thread for every TestClient; tests load models explicitly.
os.environ.setdefault("OCR_PRELOAD_MODELS", "false")
# Never call the real OCR.space API (or spend its quota) from tests; OCR.space tests use mocks.
os.environ["OCR_SPACE_API_KEY"] = ""
# Keep test jobs out of the real ocr-engine/storage folder (must be set before app.api.config is imported).
os.environ.setdefault("OCR_STORAGE_ROOT", tempfile.mkdtemp(prefix="trustgrade-ocr-tests-"))


@pytest.fixture
def sample_single_page_pdf(tmp_path: Path) -> Path:
    """Creates a valid single-page PDF document."""
    pdf_path = tmp_path / "single_page.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # Standard A4
    page.insert_text((50, 100), "TrustGrade Student Submission Page 1")
    doc.set_metadata({
        "title": "Assignment 1",
        "author": "Student 101",
        "subject": "Mathematics",
    })
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def sample_multi_page_pdf(tmp_path: Path) -> Path:
    """Creates a valid 3-page PDF document."""
    pdf_path = tmp_path / "multi_page.pdf"
    doc = pymupdf.open()
    for i in range(1, 4):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 100), f"Student Answer Page {i}")
    doc.set_metadata({
        "title": "History Assignment",
        "author": "Student 202",
    })
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def empty_pdf_file(tmp_path: Path) -> Path:
    """Creates an empty (0 byte) file with .pdf extension."""
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"")
    return pdf_path


@pytest.fixture
def fake_renamed_pdf(tmp_path: Path) -> Path:
    """Creates a plain text file renamed with a .pdf extension."""
    pdf_path = tmp_path / "not_a_pdf.pdf"
    pdf_path.write_text("This is an image/text file pretending to be a PDF.")
    return pdf_path


@pytest.fixture
def corrupted_pdf_file(tmp_path: Path) -> Path:
    """Creates a malformed/corrupted PDF with valid prefix but invalid content."""
    pdf_path = tmp_path / "corrupted.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nInvalid broken content %%EOF truncated")
    return pdf_path


@pytest.fixture
def password_protected_pdf(tmp_path: Path) -> Path:
    """Creates a password-protected encrypted PDF."""
    pdf_path = tmp_path / "protected.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Confidential Exam Content")
    doc.save(
        str(pdf_path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secure_password",
        owner_pw="admin_password",
    )
    doc.close()
    return pdf_path


@pytest.fixture
def zero_page_pdf(tmp_path: Path) -> Path:
    """Creates a syntactically valid PDF file containing 0 pages."""
    pdf_path = tmp_path / "zero_pages.pdf"
    raw_zero_page_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog /Pages 2 0 R >>\n"
        b"endobj\n"
        b"2 0 obj\n"
        b"<< /Type /Pages /Kids [] /Count 0 >>\n"
        b"endobj\n"
        b"xref\n"
        b"0 3\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"trailer\n"
        b"<< /Size 3 /Root 1 0 R >>\n"
        b"startxref\n"
        b"115\n"
        b"%%EOF\n"
    )
    pdf_path.write_bytes(raw_zero_page_pdf)
    return pdf_path


@pytest.fixture
def rotated_pages_pdf(tmp_path: Path) -> Path:
    """Creates a multi-page PDF with different page rotations (0, 90, 180, 270)."""
    pdf_path = tmp_path / "rotated.pdf"
    doc = pymupdf.open()
    rotations = [0, 90, 180, 270]
    for rot in rotations:
        page = doc.new_page(width=600, height=800)
        page.insert_text((50, 100), f"Page with rotation {rot}")
        page.set_rotation(rot)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path



# -------------------------------------------------------------
# Module 2 Fixtures (Image Preprocessing & Enhancement)
# -------------------------------------------------------------
import cv2
import numpy as np


@pytest.fixture
def valid_png_page(tmp_path: Path) -> Path:
    """Creates a valid high-resolution PNG page image with text and math."""
    img_path = tmp_path / "page_001.png"
    img = np.full((1200, 900, 3), 255, dtype=np.uint8)
    cv2.putText(img, "TrustGrade Student Answer", (80, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 2)
    cv2.putText(img, "Question 1: Solve x^2 - 4x + 4 = 0", (80, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 30, 30), 2)
    cv2.putText(img, "Solution: (x - 2)^2 = 0 => x = 2.0", (80, 350), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (25, 25, 25), 2)
    cv2.imwrite(str(img_path), img)
    return img_path


@pytest.fixture
def valid_jpeg_page(tmp_path: Path) -> Path:
    """Creates a valid JPEG page image."""
    img_path = tmp_path / "page_001.jpg"
    img = np.full((1200, 900, 3), 250, dtype=np.uint8)
    cv2.putText(img, "Scanned Homework Solution", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 2)
    cv2.imwrite(str(img_path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return img_path


@pytest.fixture
def corrupted_image_file(tmp_path: Path) -> Path:
    """Creates a corrupted/truncated image file."""
    path = tmp_path / "corrupted.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00truncated bytes that are not a valid png")
    return path


@pytest.fixture
def unsupported_format_image(tmp_path: Path) -> Path:
    """Creates an image with unsupported format (BMP)."""
    path = tmp_path / "sample.bmp"
    img = np.full((400, 400, 3), 255, dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def very_small_image(tmp_path: Path) -> Path:
    """Creates an image that is below minimum acceptable dimensions."""
    path = tmp_path / "tiny.png"
    img = np.full((50, 50, 3), 255, dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def rotated_page_image(tmp_path: Path) -> Path:
    """Creates a page image rotated by 90 degrees."""
    path = tmp_path / "rotated_90.png"
    img = np.full((900, 1200, 3), 255, dtype=np.uint8)
    cv2.putText(img, "Sideways page content", (100, 450), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (30, 30, 30), 2)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def skewed_page_image(tmp_path: Path) -> Path:
    """Creates a page tilted by 3.5 degrees."""
    path = tmp_path / "skewed_3_5.png"
    img = np.full((1000, 800, 3), 255, dtype=np.uint8)
    for y in [200, 300, 400, 500, 600]:
        cv2.putText(img, "Sample horizontal student handwriting text line", (80, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2)
    m = cv2.getRotationMatrix2D((400, 500), 3.5, 1.0)
    tilted = cv2.warpAffine(img, m, (800, 1000), borderValue=(255, 255, 255))
    cv2.imwrite(str(path), tilted)
    return path


@pytest.fixture
def noisy_page_image(tmp_path: Path) -> Path:
    """Creates a page with synthetic scanner grain/noise."""
    path = tmp_path / "noisy.png"
    img = np.full((1000, 800, 3), 245, dtype=np.uint8)
    cv2.putText(img, "Student work with scanner grain", (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20, 20, 20), 2)
    noise = np.random.normal(0, 15, img.shape).astype(np.float32)
    noisy = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    cv2.imwrite(str(path), noisy)
    return path


@pytest.fixture
def low_contrast_page(tmp_path: Path) -> Path:
    """Creates a page with very low contrast (faint pencil handwriting)."""
    path = tmp_path / "low_contrast.png"
    img = np.full((1000, 800, 3), 240, dtype=np.uint8)
    # faint pencil writing (gray level 200 on 240 background)
    cv2.putText(img, "Faint pencil student handwriting", (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def uneven_illumination_page(tmp_path: Path) -> Path:
    """Creates a page with uneven illumination and phone shadow."""
    path = tmp_path / "shadow.png"
    img = np.full((1000, 800, 3), 255, dtype=np.uint8)
    cv2.putText(img, "Shadowed assignment page", (100, 400), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20, 20, 20), 2)
    # Add dark shadow gradient
    for x in range(800):
        factor = 1.0 - (0.4 * (x / 800.0))
        img[:, x] = np.clip(img[:, x] * factor, 0, 255).astype(np.uint8)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def blank_page_image(tmp_path: Path) -> Path:
    """Creates a blank white page."""
    path = tmp_path / "blank.png"
    img = np.full((1000, 800, 3), 255, dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def thin_strokes_page(tmp_path: Path) -> Path:
    """Creates an image with fine 1-pixel thin pen strokes and cursive loops."""
    path = tmp_path / "thin_strokes.png"
    img = np.full((1000, 800, 3), 255, dtype=np.uint8)
    # 1-pixel thickness lines and curves
    for y in range(200, 600, 100):
        cv2.line(img, (100, y), (700, y), (20, 20, 20), 1)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def math_symbols_page(tmp_path: Path) -> Path:
    """Creates an image with fine mathematical symbols, dots, and subscripts."""
    path = tmp_path / "math_symbols.png"
    img = np.full((1000, 800, 3), 255, dtype=np.uint8)
    cv2.putText(img, "f(x) = 3.14159 * x_1^2 + delta_y", (100, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 1)
    # Fine decimal point
    cv2.circle(img, (200, 350), 2, (15, 15, 15), -1)
    cv2.putText(img, "y = 0.05", (220, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 1)
    cv2.imwrite(str(path), img)
    return path


# -------------------------------------------------------------
# Module 3 Fixtures (Text & Handwriting Recognition)
# -------------------------------------------------------------
@pytest.fixture
def printed_doc_page(tmp_path: Path) -> Path:
    """Creates a page containing printed typography."""
    path = tmp_path / "printed_page.png"
    img = np.full((800, 1000, 3), 255, dtype=np.uint8)
    cv2.putText(img, "TRUSTGRADE UNIVERSITY MIDTERM EXAM", (80, 100), cv2.FONT_HERSHEY_TRIPLEX, 1.0, (15, 15, 15), 2)
    cv2.putText(img, "Question 1: Explain the law of thermodynamics.", (80, 200), cv2.FONT_HERSHEY_TRIPLEX, 0.8, (25, 25, 25), 2)
    cv2.putText(img, "Question 2: State Newton's third law of motion.", (80, 300), cv2.FONT_HERSHEY_TRIPLEX, 0.8, (25, 25, 25), 2)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def handwritten_doc_page(tmp_path: Path) -> Path:
    """Creates a page containing handwritten student text."""
    path = tmp_path / "handwritten_page.png"
    img = np.full((800, 1000, 3), 255, dtype=np.uint8)
    # Cursive / wavy handwritten student lines
    for line_idx, y_base in enumerate([150, 280, 410]):
        pts = [np.array([[80 + x * 15, y_base + int(8 * np.sin(x * 0.7))] for x in range(40)], np.int32)]
        cv2.polylines(img, pts, False, (30, 30, 30), 2)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def mixed_assignment_page(tmp_path: Path) -> Path:
    """Creates a page with printed question header and handwritten student answer."""
    path = tmp_path / "mixed_page.png"
    img = np.full((900, 1000, 3), 255, dtype=np.uint8)
    # Printed question
    cv2.putText(img, "Question 1: What is the capital of France?", (80, 120), cv2.FONT_HERSHEY_TRIPLEX, 0.9, (20, 20, 20), 2)
    # Handwritten answer
    pts = [np.array([[80 + x * 18, 260 + int(6 * np.sin(x * 0.6))] for x in range(30)], np.int32)]
    cv2.polylines(img, pts, False, (35, 35, 35), 2)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def multi_column_assignment_page(tmp_path: Path) -> Path:
    """Creates a 2-column layout assignment page."""
    path = tmp_path / "multi_col.png"
    img = np.full((900, 1000, 3), 255, dtype=np.uint8)
    # Spanning header
    cv2.putText(img, "PHYSICS FINAL EXAM - SECTION A & B", (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20, 20, 20), 2)
    # Column 1 (Left: x in [50, 420])
    cv2.putText(img, "Col 1 Line 1: Left column entry", (60, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)
    cv2.putText(img, "Col 1 Line 2: Second left row", (60, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)
    # Column 2 (Right: x in [540, 920])
    cv2.putText(img, "Col 2 Line 1: Right column entry", (550, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)
    cv2.putText(img, "Col 2 Line 2: Second right row", (550, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def math_assignment_page(tmp_path: Path) -> Path:
    """Creates an assignment page with mathematical equations and symbols."""
    path = tmp_path / "math_page.png"
    img = np.full((800, 1000, 3), 255, dtype=np.uint8)
    cv2.putText(img, "Integral Solution: f(x) = x_1^2 + 3.1415", (80, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2)
    cv2.putText(img, "Summation: sum_{i=1}^n x_i = 100", (80, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def faint_handwriting_page(tmp_path: Path) -> Path:
    """Creates a page with faint low-contrast handwriting."""
    path = tmp_path / "faint_page.png"
    img = np.full((800, 1000, 3), 245, dtype=np.uint8)
    # Faint text (215 on 245)
    cv2.putText(img, "Faint student answer text", (80, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (215, 215, 215), 1)
    cv2.imwrite(str(path), img)
    return path
