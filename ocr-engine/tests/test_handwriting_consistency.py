"""Within-submission handwriting consistency check (teacher review signal).

Synthetic "writers" = distinct font + slant + stroke weight, with small per-line jitter.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.handwriting.consistency import MIN_LINES_PER_SEGMENT, analyze, collect_lines

SENTENCES = [
    "the stupa has a large hemispherical dome",
    "relics of the buddha are kept inside it",
    "four carved gateways face each direction",
    "the carvings tell stories from his life",
    "a railing and umbrella sit on the top",
    "pilgrims walk around the dome in prayer",
    "the site was protected as world heritage",
    "monks lived in monasteries on the hill",
]

WRITERS = {
    "upright": dict(font=cv2.FONT_HERSHEY_SIMPLEX, slant=0.0, thickness=2, scale=1.0),
    "slanted": dict(font=cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, slant=-0.45, thickness=1, scale=1.3),
}


def _line_image(text, writer, rng):
    w = WRITERS[writer]
    scale = w["scale"] * (1 + rng.uniform(-0.05, 0.05))
    img = np.full((70, 900, 3), 255, np.uint8)
    cv2.putText(img, text, (20, 50), w["font"], scale, (40, 40, 40), w["thickness"], cv2.LINE_AA)
    shear = np.float32([[1, w["slant"], -w["slant"] * 35], [0, 1, 0]])
    return cv2.warpAffine(img, shear, (900, 70), borderValue=(255, 255, 255))


def _page(number, writer, n_lines, seed, header=None, numbered_from=None):
    rng = np.random.default_rng(seed)
    rows, blocks, y = [], [], 0
    texts = [header] if header else []
    # Unique per page: identical lines on several pages are treated as a printed letterhead and skipped.
    texts += [f"{SENTENCES[(seed + i) % len(SENTENCES)]} page {number} line {i}" for i in range(n_lines)]
    if numbered_from is not None:
        texts[1 if header else 0] = f"{numbered_from}. {texts[1 if header else 0]}"
    for i, text in enumerate(texts):
        line = _line_image(text, "upright" if (header and i == 0) else writer, rng)
        rows.append(line)
        blocks.append({"text": text, "bbox": (0, y, 900, y + 70)})
        y += 70
    return {"page_number": number, "image": np.vstack(rows), "blocks": blocks}


def test_same_writer_is_consistent():
    pages = [_page(1, "slanted", 8, 1), _page(2, "slanted", 8, 2), _page(3, "slanted", 8, 3)]
    result = analyze(pages)
    assert result["status"] == "consistent", result["segments"]
    assert result["flagged"] == []


def test_page_by_another_writer_is_flagged_with_samples():
    pages = [_page(1, "slanted", 8, 1), _page(2, "slanted", 8, 2), _page(3, "upright", 8, 3)]
    result = analyze(pages)
    assert result["status"] == "possible_different_handwriting"
    flagged = result["flagged"]
    assert any(3 in f["page_numbers"] for f in flagged)
    first = flagged[0]
    assert first["samples"][0]["image"].startswith("data:image/png;base64,")
    assert first["reference_samples"] and first["difference_score"] >= result["threshold"]
    assert "not evidence of misconduct" in result["limitations"]


def test_two_parts_are_reported_together_not_guessed():
    result = analyze([_page(1, "slanted", 8, 1), _page(2, "upright", 8, 2)])
    assert result["status"] == "possible_different_handwriting"
    assert len(result["flagged"]) == 1
    assert "look written by different hands" in result["flagged"][0]["label"]
    assert result["flagged"][0]["page_numbers"] == [1, 2]


def test_too_little_handwriting_is_not_guessed():
    lines = MIN_LINES_PER_SEGMENT - 1
    result = analyze([_page(1, "slanted", lines, 1), _page(2, "upright", lines, 2)])
    assert result["status"] == "insufficient_handwriting"
    assert result["flagged"] == []


def test_repeated_printed_letterhead_and_numeric_lines_are_ignored():
    header = "Lakshmi Narain College of Technology Bhopal"
    pages = [_page(n, "slanted", 7, n, header=header) for n in (1, 2)]
    pages[0]["blocks"].append({"text": "2 53 1 0.625x2=1.25", "bbox": (0, 0, 900, 70)})
    texts = [line.text for line in collect_lines(pages)]
    assert header not in texts
    assert all(any(c.isalpha() for c in t) for t in texts) and "2 53 1 0.625x2=1.25" not in texts
    assert analyze(pages)["status"] == "consistent"


def test_endpoint_analyses_stored_job_and_caches(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.app import create_app
    from app.api.config import APIConfig
    from app.jobs.job_manager import JobManager

    JobManager.reset_instance()
    storage = tmp_path / "storage"
    job_id = "job-" + "ab" * 16
    job_dir = storage / job_id
    enhanced = job_dir / "artifacts" / "sub-1" / "enhanced"
    enhanced.mkdir(parents=True)
    pages = [_page(1, "slanted", 8, 1), _page(2, "slanted", 8, 2), _page(3, "upright", 8, 3)]
    result_pages = []
    for page in pages:
        cv2.imwrite(str(enhanced / f"page_{page['page_number']:03d}.png"), page["image"])
        h, w = page["image"].shape[:2]
        result_pages.append({
            "page_id": f"p{page['page_number']}", "page_number": page["page_number"], "width": w, "height": h,
            "full_text": "\n".join(b["text"] for b in page["blocks"]),
            "text_blocks": [
                {"block_id": f"b{i}", "sequence": i + 1, "type": "handwritten", "text": b["text"],
                 "bounding_box": dict(zip(("x1", "y1", "x2", "y2"), b["bbox"]))}
                for i, b in enumerate(page["blocks"])
            ],
        })
    (job_dir / "submission.pdf").write_bytes(b"%PDF-1.4")
    (job_dir / "result.json").write_text(json.dumps({"job_id": job_id, "submission_id": "sub-1",
                                                     "status": "completed", "pages": result_pages}))
    (job_dir / "job.json").write_text(json.dumps({"job_id": job_id, "submission_id": "sub-1", "status": "completed",
                                                  "stage": "done", "progress": 100}))
    JobManager.get_instance(APIConfig(storage_root=str(storage)))
    client = TestClient(create_app())

    response = client.get(f"/api/v1/ocr/handwriting/{job_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "possible_different_handwriting"
    assert any(3 in f["page_numbers"] for f in body["flagged"])
    assert (job_dir / "handwriting.json").is_file()
    assert client.get("/api/v1/ocr/handwriting/job-" + "0" * 32).status_code == 404
    JobManager.reset_instance()
