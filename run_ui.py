"""
Launch script for Streamlit UI.
Run: python run_ui.py
"""
import subprocess
import sys
from pathlib import Path

def main():
    ui_path = Path(__file__).parent / "ui" / "app.py"
    
    # Run streamlit
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        str(ui_path),
        "--server.port", "8501",
        "--server.headless", "true",
        "--theme.primaryColor", "#667eea",
        "--theme.backgroundColor", "#ffffff",
        "--theme.secondaryBackgroundColor", "#f0f2f6"
    ])

if __name__ == "__main__":
    main()
