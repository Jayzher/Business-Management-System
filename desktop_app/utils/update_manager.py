import os
import subprocess
import sys

import requests
from PyQt5.QtCore import QObject, pyqtSignal

from ..__version__ import VERSION
from .logger import app_logger

_PLACEHOLDER_URL = "https://raw.githubusercontent.com/user/repo/main/version.json"


class UpdateManager(QObject):
    update_available = pyqtSignal(str)        # latest_version
    no_update = pyqtSignal()
    update_unavailable = pyqtSignal(str)      # reason — no real endpoint configured
    error_occurred = pyqtSignal(str)
    download_progress = pyqtSignal(int)
    download_finished = pyqtSignal(str)       # path to installer

    def __init__(self, version_url: str | None = None):
        super().__init__()
        self.version_url = version_url or _PLACEHOLDER_URL
        self.latest_version: str | None = None
        self.installer_url: str | None = None

    def is_configured(self) -> bool:
        """True only when a real (non-placeholder) update endpoint is set."""
        return bool(self.version_url) and self.version_url != _PLACEHOLDER_URL

    def check_for_updates(self):
        if not self.is_configured():
            msg = "Update checks are not configured in this build."
            app_logger.info(msg)
            self.update_unavailable.emit(msg)
            return

        app_logger.info(f"Checking for updates at {self.version_url}...")
        try:
            response = requests.get(self.version_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            self.latest_version = data.get("version")
            self.installer_url = data.get("url")

            if self.latest_version and self.is_newer(self.latest_version, VERSION):
                app_logger.info(f"Update available: {self.latest_version}")
                self.update_available.emit(self.latest_version)
            else:
                app_logger.info("No updates available.")
                self.no_update.emit()

        except Exception as exc:
            app_logger.error(f"Error checking for updates: {exc}")
            self.error_occurred.emit(str(exc))

    @staticmethod
    def is_newer(latest: str, current: str) -> bool:
        try:
            l_parts = [int(p) for p in latest.split(".")]
            c_parts = [int(p) for p in current.split(".")]
            return l_parts > c_parts
        except Exception:
            return False

    def download_update(self, url: str):
        app_logger.info(f"Downloading update from {url}...")
        try:
            temp_path = os.path.join(os.environ.get("TEMP", "."), "BMS_Setup_Update.exe")
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))

            downloaded = 0
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=4096):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    f.write(chunk)
                    if total_size > 0:
                        self.download_progress.emit(int((downloaded / total_size) * 100))

            app_logger.info(f"Download finished: {temp_path}")
            self.download_finished.emit(temp_path)

        except Exception as exc:
            app_logger.error(f"Error downloading update: {exc}")
            self.error_occurred.emit(str(exc))

    def run_installer(self, installer_path: str):
        app_logger.info(f"Launching installer: {installer_path}")
        try:
            subprocess.Popen([installer_path, "/SILENT"], shell=True)
            sys.exit(0)
        except Exception as exc:
            app_logger.error(f"Error launching installer: {exc}")
            self.error_occurred.emit(str(exc))
