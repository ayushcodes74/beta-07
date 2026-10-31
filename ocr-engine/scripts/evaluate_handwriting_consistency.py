"""Evaluate the within-submission handwriting consistency check on your own data.

Give it OCR job folders (ocr-engine/storage/job-*) that are each written by ONE person (one writer per
folder, different folders = different writers, or say so with --same-writer-groups). It reports:

  * false positives: each single-writer submission analysed alone (any flag is wrong)
  * detection: each submission with ONE page from a different writer spliced in (should be flagged)

This is a sanity check, not a validation study: use many consented writers before trusting the numbers.

Usage (from ocr-engine/):
    python scripts/evaluate_handwriting_consistency.py storage/job-a storage/job-b ...
    python scripts/evaluate_handwriting_consistency.py --all          # every job in storage/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.handwriting.consistency import analyze  # noqa: E402
from app.handwriting.job_loader import load_job_pages  # noqa: E402


def _fingerprint(job: Path) -> str:
    result = json.loads((job / "result.json").read_text(encoding="utf-8"))
    text = "\n".join(p.get("full_text", "") for p in result.get("pages", []))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("jobs", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="use every job folder with a result.json in storage/")
    args = parser.parse_args()

    jobs = args.jobs
    if args.all:
        jobs = sorted((Path(__file__).resolve().parents[1] / "storage").glob("job-*"))
    jobs = [j for j in jobs if (j / "result.json").is_file()]

    unique, seen = [], set()
    for job in jobs:
        fp = _fingerprint(job)
        if fp not in seen:  # the same PDF uploaded twice is one writer, not two
            seen.add(fp)
            unique.append(job)
    if len(unique) < 1:
        sys.exit("No job folders with result.json found.")
    writers = {job.name: load_job_pages(job) for job in unique}
    print(f"{len(jobs)} job folder(s), {len(writers)} distinct submission(s) treated as distinct writers\n")

    print("== Single-writer submissions (a flag here is a FALSE POSITIVE)")
    false_pos = analysed = 0
    for name, pages in writers.items():
        result = analyze(pages)
        if result["status"] == "insufficient_handwriting":
            print(f"  {name}: insufficient handwriting ({result['lines_analyzed']} lines) - not counted")
            continue
        analysed += 1
        flagged = [f["label"] for f in result["flagged"]]
        false_pos += bool(flagged)
        print(f"  {name}: {result['status']}  flagged={flagged}")

    print("\n== One page from another writer spliced in (should be FLAGGED)")
    detected = trials = 0
    for host, host_pages in writers.items():
        for donor, donor_pages in writers.items():
            if host == donor or not host_pages or not donor_pages:
                continue
            donor_page = max(donor_pages, key=lambda p: len(p["blocks"]))
            spliced_number = max(p["page_number"] for p in host_pages) + 1
            result = analyze([*host_pages, {**donor_page, "page_number": spliced_number}])
            if result["status"] == "insufficient_handwriting":
                continue
            trials += 1
            hit = any(spliced_number in f["page_numbers"] for f in result["flagged"])
            detected += hit
            print(f"  {host} + page of {donor}: {'DETECTED' if hit else 'missed'}  flagged={[f['label'] for f in result['flagged']]}")

    print("\n== Summary")
    print(f"  false-positive submissions: {false_pos}/{analysed}")
    print(f"  spliced pages detected:     {detected}/{trials}")
    if len(writers) < 10:
        print("  NOTE: far too few writers for reliable rates; this only shows the check is not obviously broken.")


if __name__ == "__main__":
    main()
