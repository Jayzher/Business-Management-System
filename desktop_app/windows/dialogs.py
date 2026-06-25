from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout
)

from .. import config
from ..__version__ import APP_NAME, AUTHOR, VERSION


def _settings() -> QSettings:
    return QSettings(config.ORG_NAME, config.APP_NAME)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        title.setAlignment(Qt.AlignCenter)

        version_label = QLabel(f"Version {VERSION}")
        version_label.setAlignment(Qt.AlignCenter)

        author_label = QLabel(f"© {AUTHOR}")
        author_label.setAlignment(Qt.AlignCenter)

        data_label = QLabel(f"Data folder:\n{config.APP_DATA_DIR}")
        data_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data_label.setWordWrap(True)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)

        layout.addWidget(title)
        layout.addWidget(version_label)
        layout.addWidget(author_label)
        layout.addWidget(data_label)
        layout.addStretch(1)
        layout.addWidget(button_box)


class SettingsDialog(QDialog):
    """User preferences backed by QSettings. Read by MainWindow on close
    and at startup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(360)
        self._settings = _settings()

        form = QFormLayout()
        form.setSpacing(10)

        self.minimize_to_tray = QCheckBox("Minimize to system tray on close")
        self.minimize_to_tray.setChecked(
            self._settings.value("ui/minimize_to_tray", False, type=bool)
        )

        self.confirm_exit = QCheckBox("Confirm before exiting")
        self.confirm_exit.setChecked(
            self._settings.value("ui/confirm_exit", True, type=bool)
        )

        self.theme = QComboBox()
        self.theme.addItems(["System", "Light"])  # Dark deferred
        current_theme = self._settings.value("ui/theme", "System")
        idx = self.theme.findText(current_theme)
        if idx >= 0:
            self.theme.setCurrentIndex(idx)

        form.addRow(self.minimize_to_tray)
        form.addRow(self.confirm_exit)
        form.addRow("Theme:", self.theme)

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(button_box)

    def _on_save(self):
        self._settings.setValue("ui/minimize_to_tray", self.minimize_to_tray.isChecked())
        self._settings.setValue("ui/confirm_exit", self.confirm_exit.isChecked())
        self._settings.setValue("ui/theme", self.theme.currentText())
        self.accept()


class ErrorDialog(QDialog):
    """Error dialog that exposes the log directory so users can grab logs
    when reporting an issue."""

    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        path_label = QLabel(f"Logs: {config.LOGS_DIR}")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_label.setWordWrap(True)

        button_row = QHBoxLayout()
        copy_btn = QPushButton("Copy logs path")
        copy_btn.clicked.connect(self._copy_logs_path)
        button_row.addWidget(copy_btn)
        button_row.addStretch(1)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        button_row.addWidget(ok_btn)

        layout.addWidget(msg_label)
        layout.addWidget(path_label)
        layout.addLayout(button_row)

    def _copy_logs_path(self):
        QApplication.clipboard().setText(str(config.LOGS_DIR))


def confirm_exit_dialog(parent, allow_remember: bool = True):
    """QMessageBox variant with an optional 'Don't ask again' checkbox.
    Returns (accepted: bool, remember: bool)."""
    box = QMessageBox(parent)
    box.setWindowTitle("Exit")
    box.setIcon(QMessageBox.Question)
    box.setText("Are you sure you want to exit? This will stop the server.")
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)

    checkbox = None
    if allow_remember:
        checkbox = QCheckBox("Don't ask again")
        box.setCheckBox(checkbox)

    reply = box.exec_()
    accepted = reply == QMessageBox.Yes
    remember = bool(checkbox.isChecked()) if checkbox is not None else False
    return accepted, remember
