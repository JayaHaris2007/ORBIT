"""Double-clickable Windows GUI entry point for ORBIT Control Center."""

from pathlib import Path
import os
import subprocess
import sys

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# If double-clicked via system Python, re-launch inside .venv\Scripts\pythonw.exe when available
if os.name == "nt" and ".venv" not in sys.executable.lower():
    venv_pythonw = ROOT_DIR / ".venv" / "Scripts" / "pythonw.exe"
    if venv_pythonw.is_file():
        subprocess.Popen([str(venv_pythonw), str(ROOT_DIR / "orbit_launcher.py")], cwd=str(ROOT_DIR))
        raise SystemExit(0)

from orbit_launcher import launch_gui  # noqa: E402

if __name__ == "__main__":
    launch_gui()
