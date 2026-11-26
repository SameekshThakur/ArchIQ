#!/usr/bin/env python3
"""Check that this machine is ready to run ArchIQ and say how to fix anything that is not.

    python scripts/doctor.py
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
problems = 0


def report(ok: bool, what: str, fix: str = "") -> None:
    global problems
    print(f"  [{'ok' if ok else '!!'}] {what}")
    if not ok:
        problems += 1
        if fix:
            print(f"       -> {fix}")


def venv_python() -> str | None:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        if (BACKEND / rel).exists():
            return str(BACKEND / rel)
    return None


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def port_free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) != 0


def main() -> int:
    print("ArchIQ environment check\n")
    print("Python")
    report(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]} (need 3.11 or newer)", "Install Python 3.11+ from https://python.org and tick 'Add python.exe to PATH'.")
    vpy = venv_python()
    report(vpy is not None, "Backend virtual environment (backend/.venv)", "Run setup.bat (Windows) or `make install`.")
    if vpy:
        code, out = run([vpy, "-c", "import fastapi, uvicorn, networkx, jinja2, pypdf, docx, openpyxl, multipart; print('ok')"])
        report(code == 0, "Backend packages installed", "Run: backend\\.venv\\Scripts\\python -m pip install -r backend/requirements.txt" if code else "")
    print("\nNode")
    node = shutil.which("node")
    ok = False
    if node:
        code, out = run([node, "--version"])
        m = re.match(r"v(\d+)\.(\d+)", out)
        ok = bool(m) and (int(m.group(1)), int(m.group(2))) >= (22, 9)
        report(ok, f"Node {out} (need 22.9 or newer)", "Install the current LTS from https://nodejs.org, then open a new terminal.")
    else:
        report(False, "Node.js found on PATH", "Install Node.js 22.9+ from https://nodejs.org, then open a new terminal.")
    report(shutil.which("npm") is not None, "npm found on PATH")
    report((FRONTEND / "node_modules").exists(), "Frontend packages installed (frontend/node_modules)", "Run setup.bat (Windows) or `make install`.")
    print("\nProject")
    seed = BACKEND / "app" / "data" / "seed"
    report(seed.exists() and any(seed.glob("*.json")), "Seeded estate data present", "It is generated on first start; if this fails, run: python -m scripts.generate_seed (inside backend)")
    report((ROOT / "sample-files").exists(), "Sample files present (sample-files/)")
    data = BACKEND / "data"
    try:
        data.mkdir(exist_ok=True)
        probe = data / ".write-test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        report(True, "Database folder is writable (backend/data)")
    except OSError as e:
        report(False, f"Database folder is writable ({e})", "Move the project out of a read-only or synced folder (for example not inside OneDrive Desktop).")
    print("\nPorts")
    report(port_free(8000), "Port 8000 is free (API)", "Another program is using 8000. Close it, or stop an old ArchIQ window.")
    report(port_free(5173), "Port 5173 is free (web app)", "Another program is using 5173. Close it, or stop an old ArchIQ window.")
    print("\nText encoding")
    report(True, f"Console encoding {sys.stdout.encoding}; the launchers force UTF-8 for the API (PYTHONUTF8=1)")
    print("\n" + ("Everything looks good. Start with: dev.bat (Windows) or make dev" if not problems else f"{problems} problem(s) found. Fix them and run this check again."))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
