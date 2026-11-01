"""Whole-sheet copy detection: the shingle comparison itself, the review queue's "copying" list, and the
copy flag on a submission's integrity report."""

from uuid import uuid4

from app.schemas.ocr import OCRDocumentResult
from app.services.copy_detection import COPY_FLAG_OVERLAP, find_copies, similarity_to_others
from tests.test_review_service import TEACHER, TOKEN, _assignment, _run, _service, _submission

QUESTION = "Explain the architecture and the purpose of the Great Stupa at Sanchi and its gateways."

ANSWER_A = """Q1
The Great Stupa at Sanchi was built by Emperor Ashoka in the third century BCE to house relics of the Buddha.
It is a large hemispherical dome called the anda surrounded by a railing and four carved gateways called toranas.
Pilgrims walk around it clockwise on the circular path known as pradakshina patha while they meditate."""

# Same work with OCR-ish noise: different case, punctuation, a page header and a word dropped.
ANSWER_A_COPY = """[Page 1]
Q1
the great stupa at sanchi was built by emperor ashoka in the third century BCE to house relics of the buddha
it is a large hemispherical dome called the anda surrounded by a railing and four carved gateways called toranas
pilgrims walk around it clockwise on the circular path known as pradakshina patha while they meditate"""

ANSWER_B = """Q1
Sanchi is in Madhya Pradesh. The monument there is a stone mound whose shape stands for the cosmic mountain.
Its gateways show scenes from the Jataka tales, carved by ivory workers of nearby Vidisha.
Later rulers such as the Satavahanas added the gateways and kept repairing the site for centuries."""


def test_identical_answer_sheets_are_flagged_despite_ocr_noise():
    matches = find_copies({"a": ANSWER_A, "copy": ANSWER_A_COPY, "b": ANSWER_B}, [QUESTION])
    assert [(m.first, m.second) for m in matches] == [("a", "copy")]
    assert matches[0].overlap >= 0.9


def test_different_answers_to_the_same_question_are_not_flagged():
    assert find_copies({"a": ANSWER_A, "b": ANSWER_B}, [QUESTION]) == []


def test_copying_the_question_text_is_not_copying():
    # Both students wrote the question out, then gave different answers.
    a = f"{QUESTION}\n{ANSWER_A}"
    b = f"{QUESTION}\n{ANSWER_B}"
    assert find_copies({"a": a, "b": b}, [QUESTION]) == []
    # Without the question text excluded, the shared question would count toward the overlap.
    assert similarity_to_others("a", {"a": a, "b": b})["b"] > similarity_to_others("a", {"a": a, "b": b}, [QUESTION])["b"]


def test_copying_part_of_a_longer_sheet_into_a_short_one_is_caught():
    short_copy = "\n".join(ANSWER_A.splitlines()[:3])  # only the first two answer lines
    matches = find_copies({"long": ANSWER_A + "\n" + ANSWER_B, "short": short_copy}, [QUESTION])
    assert len(matches) == 1 and matches[0].overlap == 1.0


def test_very_short_sheets_are_not_judged():
    assert similarity_to_others("a", {"a": "Torana is a temple", "b": "Torana is a temple"}) == {}


def test_boilerplate_most_of_the_class_wrote_is_ignored():
    header = "Name of the student roll number class section subject history date of submission"
    texts = {f"s{i}": f"{header}\n{answer}" for i, answer in enumerate([ANSWER_A, ANSWER_B, ANSWER_B[::-1], "x " * 40])}
    assert find_copies(texts, [QUESTION]) == []


def test_threshold_is_the_documented_default():
    assert COPY_FLAG_OVERLAP == 0.6


# ---- review queue + integrity report ---------------------------------------------------------


def _doc(job_id: str, text: str) -> OCRDocumentResult:
    return OCRDocumentResult.model_validate(
        {
            "job_id": job_id, "submission_id": "s", "status": "completed",
            "processing_summary": {"total_pages": 1, "processed_pages": 1, "failed_pages": 0,
                                   "total_processing_time_ms": 1.0},
            "pages": [{"page_id": "p1", "page_number": 1, "width": 10, "height": 10, "full_text": text,
                       "text_blocks": [], "math_blocks": []}],
        }
    )


def _class_of_three():
    assignment = _assignment()
    original = _submission(assignment.id, job="job-a")
    copy = _submission(assignment.id, job="job-copy")
    honest = _submission(assignment.id, job="job-b")
    ocr = {"job-a": _doc("job-a", ANSWER_A), "job-copy": _doc("job-copy", ANSWER_A_COPY), "job-b": _doc("job-b", ANSWER_B)}
    return assignment, original, copy, honest, ocr


