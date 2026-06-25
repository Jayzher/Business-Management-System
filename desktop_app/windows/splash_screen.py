from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget
)

from .. import config


class LoadingSplashScreen(QWidget):
    """Frameless splash that uses a real layout (the old QSplashScreen-based
    version mixed layouts with absolute geometry, which never positioned
    children correctly)."""

    def __init__(self):
        super().__init__(
            flags=Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setObjectName("SplashScreen")
        self.setFixedSize(420, 220)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        if config.ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(config.ICON_PATH)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        self.title_label = QLabel("Business Management System")
        self.title_label.setObjectName("SplashTitle")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel("Initializing...")
        self.status_label.setObjectName("SplashStatus")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)

        self.progress = QProgressBar()
        self.progress.setObjectName("SplashProgress")
        self.progress.setRange(0, 0)  # Indeterminate
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)

        layout.addStretch(1)
        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addWidget(self.progress)

        # Fallback style in case the global stylesheet hasn't loaded yet.
        self.setStyleSheet("""
            QWidget#SplashScreen {
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
            }
            QLabel#SplashTitle {
                font-size: 18px;
                font-weight: 600;
                color: #1f2937;
            }
            QLabel#SplashStatus {
                font-size: 12px;
                color: #4b5563;
            }
        """)

    def show_message(self, message: str) -> None:
        self.status_label.setText(message)
        self.repaint()
        QApplication.processEvents()

    def finish(self, main_window) -> None:
        """API-compatible with QSplashScreen.finish(): close splash once
        the target window is visible."""
        self.close()

    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )
