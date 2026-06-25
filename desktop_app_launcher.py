import os
import sys

# Add the current directory to sys.path so we can import desktop_app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from desktop_app.main import main

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Critical error: {e}")
        input("Press Enter to exit...")
