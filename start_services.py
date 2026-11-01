"""
Supervisor script to run and monitor all TrustGrade services:
- Backend: port 8000
- OCR Engine: port 8001
- AI Engine: port 8002
- Frontend: port 5173
"""
import os
import signal
import subprocess
import sys
import time

PYTHON = r"C:\beta-07\.venv\Scripts\python.exe"
NPX = r"C:\Program Files\nodejs\npx.cmd"
LOGS_DIR = r"C:\beta-07\logs"

SERVICES = [
    {
        "name": "backend",
        "cmd": [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        "cwd": r"C:\beta-07\backend",
        "port": 8000,
    },
    {
        "name": "ocr-engine",
        "cmd": [PYTHON, "-m", "uvicorn", "app.api.app:app", "--host", "127.0.0.1", "--port", "8001"],
        "cwd": r"C:\beta-07\ocr-engine",
        "port": 8001,
    },
    {
        "name": "ai-engine",
        "cmd": [PYTHON, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", "8002"],
        "cwd": r"C:\beta-07\ai-engine",
        "port": 8002,
    },
    {
        "name": "frontend",
        "cmd": [NPX, "vite", "--port", "5173", "--strictPort"],
        "cwd": r"C:\beta-07\frontend",
        "port": 5173,
    },
]

running_procs = {}
log_files = {}


def start_service(svc):
    name = svc["name"]
    log_path = os.path.join(LOGS_DIR, f"{name}.log")
    f = open(log_path, "a", encoding="utf-8", buffering=1)
    log_files[name] = f
    f.write(f"\n--- Starting {name} at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    f.flush()
    proc = subprocess.Popen(
        svc["cmd"],
        cwd=svc["cwd"],
        stdout=f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )
    running_procs[name] = (proc, svc)
    print(f"[{name}] Started with PID {proc.pid}", flush=True)


def cleanup(*args):
    print("\nShutting down all services...", flush=True)
    for name, (proc, _) in running_procs.items():
        try:
            print(f"[{name}] Terminating PID {proc.pid}", flush=True)
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    for f in log_files.values():
        try:
            f.close()
        except Exception:
            pass
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)


def main():
    os.makedirs(LOGS_DIR, exist_ok=True)
    for svc in SERVICES:
        start_service(svc)

    print("All services launched. Monitoring...", flush=True)
    while True:
        time.sleep(2)
        for name, (proc, svc) in list(running_procs.items()):
            ret = proc.poll()
            if ret is not None:
                print(f"[{name}] Process exited with code {ret}. Restarting...", flush=True)
                start_service(svc)


if __name__ == "__main__":
    main()

