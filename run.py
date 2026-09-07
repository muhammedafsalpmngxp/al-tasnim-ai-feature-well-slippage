"""
Run the Well Delay AI backend (FastAPI) and frontend (React/Vite) together.

Usage:

    python run.py

Stops both processes on Ctrl+C, or if either one exits on its own.
"""

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"

BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")

IS_WINDOWS = os.name == "nt"


# Vite prints box-drawing and arrow glyphs that a cp1252 Windows
# console cannot encode — without this, relaying its output raises
# UnicodeEncodeError and the log thread dies silently.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


# ============================================================
# PREREQUISITE CHECKS
# ============================================================

def check_prerequisites():

    if not BACKEND_DIR.is_dir():
        raise SystemExit(f"Backend directory not found: {BACKEND_DIR}")

    if not FRONTEND_DIR.is_dir():
        raise SystemExit(f"Frontend directory not found: {FRONTEND_DIR}")

    npm = shutil.which("npm")

    if npm is None:
        raise SystemExit(
            "npm was not found on PATH. Install Node.js 18+ to run the frontend."
        )

    if not (FRONTEND_DIR / "node_modules").is_dir():
        raise SystemExit(
            "Frontend dependencies are not installed. Run:\n\n"
            "    cd frontend && npm install\n"
        )

    return npm


# ============================================================
# PROCESS MANAGEMENT
# ============================================================

def stream_output(prefix, process):

    for line in process.stdout:
        sys.stdout.write(f"[{prefix}] {line}")
        sys.stdout.flush()


def start_process(prefix, command, cwd):

    print(f"[{prefix}] starting: {' '.join(command)}")

    # New process group / session so the whole tree can be
    # stopped later — uvicorn --reload and vite both spawn
    # child processes of their own.
    if IS_WINDOWS:
        platform_options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        platform_options = {"start_new_session": True}

    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        **platform_options
    )

    reader = threading.Thread(
        target=stream_output,
        args=(prefix, process),
        daemon=True
    )

    reader.start()

    return process


def stop_process(prefix, process):

    if process.poll() is not None:
        return

    print(f"[{prefix}] stopping...")

    try:

        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)

        process.wait(timeout=10)

    except Exception:
        process.kill()


# ============================================================
# MAIN
# ============================================================

def main():

    npm = check_prerequisites()

    backend_command = [
        sys.executable,
        "-m", "uvicorn",
        "main:app",
        "--reload",
        "--host", BACKEND_HOST,
        "--port", BACKEND_PORT
    ]

    frontend_command = [npm, "run", "dev"]

    processes = []

    try:

        processes.append(
            ("backend", start_process("backend", backend_command, BACKEND_DIR))
        )

        processes.append(
            ("frontend", start_process("frontend", frontend_command, FRONTEND_DIR))
        )

        print()
        print(f"Backend:  http://{BACKEND_HOST}:{BACKEND_PORT}")
        print("Frontend: http://localhost:5173")
        print("Press Ctrl+C to stop both.")
        print()

        # Exit as soon as either process stops, so a crashed
        # backend does not leave a frontend running against it.
        while True:

            for name, process in processes:

                if process.poll() is not None:
                    print(f"\n[{name}] exited with code {process.returncode}")
                    return

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nShutting down...")

    finally:

        for name, process in processes:
            stop_process(name, process)


if __name__ == "__main__":
    main()
