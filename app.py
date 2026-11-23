"""Local development launcher for the Flask application."""

from pathlib import Path
import subprocess
import sys


PROJECT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"

# `py app.py` may use system Python instead of the project's virtual environment.
# Re-run this launcher with the virtual environment when it is available.
if VENV_PYTHON.is_file() and sys.prefix == sys.base_prefix:
    process = subprocess.Popen(
        [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=PROJECT_DIR,
    )
    try:
        return_code = process.wait()
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
            process.wait()
        print("\nServer stopped.")
        raise SystemExit(0)
    raise SystemExit(return_code)

from wsgi import app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
