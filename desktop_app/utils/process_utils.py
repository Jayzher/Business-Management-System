import os
import socket

import psutil

from .. import config


def find_available_port(start_port=8000, max_attempts=10):
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except socket.error:
                continue
    return None


def is_port_in_use(port):
    """Check if a port is currently in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def _iter_connections(proc):
    """psutil renamed Process.connections() -> net_connections() in 6.0;
    fall back to the old name for pinned 5.x installations."""
    getter = getattr(proc, "net_connections", None) or getattr(proc, "connections", None)
    if getter is None:
        return []
    try:
        return getter(kind="inet")
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return []


def kill_process_on_port(port):
    """Terminate any process listening on the specified port. Returns True
    if one was found. Uses proc.terminate() so it works on Windows where
    signal.SIGTERM is unreliable for non-console subprocesses."""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for conn in _iter_connections(proc):
                laddr = getattr(conn, "laddr", None)
                if laddr and getattr(laddr, "port", None) == port:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False


def get_django_env():
    """Build the env passed to the Django subprocess. Injects desktop-mode
    flag and the absolute paths Django should use for DB/logs/sessions/cache
    so the child doesn't need to import desktop_app."""
    env = os.environ.copy()
    env['DESKTOP_MODE'] = 'true'
    env['PYTHONUNBUFFERED'] = '1'
    env.update(config.env_overrides())
    return env
