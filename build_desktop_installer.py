import os
import subprocess
import sys
import shutil

# Add the current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from desktop_app.__version__ import VERSION

def find_iscc():
    """Find the Inno Setup Compiler executable."""
    common_paths = [
        r"C:\Users\Jayzee\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # Try finding in PATH
    iscc = shutil.which("iscc")
    if iscc:
        return iscc
        
    return None

def build_installer():
    print(f"Building Business Management System Installer v{VERSION}...")
    
    # 1. Build the PyInstaller executable
    print("\n--- Step 1: Building PyInstaller Executable ---")
    if not os.path.exists("build_desktop_app.py"):
        print("Error: build_desktop_app.py not found.")
        return
    
    subprocess.run([sys.executable, "build_desktop_app.py"], check=True)
    
    # 2. Compile Inno Setup Script
    print("\n--- Step 2: Compiling Inno Setup Script ---")
    iscc_path = find_iscc()
    if not iscc_path:
        print("Error: Inno Setup Compiler (ISCC.exe) not found.")
        print("Please install Inno Setup from https://jrsoftware.org/isdl.php")
        return
    
    iss_script = os.path.join("installer", "business_management_system.iss")
    if not os.path.exists(iss_script):
        print(f"Error: Installer script not found at {iss_script}")
        return
    
    # Run ISCC
    cmd = [iscc_path, iss_script]
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print(f"\nSUCCESS: Installer created in the 'dist' folder.")
        print(f"File: BMS_Setup_v{VERSION}.exe")
    else:
        print("\nERROR: Inno Setup compilation failed.")

if __name__ == "__main__":
    build_installer()
