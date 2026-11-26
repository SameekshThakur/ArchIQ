#!/usr/bin/env python3
"""Start the API and the web app together, in one terminal, on Windows, macOS or Linux.

    python scripts/dev.py            # starts both, opens the browser
    python scripts/dev.py --no-browser

Ctrl+C stops both. This replaces `make dev` where `make` is not available.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
API_PORT, WEB_PORT = 8000, 5173
WIN = os.name == "nt"


def venv_python() -> str:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        p = BACKEND / rel
        if p.exists():
            return str(p)
    return sys.executable


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if WIN:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False)
        else:
            import signal

            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        proc.terminate()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    npm = shutil.which("npm")
    if not npm:
        print("npm was not found. Install Node.js 22.9 or newer from https://nodejs.org and open a new terminal.")
        return 1
    if not (FRONTEND / "node_modules").exists():
        print("Frontend packages are not installed. Run setup first (setup.bat on Windows, `make install` elsewhere).")
        return 1
    busy = [p for p in (API_PORT, WEB_PORT) if port_open(p)]
    if busy:
        print(f"Port(s) {', '.join(map(str, busy))} already in use. Close the other ArchIQ window or program using them, then run this again.")
        return 1

    if not WIN:
        import signal

        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    kw: dict = dict(env=env)
    if WIN:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True

    procs = {
        "API": subprocess.Popen([venv_python(), "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", str(API_PORT)], cwd=BACKEND, **kw),
        "Web": subprocess.Popen([npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(WEB_PORT)], cwd=FRONTEND, **kw),
    }
    print("Starting ArchIQ… press Ctrl+C to stop.")
    try:
        deadline = time.time() + 90
        ready = False
        while time.time() < deadline:
            for name, p in procs.items():
                if p.poll() is not None:
                    print(f"The {name} process stopped unexpectedly (exit code {p.returncode}). See the messages above.")
                    return 1
            if port_open(API_PORT) and port_open(WEB_PORT):
                ready = True
                break
            time.sleep(0.5)
        url = f"http://127.0.0.1:{WEB_PORT}"
        if ready:
            print(f"\nArchIQ is running:  {url}   (API docs: http://127.0.0.1:{API_PORT}/docs)\n")
            if not args.no_browser:
                webbrowser.open(url)
        else:
            print("Still starting after 90 seconds; check the messages above.")
        while all(p.poll() is None for p in procs.values()):
            time.sleep(0.5)
        return 1
    except KeyboardInterrupt:
        print("\nStopping…")
        return 0
    finally:
        for p in procs.values():
            stop(p)


if __name__ == "__main__":
    sys.exit(main())
