"""Central path / config module for the desktop app.

Provides a single source of truth for where the app reads and writes data:
- In a frozen build (PyInstaller .exe) all user data lives under
  %LOCALAPPDATA%\\BusinessManagementSystem so the app works when installed
  to Program Files or any other read-only directory.
- In dev mode (running from source), data stays in the project root so
  developers see what they expect.

On first launch in frozen mode, this module also performs a one-time
migration of pre-existing data (db.sqlite3, sidecar WAL/SHM files, and the
media/ folder) from next-to-the-exe to %LOCALAPPDATA%. This handles users
upgrading from v1.0.0 which wrote data next to BusinessManagementSystem.exe.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "BusinessManagementSystem"
ORG_NAME = "PsyChoNyMouz"

IS_FROZEN = bool(getattr(sys, "frozen", False))


def _frozen_app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def _dev_project_root() -> Path:
    # desktop_app/config.py -> desktop_app/ -> project root
    return Path(__file__).resolve().parent.parent


if IS_FROZEN:
    APP_DATA_DIR: Path = _frozen_app_data_dir()
    EXE_DIR: Path = Path(sys.executable).resolve().parent
else:
    APP_DATA_DIR = _dev_project_root()
    EXE_DIR = APP_DATA_DIR

LOGS_DIR: Path = APP_DATA_DIR / "logs"
SESSIONS_DIR: Path = APP_DATA_DIR / "sessions"
CACHE_DIR: Path = APP_DATA_DIR / "cache"
MEDIA_DIR: Path = APP_DATA_DIR / "media"
DB_PATH: Path = APP_DATA_DIR / "db.sqlite3"

# Resources shipped inside the bundle (read-only). PyInstaller extracts
# datas into sys._MEIPASS; in dev they sit alongside this file.
if IS_FROZEN and hasattr(sys, "_MEIPASS"):
    _RESOURCES_DIR = Path(sys._MEIPASS) / "desktop_app" / "resources"
else:
    _RESOURCES_DIR = Path(__file__).resolve().parent / "resources"

ICON_PATH: Path = _RESOURCES_DIR / "icons" / "app.ico"
STYLESHEET_PATH: Path = _RESOURCES_DIR / "styles" / "app.qss"

_MIGRATION_MARKER = APP_DATA_DIR / ".migrated_v1"


def _ensure_dirs() -> None:
    for d in (APP_DATA_DIR, LOGS_DIR, SESSIONS_DIR, CACHE_DIR, MEDIA_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _migrate_legacy_data() -> None:
    """Copy v1.0.0 data (next to the .exe) into APP_DATA_DIR. Runs once."""
    if not IS_FROZEN or _MIGRATION_MARKER.exists():
        return

    legacy_db = EXE_DIR / "db.sqlite3"
    if legacy_db.exists() and not DB_PATH.exists():
        for name in ("db.sqlite3", "db.sqlite3-wal", "db.sqlite3-shm"):
            src = EXE_DIR / name
            if src.exists():
                try:
                    shutil.copy2(src, APP_DATA_DIR / name)
                except OSError:
                    # Best-effort: don't crash launch if a sidecar file is locked.
                    pass

        legacy_media = EXE_DIR / "media"
        if legacy_media.is_dir() and not any(MEDIA_DIR.iterdir()):
            try:
                shutil.copytree(legacy_media, MEDIA_DIR, dirs_exist_ok=True)
            except OSError:
                pass

    try:
        _MIGRATION_MARKER.write_text("v1\n", encoding="utf-8")
    except OSError:
        pass


_ensure_dirs()
_migrate_legacy_data()


def env_overrides() -> dict[str, str]:
    """Env vars passed to the Django subprocess so it uses the same paths
    without importing this module."""
    return {
        "BMS_DB_PATH": str(DB_PATH),
        "BMS_SESSIONS_DIR": str(SESSIONS_DIR),
        "BMS_CACHE_DIR": str(CACHE_DIR),
        "BMS_LOGS_DIR": str(LOGS_DIR),
        "BMS_MEDIA_DIR": str(MEDIA_DIR),
    }
