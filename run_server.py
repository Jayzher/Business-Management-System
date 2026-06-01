#!/usr/bin/env python
"""
Dev server helper with Start/Stop commands.

Usage:
  python run_server.py start   # starts dev server on 0.0.0.0:8000
  python run_server.py stop    # stops previously started server

Behavior:
  - Uses local env/Scripts/python.exe if present, otherwise current python.
  - Writes PID to .devserver.pid so you can stop it later.
  - Prints the URL and port when starting.
"""
from pathlib import Path
import subprocess
import sys
import os

BASE_DIR = Path(__file__).resolve().parent
VENV_PY = BASE_DIR / "env" / "Scripts" / "python.exe"
MANAGE_PY = BASE_DIR / "manage.py"
PID_FILE = BASE_DIR / ".devserver.pid"

if not VENV_PY.exists():
    print("ERROR: Virtualenv Python not found at", VENV_PY)
    print("Create/activate the env first, e.g.:")
    print("  python -m venv env")
    print("  env\\Scripts\\activate && pip install -r requirements.txt")
    sys.exit(1)

python_exe = VENV_PY


def start_server():
    if PID_FILE.exists():
        print(f"PID file already exists at {PID_FILE}. If the server is not running, delete the file and try again.")
        return
    print(f"Using Python: {python_exe}")
    print("Running migrations...")
    result = subprocess.run(
        [str(python_exe), str(MANAGE_PY), "migrate", "--no-input"],
        cwd=str(BASE_DIR),
    )
    if result.returncode != 0:
        print("ERROR: migrate failed. Fix the error above before starting the server.")
        sys.exit(result.returncode)
    check = subprocess.run(
        [str(python_exe), str(MANAGE_PY), "shell", "--no-input", "-c",
         "from django.conf import settings; print('1' if getattr(settings, 'NEON_INITIAL_SYNC', True) else '0')"],
        capture_output=True, text=True, cwd=str(BASE_DIR),
    )
    if check.returncode == 0 and check.stdout.strip() == '1':
        print("Syncing latest data from Neon PostgreSQL → local SQLite...")
        sync_result = subprocess.run(
            [str(python_exe), str(MANAGE_PY), "db_sync", "--direction", "neon_to_local"],
            cwd=str(BASE_DIR),
        )
        if sync_result.returncode != 0:
            print("WARNING: Initial Neon sync failed. Server will start with existing local data.")
    else:
        print("NEON_INITIAL_SYNC=False — skipping startup sync.")
    print("Starting dev server on http://127.0.0.1:8000 (bound to 0.0.0.0:8000)...")
    proc = subprocess.Popen(
        [str(python_exe), str(MANAGE_PY), "runserver", "0.0.0.0:8000"],
        cwd=str(BASE_DIR),
    )
    PID_FILE.write_text(str(proc.pid))
    print(f"Server PID: {proc.pid} (saved to {PID_FILE})")


def stop_server():
    if not PID_FILE.exists():
        print("No PID file found. Is the server running?")
        return
    pid = PID_FILE.read_text().strip()
    if not pid:
        print("PID file is empty; remove it manually if needed.")
        return
    print(f"Stopping server PID {pid}...")
    try:
        # Windows-friendly termination via taskkill
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        # Fallback: attempt os.kill if taskkill not available
        try:
            os.kill(int(pid), 9)
        except Exception as e:
            print(f"Could not kill PID {pid}: {e}")
            return
    PID_FILE.unlink(missing_ok=True)
    print("Server stopped and PID file removed.")


def main():
    if len(sys.argv) < 2 or sys.argv[1].lower() not in {"start", "stop"}:
        print("Usage: python run_server.py [start|stop]")
        return
    cmd = sys.argv[1].lower()
    if cmd == "start":
        start_server()
    else:
        stop_server()


if __name__ == "__main__":
    main()
