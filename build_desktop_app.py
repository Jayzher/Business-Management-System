import os
import shutil
import subprocess
import sys

import PyInstaller.__main__


def build():
    for folder in ('build', 'dist'):
        if os.path.exists(folder):
            shutil.rmtree(folder)

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
