"""Strict audit benchmark script comparing actual engine output against ground truth."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from app.recognition import recognize_page
from scripts.evaluate_recognition import compute_cer, compute_wer

samples = [
    ("Clear Print", "Question 1: Explain the principle of conservation of energy.", True),
    ("Clear Script", "Energy cannot be created or destroyed, only transformed from one form to another.", False),
    ("Cursive Script", "The kinetic energy of the pendulum reaches its maximum at the lowest point of the swing.", False),
    ("Faint Script", "Frictional losses cause gradual dissipation of mechanical energy into thermal energy.", False),
    ("Math & Text", "The total energy E = K + U = 0.5 * m * v^2 + m * g * h remains constant.", False),
]

def run_audit():
    print("=" * 85)
    print("AUDIT BENCHMARK: CPU Heuristic Fallback Engine on Ground Truth Sentences")
    print("=" * 85)

    total_cer, total_wer, total_time = 0.0, 0.0, 0.0
    out_dir = Path("ocr-engine/benchmark_samples")
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, ref_text, is_print in samples:
        img = np.full((300, 900, 3), 255, dtype=np.uint8)
        font = cv2.FONT_HERSHEY_TRIPLEX if is_print else cv2.FONT_HERSHEY_SIMPLEX
        color = (25, 25, 25) if "Faint" not in name else (210, 210, 210)
        cv2.putText(img, ref_text[:45], (40, 100), font, 0.7, color, 2 if is_print else 1)
        if len(ref_text) > 45:
            cv2.putText(img, ref_text[45:], (40, 180), font, 0.7, color, 2 if is_print else 1)

        safe_name = name.lower().replace(" ", "_").replace("&", "and")
        test_path = out_dir / f"audit_{safe_name}.png"
        cv2.imwrite(str(test_path), img)

        t0 = time.time()
        res = recognize_page(str(test_path), "audit-sub", 1)
        elapsed = (time.time() - t0) * 1000.0

        hyp_text = res.full_text
        cer = compute_cer(ref_text, hyp_text)
        wer = compute_wer(ref_text, hyp_text)

        total_cer += cer
        total_wer += wer
        total_time += elapsed

        print(f"{name:<15} | Time: {elapsed:5.1f}ms | CER: {cer:6.2%} | WER: {wer:6.2%}")
        print(f"  Reference : {ref_text}")
        print(f"  Hypothesis: {hyp_text}")
        print("-" * 85)

    n = len(samples)
    print(f"Mean Latency : {total_time / n:.1f} ms")
    print(f"Mean CER     : {total_cer / n:.2%}")
    print(f"Mean WER     : {total_wer / n:.2%}")
    print("=" * 85)

if __name__ == "__main__":
    run_audit()

