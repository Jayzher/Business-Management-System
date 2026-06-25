from PyQt5.QtCore import QSettings, pyqtSlot
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAction, QMainWindow, QMenu, QMessageBox, QStatusBar, QStyle,
    QSystemTrayIcon, QVBoxLayout, QWidget
)

from .. import config
from ..__version__ import VERSION
from ..server_manager import ServerManager
from ..utils.logger import app_logger
from ..utils.update_manager import UpdateManager
from ..widgets.server_status import ServerStatusWidget
from ..widgets.toolbar import NavigationToolBar
from ..widgets.web_view import WebViewWidget
from .dialogs import AboutDialog, ErrorDialog, SettingsDialog, confirm_exit_dialog


class MainWindow(QMainWindow):
    def __init__(self, port=8000):
        super().__init__()
        self.port = port
        self.setWindowTitle(f"Business Management System - v{VERSION}")
        self.resize(1280, 820)
        self._settings = QSettings(config.ORG_NAME, config.APP_NAME)
        self._force_quit = False

        if config.ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(config.ICON_PATH)))

        self.server_manager = ServerManager(port=self.port)
        self.update_manager = UpdateManager()

        self.init_ui()
        self.init_tray()
        self.setup_connections()

    # ---- UI -----------------------------------------------------------------

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.server_status = ServerStatusWidget()
        self.layout.addWidget(self.server_status)

        self.web_view = WebViewWidget(port=self.port)
        self.nav_toolbar = NavigationToolBar(self.web_view, self)
        self.addToolBar(self.nav_toolbar)

        self.layout.addWidget(self.web_view)

        # Menu bar references web_view, so build it after the view exists.
        self.setup_menu_bar()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def setup_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu('&File')
        settings_action = QAction('Settings...', self)
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        quit_action = QAction('Quit', self)
        quit_action.setShortcut('Ctrl+Q')
        quit_action.triggered.connect(self._quit_from_menu)
        file_menu.addAction(quit_action)

        view_menu = menubar.addMenu('&View')
        reload_action = QAction('Reload', self)
        reload_action.setShortcut('F5')
        reload_action.triggered.connect(self.web_view.reload)
        view_menu.addAction(reload_action)
        home_action = QAction('Home', self)
        home_action.setShortcut('Alt+Home')
        home_action.triggered.connect(self.web_view.navigate_to_home)
        view_menu.addAction(home_action)

        help_menu = menubar.addMenu('&Help')
        check_update_action = QAction('Check for Updates...', self)
        check_update_action.triggered.connect(self.check_for_updates)
        help_menu.addAction(check_update_action)
        about_action = QAction('About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return

        icon = QIcon(str(config.ICON_PATH)) if config.ICON_PATH.exists() \
            else self.style().standardIcon(QStyle.SP_ComputerIcon)

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(f"Business Management System v{VERSION}")

        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self._restore_from_tray)
        menu.addAction(show_action)

        restart_action = QAction("Restart Server", self)
        restart_action.triggered.connect(self.restart_server)
        menu.addAction(restart_action)

        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_from_menu)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # ---- Signals ------------------------------------------------------------

    def setup_connections(self):
        sm = self.server_manager
        sm.server_started.connect(self.on_server_started)
        sm.server_stopped.connect(self.on_server_stopped)
        sm.server_error.connect(self.on_server_error)
        sm.health_check_done.connect(self.on_health_check_done)

        sm.server_started.connect(self.server_status.set_running)
        sm.server_stopped.connect(self.server_status.set_stopped)
        sm.server_error.connect(self.server_status.set_error)

        sm.migration_started.connect(
            lambda: self.status_bar.showMessage("Running database migrations...")
        )

        self.server_status.restart_btn.clicked.connect(self.restart_server)

        self.update_manager.update_available.connect(self.on_update_available)
        self.update_manager.no_update.connect(self.on_no_update)
        self.update_manager.update_unavailable.connect(self.on_update_unavailable)
        self.update_manager.error_occurred.connect(self.on_update_error)

        self.web_view.download_completed.connect(self.on_download_completed)
        self.web_view.download_failed.connect(self.on_download_failed)

    # ---- Actions ------------------------------------------------------------

    def start_backend(self):
        app_logger.info("Starting backend server thread...")
        self.server_manager.start()

    def restart_server(self):
        self.server_manager.stop_server()
        self.server_manager.start()

    def check_for_updates(self):
        self.status_bar.showMessage("Checking for updates...")
        self.update_manager.check_for_updates()

    def show_settings(self):
        SettingsDialog(self).exec_()

    def show_about(self):
        AboutDialog(self).exec_()

    # ---- Slots --------------------------------------------------------------

    @pyqtSlot(int)
    def on_server_started(self, port):
        self.port = port
        self.web_view.port = port
        self.status_bar.showMessage(f"Server started on port {port}. Waiting for health check...")

    @pyqtSlot(bool)
    def on_health_check_done(self, healthy):
        if healthy:
            self.status_bar.showMessage("Server is healthy. Loading UI...")
            self.web_view.navigate_to_home()
        else:
            self.status_bar.showMessage("Server health check failed.")
            ErrorDialog(
                "Error",
                "Server health check failed. Please check the logs and try restarting.",
                self,
            ).exec_()

    @pyqtSlot()
    def on_server_stopped(self):
        self.status_bar.showMessage("Server stopped.")

    @pyqtSlot(str)
    def on_server_error(self, message):
        self.status_bar.showMessage(f"Server Error: {message}")
        ErrorDialog("Server Error", message, self).exec_()

    @pyqtSlot(str)
    def on_update_available(self, latest_version):
        self.status_bar.showMessage(f"Update available: {latest_version}")
        reply = QMessageBox.question(
            self, 'Update Available',
            f"A new version ({latest_version}) is available. Download and install now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes and self.update_manager.installer_url:
            self.update_manager.download_update(self.update_manager.installer_url)

    @pyqtSlot()
    def on_no_update(self):
        self.status_bar.showMessage("App is up to date.")
        QMessageBox.information(self, "Up to Date", f"You are running the latest version (v{VERSION}).")

    @pyqtSlot(str)
    def on_update_unavailable(self, reason):
        self.status_bar.showMessage(reason)
        QMessageBox.information(self, "Updates", reason)

    @pyqtSlot(str)
    def on_update_error(self, error):
        self.status_bar.showMessage(f"Update error: {error}")
        QMessageBox.warning(self, "Update Error", f"Could not check for updates:\n{error}")

    @pyqtSlot(str)
    def on_download_completed(self, path):
        self.status_bar.showMessage(f"Download complete: {path}", 5000)
        if self.tray is not None:
            self.tray.showMessage(
                "Download complete", path, QSystemTrayIcon.Information, 3000,
            )

    @pyqtSlot(str)
    def on_download_failed(self, path):
        self.status_bar.showMessage(f"Download failed: {path}", 5000)
        if self.tray is not None:
            self.tray.showMessage(
                "Download failed", path, QSystemTrayIcon.Warning, 3000,
            )

    # ---- Tray handling ------------------------------------------------------

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---- Exit flow ----------------------------------------------------------

    def _quit_from_menu(self):
        self._force_quit = True
        self.close()

    def closeEvent(self, event):
        minimize_to_tray = self._settings.value("ui/minimize_to_tray", False, type=bool)
        if minimize_to_tray and not self._force_quit and self.tray is not None:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Business Management System",
                "App is still running in the system tray.",
                QSystemTrayIcon.Information, 3000,
            )
            return

        confirm_exit = self._settings.value("ui/confirm_exit", True, type=bool)
        if confirm_exit and not self._force_quit:
            accepted, remember = confirm_exit_dialog(self)
            if not accepted:
                event.ignore()
                return
            if remember:
                self._settings.setValue("ui/confirm_exit", False)

        app_logger.info("Closing application...")
        self.server_manager.stop_server()
        if self.tray is not None:
            self.tray.hide()
        event.accept()
