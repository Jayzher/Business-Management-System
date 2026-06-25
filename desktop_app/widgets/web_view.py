from pathlib import Path

from PyQt5.QtCore import QSettings, QStandardPaths, QUrl, pyqtSignal
from PyQt5.QtWebEngineWidgets import (
    QWebEngineDownloadItem, QWebEngineProfile, QWebEngineView,
)
from PyQt5.QtWidgets import QFileDialog

from .. import config
from ..utils.logger import app_logger

_DOWNLOAD_DIR_KEY = "downloads/last_dir"


class WebViewWidget(QWebEngineView):
    # Emitted after a download finishes, so MainWindow can surface it
    # (status bar / tray) without WebViewWidget knowing about that UI.
    download_completed = pyqtSignal(str)
    download_failed = pyqtSignal(str)

    def __init__(self, port=8000, parent=None):
        super().__init__(parent)
        self.port = port
        self._active_downloads = {}  # id(download) -> download, keeps refs alive
        self.setup_settings()

        # Connect signals
        self.loadStarted.connect(self.on_load_started)
        self.loadProgress.connect(self.on_load_progress)
        self.loadFinished.connect(self.on_load_finished)

    def setup_settings(self):
        """Configure WebEngine settings."""
        settings = self.settings()
        # settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        # settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)

        # Persistent storage for cookies/sessions
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentStoragePath(profile.persistentStoragePath())
        profile.setPersistentCookiesPolicy(QWebEngineProfile.AllowPersistentCookies)

        # Without this, Chromium silently drops every download (CSV/XLSX
        # exports, import templates, invoice attachments) since QWebEngineView
        # has no default "Save As" behavior like a real browser.
        profile.downloadRequested.connect(self._on_download_requested)

    def _on_download_requested(self, download: QWebEngineDownloadItem) -> None:
        suggested = download.suggestedFileName() or Path(download.url().path()).name or "download"

        qsettings = QSettings(config.ORG_NAME, config.APP_NAME)
        last_dir = qsettings.value(_DOWNLOAD_DIR_KEY, "")
        default_dir = last_dir if last_dir and Path(last_dir).is_dir() else (
            QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        )

        path, _ = QFileDialog.getSaveFileName(
            self, "Save File", str(Path(default_dir) / suggested)
        )
        if not path:
            download.cancel()
            return

        download.setPath(path)
        download.accept()
        qsettings.setValue(_DOWNLOAD_DIR_KEY, str(Path(path).parent))

        self._active_downloads[id(download)] = download
        download.finished.connect(lambda d=download: self._on_download_finished(d))

    def _on_download_finished(self, download: QWebEngineDownloadItem) -> None:
        self._active_downloads.pop(id(download), None)
        if download.state() == QWebEngineDownloadItem.DownloadCompleted:
            app_logger.info(f"Download completed: {download.path()}")
            self.download_completed.emit(download.path())
        else:
            app_logger.warning(
                f"Download did not complete (state={download.state()}): {download.path()}"
            )
            self.download_failed.emit(download.path())

    def navigate_to_home(self):
        """Load localhost:port."""
        url = f"http://127.0.0.1:{self.port}/"
        app_logger.info(f"Navigating to {url}")
        self.setUrl(QUrl(url))

    def on_load_started(self):
        app_logger.info("WebView: Page load started...")

    def on_load_progress(self, progress):
        if progress % 25 == 0:
            app_logger.info(f"WebView: Load progress {progress}%")

    def on_load_finished(self, ok):
        """Handle load completion."""
        if ok:
            app_logger.info("WebView: Page load finished successfully.")
        else:
            app_logger.error("WebView: Failed to load page.")
            # We could show a custom error page here
            self.setHtml("<h1>Failed to connect to the server.</h1><p>Please check if the Django server is running.</p>")
