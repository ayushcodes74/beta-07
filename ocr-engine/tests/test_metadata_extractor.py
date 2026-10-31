"""Tests for MetadataExtractor."""

from pathlib import Path
import pymupdf

from app.ingestion.metadata_extractor import MetadataExtractor


def test_extract_document_metadata_present(sample_single_page_pdf: Path):
    doc = pymupdf.open(str(sample_single_page_pdf))
    try:
        meta = MetadataExtractor.extract_document_metadata(doc)
        assert meta.title == "Assignment 1"
        assert meta.author == "Student 101"
        assert meta.subject == "Mathematics"
    finally:
        doc.close()


def test_extract_document_metadata_empty(tmp_path: Path):
    pdf_path = tmp_path / "no_meta.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    doc = pymupdf.open(str(pdf_path))
    try:
        meta = MetadataExtractor.extract_document_metadata(doc)
        assert meta.title is None
        assert meta.author is None
    finally:
        doc.close()


def test_extract_page_dimensions_and_rotation(rotated_pages_pdf: Path):
    doc = pymupdf.open(str(rotated_pages_pdf))
    try:
        expected_rotations = [0, 90, 180, 270]
        assert doc.page_count == 4
        for i, expected_rot in enumerate(expected_rotations):
            page = doc.load_page(i)
            width, height, rot = MetadataExtractor.extract_page_dimensions(page)
            assert rot == expected_rot
            if expected_rot in (0, 180):
                assert width == 600.0
                assert height == 800.0
            else:
                assert width == 800.0
                assert height == 600.0
    finally:
        doc.close()

