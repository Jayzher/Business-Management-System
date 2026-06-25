import os
import sys
import traceback

from PyQt5.QtCore import QCoreApplication, QSharedMemory
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox

from . import config
from .utils.logger import app_logger
from .windows.dialogs import ErrorDialog
from .windows.main_window import MainWindow
from .windows.splash_screen import LoadingSplashScreen


def exception_hook(exctype, value, tb):
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    app_logger.critical(f"Unhandled exception: {err_msg}")
    print(err_msg)
    try:
        if QApplication.instance():
            ErrorDialog("Critical Error", str(value)).exec_()
    except Exception:
        pass
    sys.exit(1)


def _load_stylesheet(app: QApplication) -> None:
    qss_path = config.STYLESHEET_PATH
    if qss_path.exists():
        try:
            app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
        except OSError as exc:
            app_logger.warning(f"Could not load stylesheet {qss_path}: {exc}")


def main():
    sys.excepthook = exception_hook
    os.environ['DESKTOP_MODE'] = 'true'

    # Short-circuit Django management subcommands when launched as a bundled exe.
    if len(sys.argv) > 1 and sys.argv[1] in ('runserver', 'migrate', 'db_sync', 'shell'):
        try:
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
            from django.core.management import execute_from_command_line
            execute_from_command_line(sys.argv)
            return
        except Exception as exc:
            try:
                (config.LOGS_DIR / "django_error.log").write_text(
                    f"Error executing {sys.argv[1]}: {exc}\n{traceback.format_exc()}",
                    encoding="utf-8",
                )
            except OSError:
                pass
            return

    # QSettings org/app names must be set before any QSettings() call.
    QCoreApplication.setOrganizationName(config.ORG_NAME)
    QCoreApplication.setApplicationName(config.APP_NAME)

    app = QApplication(sys.argv)
    app.setApplicationName("Business Management System")
    if config.ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(config.ICON_PATH)))

    _load_stylesheet(app)

    mutex = QSharedMemory("BMS_Desktop_App_Mutex")
    if not mutex.create(1):
        print("Application is already running.")
        sys.exit(0)
    app._mutex = mutex

    splash = LoadingSplashScreen()
    splash.show()
    QApplication.processEvents()

    window = MainWindow()
    window.start_backend()

    def on_health_check(healthy):
        app_logger.info(f"Main health check callback triggered. Healthy: {healthy}")
        if healthy:
            try:
                window.show()
                splash.finish(window)
                window.raise_()
                window.activateWindow()
                app_logger.info("Main window shown.")
            except Exception as exc:
                app_logger.error(f"Error showing main window: {exc}\n{traceback.format_exc()}")
        else:
            splash.finish(window)
            app_logger.error("Server initialization failed.")
            ErrorDialog(
                "Startup Error",
                "Server initialization failed. Check the log file for details.",
            ).exec_()
            sys.exit(1)

    window.server_manager.health_check_done.connect(on_health_check)

    app_logger.info("Entering main event loop...")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
