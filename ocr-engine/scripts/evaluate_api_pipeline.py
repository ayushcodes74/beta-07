"""Evaluation and benchmarking script for Module 5 OCR API and Orchestration pipeline."""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add ocr-engine to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
import pymupdf

from app.api.app import create_app
from app.api.schemas import HealthResponse, OCRDocumentResult
from app.jobs.job_manager import JobManager
from app.orchestration.ocr_orchestrator import OCROrchestrator

logger = logging.getLogger("evaluate_api_pipeline")


def create_benchmark_pdf(path: Path, pages: int = 2) -> Path:
    """Generate a valid multi-page PDF with printed text and mathematical notation."""
    doc = pymupdf.open()
    for p_idx in range(1, pages + 1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 100), f"TrustGrade Academic Examination - Page {p_idx}", fontsize=14)
        page.insert_text((50, 180), f"Question {p_idx}: Derive the equation of motion.", fontsize=11)
        page.insert_text((50, 260), "Student Answer: v^2 = u^2 + 2 * a * s", fontsize=11)
        page.insert_text((50, 340), "Integral Expression: int x^2 dx = x^3 / 3 + C", fontsize=11)
    doc.save(str(path))
    doc.close()
    return path


def run_api_pipeline_evaluation() -> None:
    """Run comprehensive API and orchestration pipeline benchmarks."""
    print("=" * 95)
    print("TrustGrade OCR Module 5 — API & Orchestration Pipeline Evaluation")
    print("=" * 95)

    app = create_app()
    client = TestClient(app)

    # 1. Health Audit
    print("\n--- 1. API Health & Model Readiness Audit ---")
    t0 = time.time()
    h_resp = client.get("/health")
    h_lat = (time.time() - t0) * 1000.0
    assert h_resp.status_code == 200
    health_data = h_resp.json()
    print(f"Health Endpoint Latency : {h_lat:.2f} ms")
    print(f"Service Operational     : {health_data['service_available']} (Status: {health_data['status']})")
    print(f"Modules Availability    : {health_data['modules']}")
    print(f"DL Models Readiness     : {health_data['models']}")

    # 2. End-to-End Synchronous Job Processing
    print("\n--- 2. End-to-End PDF Orchestration Benchmark ---")
    work_dir = Path("ocr-engine/benchmark_samples")
    work_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = create_benchmark_pdf(work_dir / "bench_api_sample.pdf", pages=2)

    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    t_sub_start = time.time()
    sub_resp = client.post(
        "/api/v1/ocr/process",
        data={"submission_id": "bench-api-sub", "run_async": "false"},
        files={"file": ("bench_api_sample.pdf", file_bytes, "application/pdf")},
    )
    sub_lat = (time.time() - t_sub_start) * 1000.0
    assert sub_resp.status_code == 202
    job_id = sub_resp.json()["job_id"]
    print(f"Job Submission Latency  : {sub_lat:.1f} ms (Job ID: {job_id})")

    # Retrieve Result
    t_res_start = time.time()
    res_resp = client.get(f"/api/v1/ocr/result/{job_id}")
    res_lat = (time.time() - t_res_start) * 1000.0
    assert res_resp.status_code == 200
    result_data = res_resp.json()

    print(f"Result Retrieval Latency: {res_lat:.1f} ms")
    print(f"Final Job Status        : {result_data['status']}")
    print(f"Pages Processed         : {result_data['processing_summary']['processed_pages']} / {result_data['processing_summary']['total_pages']}")
    print(f"Total Pipeline Duration : {result_data['processing_summary']['total_processing_time_ms']:.1f} ms")
    print("Stage Duration Breakdown:")
    for stage, dur in result_data["processing_summary"]["stage_durations_ms"].items():
        print(f"  - {stage:<18}: {dur:6.1f} ms")

    # 3. Security Boundary Validation
    print("\n--- 3. Upload Security Boundary Verification ---")
    # Empty file
    r_empty = client.post("/api/v1/ocr/process", files={"file": ("empty.pdf", b"", "application/pdf")})
    print(f"Empty File Rejection    : HTTP {r_empty.status_code} ({r_empty.json().get('detail') or r_empty.json().get('message')})")
    assert r_empty.status_code == 400

    # Wrong extension
    r_ext = client.post("/api/v1/ocr/process", files={"file": ("test.png", b"fake image bytes", "image/png")})
    print(f"Invalid Ext Rejection   : HTTP {r_ext.status_code}")
    assert r_ext.status_code == 400

    # Invalid header magic bytes
    r_magic = client.post("/api/v1/ocr/process", files={"file": ("test.pdf", b"NOT_A_PDF_HEADER", "application/pdf")})
    print(f"Invalid Magic Bytes     : HTTP {r_magic.status_code}")
    assert r_magic.status_code == 400

    print("=" * 95)
    print("Module 5 API & Orchestration Pipeline Verification: ALL CHECKS PASSED")
    print("=" * 95)


if __name__ == "__main__":
    run_api_pipeline_evaluation()

