"""
main.py — project root launcher
Starts the FastAPI backend and Vite frontend in parallel.
Press Ctrl+C to stop both.
"""
import os
import sys
import signal
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

# Python interpreter inside the backend venv
if sys.platform == "win32":
    VENV_PYTHON = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
else:
    VENV_PYTHON = BACKEND_DIR / "venv" / "bin" / "python"

if not VENV_PYTHON.exists():
    sys.exit(
        f"[ERROR] venv not found at {VENV_PYTHON}\n"
        "Run:  python -m venv backend/venv  then  pip install -r backend/requirements.txt"
    )


def start_backend() -> subprocess.Popen:
    env = os.environ.copy()
    # Put backend/ on PYTHONPATH so both 'backend.*' and 'chatbot.*' imports resolve
    env["PYTHONPATH"] = str(BACKEND_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(
        [
            str(VENV_PYTHON), "-m", "uvicorn",
            "backend.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
            "--reload-include", "*.py",
            "--reload-dir", str(BACKEND_DIR),
            "--reload-exclude", "venv",
            "--reload-exclude", "output",
            "--reload-exclude", "memory",
            "--reload-exclude", "__pycache__",
        ],
        cwd=str(ROOT),
        env=env,
    )


def start_frontend() -> subprocess.Popen:
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    return subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(FRONTEND_DIR),
    )


def main():
    print("Starting backend  ->  http://localhost:8000")
    print("Starting frontend ->  http://localhost:5173")
    print("Press Ctrl+C to stop both.\n")

    backend = start_backend()
    frontend = start_frontend()

    procs = [backend, frontend]

    def shutdown(sig, frame):
        print("\nShutting down...")
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Wait — exit if either process dies unexpectedly
    while True:
        for p in procs:
            code = p.poll()
            if code is not None:
                name = "Backend" if p is backend else "Frontend"
                print(f"\n[{name}] exited with code {code}. Stopping both...")
                shutdown(None, None)
        signal.pause() if sys.platform != "win32" else __import__("time").sleep(1)


if __name__ == "__main__":
    main()