def test_review_queue_lists_both_students_of_a_copied_pair_only():
    assignment, original, copy, honest, ocr = _class_of_three()
    service, _ = _service(assignment, [original, copy, honest], ocr=ocr)

    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))

    flagged = {item.submission_id: item for item in queue.copying}
    assert set(flagged) == {original.id, copy.id}
    assert flagged[original.id].matched_submission_id == copy.id
    assert flagged[copy.id].matched_student_id == original.student_id
    assert all(item.category == "copying" and item.match_overlap >= 0.9 for item in queue.copying)
    assert "cannot tell who copied" in " ".join(flagged[copy.id].reasons)
    assert queue.thresholds.copy_overlap == COPY_FLAG_OVERLAP


def test_review_queue_skips_unreadable_submissions_and_says_so():
    assignment, original, copy, honest, ocr = _class_of_three()
    ocr["job-copy"] = RuntimeError("OCR engine down")
    service, _ = _service(assignment, [original, copy, honest], ocr=ocr)

    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))

    assert queue.copying == []
    assert any("could not be checked for copying" in note for note in queue.notes)


def test_integrity_report_flags_the_copy_and_names_the_matching_submission():
    assignment, original, copy, honest, ocr = _class_of_three()
    service, _ = _service(assignment, [original, copy, honest], ocr=ocr)
    service.submissions.ocr_client = service.ocr_client  # the shared fake also serves integrity checks

    report = _run(service.submissions.analyze_submission_integrity(TEACHER, copy.id, access_token=TOKEN))

    assert report.copy_flag is True and report.review_status == "needs_teacher_review"
    top = report.similar_submissions[0]
    assert top.submission_id == original.id and top.student_id == original.student_id and top.likely_copy
    assert all(item.submission_id != honest.id or not item.likely_copy for item in report.similar_submissions)
    assert report.notes[0].startswith("Possible copying")


def test_integrity_report_for_honest_work_has_no_copy_flag():
    assignment, original, copy, honest, ocr = _class_of_three()
    service, _ = _service(assignment, [original, copy, honest], ocr=ocr)
    service.submissions.ocr_client = service.ocr_client  # the shared fake also serves integrity checks

    report = _run(service.submissions.analyze_submission_integrity(TEACHER, honest.id, access_token=TOKEN))

    assert report.copy_flag is False
    assert not any(item.likely_copy for item in report.similar_submissions)


# ---- exact same PDF file (SHA-256) ------------------------------------------------------------

from app.services.copy_detection import identical_files  # noqa: E402
from tests.test_review_service import FakeOCR  # noqa: E402


class HashingOCR(FakeOCR):
    def __init__(self, results, hashes):
        super().__init__(results)
        self.hashes = hashes

    async def get_file_hash(self, job_id):
        return self.hashes.get(job_id)


def test_identical_files_pairs_only_different_students():
    hashes = {"a": "h1", "b": "h1", "c": "h2", "d": "h1"}
    owners = {"a": "asha", "b": "bilal", "c": "chen", "d": "asha"}  # d = asha's own re-upload
    assert sorted(map(sorted, identical_files(hashes, owners))) == [["a", "b"], ["b", "d"]]


def _same_file_class(text_a: str, text_b: str):
    assignment = _assignment()
    first = _submission(assignment.id, job="job-1")
    second = _submission(assignment.id, job="job-2")
    other = _submission(assignment.id, job="job-3")
    ocr = HashingOCR(
        {"job-1": _doc("job-1", text_a), "job-2": _doc("job-2", text_b), "job-3": _doc("job-3", ANSWER_B)},
        {"job-1": "f" * 64, "job-2": "f" * 64, "job-3": "e" * 64},
    )
    service, _ = _service(assignment, [first, second, other])
    service.ocr_client = ocr
    service.submissions.ocr_client = ocr
    return service, first, second, other


def test_same_pdf_from_two_students_is_flagged_even_without_ocr_text():
    service, first, second, other = _same_file_class("", "")  # OCR read nothing from either

    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))

    flagged = {item.submission_id: item for item in queue.copying}
    assert set(flagged) == {first.id, second.id}
    assert all(item.identical_file and item.match_overlap == 1.0 for item in flagged.values())
    assert "same PDF file" in flagged[first.id].reasons[0]


def test_same_pdf_is_reported_once_not_also_as_a_text_match():
    service, first, second, other = _same_file_class(ANSWER_A, ANSWER_A)

    queue = _run(service.build_queue(TEACHER, access_token=TOKEN))

    assert len(queue.copying) == 2 and all(item.identical_file for item in queue.copying)


def test_integrity_report_says_identical_file():
    service, first, second, other = _same_file_class("", "")

    report = _run(service.submissions.analyze_submission_integrity(TEACHER, second.id, access_token=TOKEN))

    assert report.copy_flag
    top = report.similar_submissions[0]
    assert top.submission_id == first.id and top.identical_file and top.likely_copy
    assert "same PDF file" in report.notes[0]
