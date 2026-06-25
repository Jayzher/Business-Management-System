import os
import subprocess
import sys
import threading

from PyQt5.QtCore import QThread, pyqtSignal

from .utils.health_check import check_server_health
from .utils.logger import app_logger, server_logger
from .utils.process_utils import find_available_port, get_django_env, is_port_in_use


class ServerManager(QThread):
    server_started = pyqtSignal(int)      # port
    server_stopped = pyqtSignal()
    server_error = pyqtSignal(str)
    server_log = pyqtSignal(str)
    health_check_done = pyqtSignal(bool)
    migration_started = pyqtSignal()
    migration_finished = pyqtSignal(bool)  # success

    def __init__(self, project_path=None, port=8000):
        super().__init__()
        self.project_path = project_path or os.getcwd()
        self.port = port
        self.process = None
        self.is_running = False
        self._stop_event = threading.Event()

    def run(self):
        self.start_server()

    def _django_cmd(self, *args):
        """Build the command vector for invoking a Django management command,
        accounting for whether we're running as a script or a PyInstaller exe.

        In frozen mode, main.py short-circuits known subcommands through
        django.core.management.execute_from_command_line before Qt starts,
        so re-invoking sys.executable with the subcommand as argv[1] works."""
        if getattr(sys, 'frozen', False):
            return [sys.executable, *args]
        return [sys.executable, "manage.py", *args]

    def _run_migrate(self) -> bool:
        """Run `migrate --noinput` synchronously. Returns True on success."""
        self.migration_started.emit()
        app_logger.info("Running database migrations...")
        cmd = self._django_cmd("migrate", "--noinput")
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                env=get_django_env(),
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
        except Exception as exc:
            app_logger.error(f"Failed to launch migrate subprocess: {exc}")
            self.migration_finished.emit(False)
            return False

        for line in (result.stdout or "").splitlines():
            server_logger.info(line)
            self.server_log.emit(line)
        for line in (result.stderr or "").splitlines():
            server_logger.warning(line)
            self.server_log.emit(line)

        ok = result.returncode == 0
        app_logger.info(f"Migrations completed with exit code {result.returncode}")
        self.migration_finished.emit(ok)
        return ok

    def start_server(self):
        try:
            if is_port_in_use(self.port):
                app_logger.info(f"Port {self.port} is in use. Finding another port...")
                next_port = find_available_port(self.port + 1)
                if not next_port:
                    self.server_error.emit("Could not find an available port.")
                    return
                self.port = next_port

            if not self._run_migrate():
                self.server_error.emit("Database migration failed. See logs for details.")
                self.health_check_done.emit(False)
                return

            app_logger.info(f"Starting Django server on port {self.port}...")
            cmd = self._django_cmd("runserver", f"127.0.0.1:{self.port}", "--noreload")

            self.process = subprocess.Popen(
                cmd,
                cwd=self.project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=get_django_env(),
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )

            self.is_running = True
            self.server_started.emit(self.port)

            threading.Thread(target=self._read_logs, daemon=True).start()

            url = f"http://127.0.0.1:{self.port}/"
            app_logger.info(f"Performing health check on {url}...")
            healthy = check_server_health(url, timeout=5, retries=30, interval=1.0)
            app_logger.info(f"Health check result: {healthy}")
            self.health_check_done.emit(healthy)

            if not healthy:
                app_logger.error("Server health check failed after retries.")
                self.server_error.emit("Server health check failed.")
                self.stop_server()

        except Exception as exc:
            app_logger.error(f"Error starting server: {exc}")
            self.server_error.emit(str(exc))

    def _read_logs(self):
        if self.process and self.process.stdout:
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    clean_line = line.strip()
                    server_logger.info(clean_line)
                    self.server_log.emit(clean_line)
            self.process.stdout.close()

    def stop_server(self):
        if self.process:
            app_logger.info("Stopping Django server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app_logger.warning("Server didn't stop gracefully, killing it...")
                self.process.kill()
            self.process = None
            self.is_running = False
            self.server_stopped.emit()
            app_logger.info("Django server stopped.")

    def is_healthy(self) -> bool:
        url = f"http://127.0.0.1:{self.port}/"
        return check_server_health(url)
