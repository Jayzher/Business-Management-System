import os
import shutil
import subprocess
import sys
import time

import PyInstaller.__main__


def _kill_running_exe(name: str) -> None:
    """Terminate any running process whose image name matches `name`."""
    result = subprocess.run(
        ['taskkill', '/F', '/IM', name],
        capture_output=True,
    )
    if result.returncode == 0:
        print(f"Stopped running {name}, waiting for it to release files...")
        time.sleep(2)


def _rmtree_retry(path: str, retries: int = 3, delay: float = 2.0) -> None:
    for attempt in range(retries):
        try:
            shutil.rmtree(path)
            return
        except PermissionError as exc:
            if attempt < retries - 1:
                print(f"Could not remove {path} ({exc}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise


def build():
    _kill_running_exe('BusinessManagementSystem.exe')

    for folder in ('build', 'dist'):
        if os.path.exists(folder):
            _rmtree_retry(folder)

    debug_console = os.environ.get('BMS_DEBUG_CONSOLE') == '1'

    args = [
        'desktop_app_launcher.py',
        '--name=BusinessManagementSystem',
        '--onefile',
        '--windowed' if not debug_console else '--console',
        '--icon=desktop_app/resources/icons/app.ico',
        '--add-data=templates;templates',
        '--add-data=static;static',
        '--add-data=media;media',
        '--add-data=desktop_app/resources;desktop_app/resources',
        '--collect-all=PyQt5',
        '--collect-all=PyQtWebEngine',
        '--collect-data=autobahn',
        '--hidden-import=PyQt5.QtWebEngineWidgets',
        '--hidden-import=django.contrib.admin',
        '--hidden-import=django.contrib.auth',
        '--hidden-import=django.contrib.contenttypes',
        '--hidden-import=django.contrib.sessions',
        '--hidden-import=django.contrib.messages',
        '--hidden-import=django.contrib.staticfiles',
        '--hidden-import=whitenoise.middleware',
        '--hidden-import=inventory_system.urls',
        '--hidden-import=inventory_system.wsgi',
        '--hidden-import=inventory_system.asgi',
        '--hidden-import=inventory_system.env_middleware',
        '--hidden-import=inventory_system.db_router',
        '--hidden-import=inventory_system.settings_desktop',
        '--hidden-import=accounts.backends',
    ]

    print("Running collectstatic...")
    subprocess.run(
        [sys.executable, "manage.py", "collectstatic", "--noinput"],
        check=True,
    )

    print("Starting build process...")
    PyInstaller.__main__.run(args)
    print("Build complete. Executable is in the 'dist' folder.")


if __name__ == "__main__":
    build()
