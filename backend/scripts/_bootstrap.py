"""
Shared start-up for scripts: make ``app`` importable and fail with a clear
message when the script is run with the wrong Python (not backend/.venv).
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"


def bootstrap() -> None:
    try:
        import psycopg  # noqa: F401
    except ModuleNotFoundError:
        script = Path(sys.argv[0]).name
        sys.exit(
            "\n[setup] This script must run with the project's Python environment, not "
            f"{sys.executable}\n\n"
            "  From the backend folder, run:\n"
            f"    .venv\\Scripts\\python scripts\\{script}\n\n"
            "  (If backend\\.venv does not exist yet, double-click dev.cmd once to create it.)\n"
        )
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
