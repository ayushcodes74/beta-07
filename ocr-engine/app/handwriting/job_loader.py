"""Build handwriting-analysis input from a stored OCR job workspace (result.json + page images)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2


def _page_image(job_dir: Path, page: Dict[str, Any]) -> Optional[Any]:
    number = int(page["page_number"])
    candidates = []
    for key in ("enhanced_image_path", "image_path"):
        if page.get(key):
            path = Path(page[key])
            candidates += [path, job_dir / path, job_dir.parent.parent / path]
    candidates += sorted(job_dir.glob(f"artifacts/*/enhanced/page_{number:03d}.png"))
    candidates += sorted(job_dir.glob(f"artifacts/*/pages/page_{number:03d}.png"))
    for path in candidates:
        if path.is_file():
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None:
                return image
    return None


def pages_from_result(job_dir: Path, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """[{page_number, image, blocks:[{text, bbox}]}] in page/reading order; pages without images are skipped."""
    pages = []
    for page in sorted(result.get("pages", []), key=lambda p: p["page_number"]):
        image = _page_image(job_dir, page)
        if image is None:
            continue
        blocks = []
        for block in sorted(page.get("text_blocks", []), key=lambda b: b.get("sequence", 0)):
            box = block.get("bounding_box") or {}
            if not box:
                continue
            blocks.append({"text": block.get("text", ""), "bbox": (box["x1"], box["y1"], box["x2"], box["y2"])})
        pages.append({"page_number": int(page["page_number"]), "image": image, "blocks": blocks})
    return pages


def load_job_pages(job_dir: Path) -> List[Dict[str, Any]]:
    result = json.loads((Path(job_dir) / "result.json").read_text(encoding="utf-8"))
    return pages_from_result(Path(job_dir), result)
