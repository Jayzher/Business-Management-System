import time
import webbrowser

from PyQt5.QtCore import QTimer, pyqtSlot
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ..utils.logger import app_logger


def _format_uptime(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


class ServerStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._port: int | None = None
        self._started_at: float | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.status_indicator = QLabel("●")
        self.status_indicator.setObjectName("StatusIndicator")
        self.status_indicator.setStyleSheet("color: #ef4444; font-size: 14px;")

        self.status_label = QLabel("Server: Stopped")
        self.port_label = QLabel("")
        self.uptime_label = QLabel("")
        self.uptime_label.setStyleSheet("color: #6b7280;")

        self.open_browser_btn = QPushButton("Open in Browser")
        self.open_browser_btn.setEnabled(False)
        self.open_browser_btn.clicked.connect(self._open_browser)

        self.restart_btn = QPushButton("Restart Server")
        self.restart_btn.setEnabled(False)

        layout.addWidget(self.status_indicator)
        layout.addWidget(self.status_label)
        layout.addWidget(self.port_label)
        layout.addWidget(self.uptime_label)
        layout.addStretch(1)
        layout.addWidget(self.open_browser_btn)
        layout.addWidget(self.restart_btn)

        self.setLayout(layout)

    def _tick(self):
        if self._started_at is None:
            return
        self.uptime_label.setText(f"Uptime: {_format_uptime(time.time() - self._started_at)}")

    def _open_browser(self):
        if self._port is None:
            return
        webbrowser.open(f"http://127.0.0.1:{self._port}/")

    @pyqtSlot(int)
    def set_running(self, port):
        self._port = port
        self._started_at = time.time()
        self.status_label.setText("Server: Running")
        self.status_indicator.setStyleSheet("color: #22c55e; font-size: 14px;")
        self.port_label.setText(f"(Port: {port})")
        self.uptime_label.setText("Uptime: 0:00:00")
        self.restart_btn.setEnabled(True)
        self.open_browser_btn.setEnabled(True)
        self._timer.start()

    @pyqtSlot()
    def set_stopped(self):
        self._port = None
        self._started_at = None
        self._timer.stop()
        self.status_label.setText("Server: Stopped")
        self.status_indicator.setStyleSheet("color: #ef4444; font-size: 14px;")
        self.port_label.setText("")
        self.uptime_label.setText("")
        self.restart_btn.setEnabled(False)
        self.open_browser_btn.setEnabled(False)

    @pyqtSlot(str)
    def set_error(self, message):
        self._timer.stop()
        self.status_label.setText("Server Error")
        self.status_indicator.setStyleSheet("color: #f59e0b; font-size: 14px;")
        app_logger.error(f"Server Status Widget error: {message}")
