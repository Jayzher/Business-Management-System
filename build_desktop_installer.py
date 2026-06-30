import os
import shutil
import subprocess
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from desktop_app.__version__ import VERSION


def find_iscc():
    """Locate the Inno Setup Compiler executable."""
    candidates = [
        r"C:\Users\Jayzee\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return shutil.which("iscc")


def find_build_python():
    """Return a Python interpreter that has PyInstaller.
    Prefers the current interpreter; falls back to the system Python 3.13."""
    try:
        subprocess.run(
            [sys.executable, "-c", "import PyInstaller"],
            check=True, capture_output=True,
        )
        return sys.executable
    except subprocess.CalledProcessError:
        pass

    fallback = r"C:\Users\Jayzee\AppData\Local\Programs\Python\Python313\python.exe"
    if os.path.exists(fallback):
        return fallback

    raise RuntimeError(
        "PyInstaller not found. Install it with: pip install pyinstaller"
    )


def build_installer():
    print(f"Building Business Management System Installer v{VERSION}...\n")

    # ── Step 1: build the app EXE ────────────────────────────────────────────
    print("--- Step 1: Building PyInstaller Executable ---")
    python = find_build_python()
    subprocess.run([python, "build_desktop_app.py"], check=True)

    app_exe = os.path.join("dist", "BusinessManagementSystem.exe")
    if not os.path.exists(app_exe):
        print(f"ERROR: Expected {app_exe} after build — aborting.")
        sys.exit(1)

    # ── Step 2: compile the Inno Setup installer ─────────────────────────────
    print("\n--- Step 2: Compiling Inno Setup Installer ---")
    iscc = find_iscc()
    if not iscc:
        print("ERROR: Inno Setup Compiler (ISCC.exe) not found.")
        print("Download from https://jrsoftware.org/isdl.php and install.")
        sys.exit(1)

    iss_script = os.path.join("installer", "business_management_system.iss")
    if not os.path.exists(iss_script):
        print(f"ERROR: Installer script not found at {iss_script}")
        sys.exit(1)

    # /DMyAppVersion injects the version so the .iss never needs manual edits.
    cmd = [iscc, f"/DMyAppVersion={VERSION}", iss_script]
    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        output = os.path.join("dist", f"BMS_Setup_v{VERSION}.exe")
        print(f"\nSUCCESS: Installer ready at {output}")
    else:
        print("\nERROR: Inno Setup compilation failed.")
        sys.exit(1)


if __name__ == "__main__":
    build_installer()
