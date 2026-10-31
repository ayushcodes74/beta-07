from uuid import uuid4

from app.schemas.ocr import OCRDocumentResult, PageResult, ProcessingSummary, TextBlock, BoundingBox
from app.services.plagiarism import compare_ocr_documents, summarize_ocr


def _document(
    text: str,
    *,
    confidence: float | None = 0.96,
    total_pages: int = 1,
    block_type: str = "handwritten",
) -> OCRDocumentResult:
    page = PageResult(
        page_id="page-1",
        page_number=1,
        width=800,
        height=1000,
        text_blocks=[
            TextBlock(
                block_id="region-1",
                sequence=1,
                type=block_type,
                text=text,
                confidence=confidence,
                bounding_box=BoundingBox(x1=10, y1=20, x2=700, y2=80),
            )
        ],
        full_text=text,
    )
    return OCRDocumentResult(
        job_id="job",
        submission_id="submission",
        processing_summary=ProcessingSummary(
            total_pages=total_pages,
            processed_pages=1,
            total_processing_time_ms=10,
        ),
        pages=[page],
    )


def test_identical_passage_matches_across_spacing_and_line_breaks():
    current = _document(
        "Cells convert glucose into usable energy through cellular respiration "
        "within the mitochondria of the cell."
    )
    source = _document(
        "Cells convert glucose into usable energy\nthrough cellular respiration "
        "within the mitochondria of the cell."
    )

    evidence, _ = compare_ocr_documents(uuid4(), current, uuid4(), source)

    assert len(evidence) == 1
    assert evidence[0].exact_match_score == 1.0
    assert evidence[0].current_regions[0].region_id == "region-1"
    assert evidence[0].source_regions[0].page_number == 1
    assert evidence[0].semantic_similarity_score is None


def test_near_identical_passage_reports_token_similarity_not_verdict():
    current = _document(
        "Cells convert glucose into usable energy through cellular respiration "
        "within the mitochondria of the cell."
    )
    source = _document(
        "Cells convert glucose into usable energy through cellular respiration "
        "inside the mitochondria of the cell."
    )

    evidence, _ = compare_ocr_documents(uuid4(), current, uuid4(), source)

    assert evidence
    assert 0.8 <= evidence[0].exact_match_score < 1.0
    assert "review signal" in (evidence[0].context_note or "").lower() or evidence[0].context_note is None


def test_generic_definition_template_is_not_returned_as_match():
    definition = "A term is defined as the process by which a term is defined."

    evidence, _ = compare_ocr_documents(uuid4(), _document(definition), uuid4(), _document(definition))

    assert evidence == []


def test_repeated_printed_question_text_is_not_counted_as_answer_evidence():
    prompt = "Explain how cellular respiration produces usable energy inside living organisms."

    evidence, _ = compare_ocr_documents(
        uuid4(),
        _document(prompt, block_type="printed"),
        uuid4(),
        _document(prompt, block_type="printed"),
    )

    assert evidence == []


def test_low_confidence_match_is_marked_uncertain_and_keeps_source_text():
    text = "Cells convert glucose into usable energy through cellular respiration within mitochondria."

    evidence, quality = compare_ocr_documents(
        uuid4(),
        _document(text, confidence=0.4),
        uuid4(),
        _document(text, confidence=0.96),
    )

    assert evidence
    assert evidence[0].ocr_uncertain is True
    assert quality.low_confidence_regions[0].original_text == text


def test_missing_ocr_confidence_is_not_reported_as_certain():
    text = "Cells convert glucose into usable energy through cellular respiration within mitochondria."

    evidence, quality = compare_ocr_documents(
        uuid4(),
        _document(text, confidence=None),
        uuid4(),
        _document(text, confidence=0.96),
    )

    assert evidence[0].ocr_uncertain is True
    assert quality.mean_confidence is None
    assert quality.low_confidence_regions[0].confidence is None


def test_missing_pages_are_reported_without_inventing_text():
    quality = summarize_ocr(_document("Readable page content.", total_pages=2))

    assert quality.missing_pages == [2]
    assert quality.mean_confidence == 0.96
