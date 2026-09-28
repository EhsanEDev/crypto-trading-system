#!/usr/bin/env python3
"""Starter for the Crypto Lab UI.

    python run.py [--port 8501]

Works from any directory; if Streamlit is not importable with the current
interpreter, re-executes itself with the project's `.venv` interpreter.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Crypto Lab UI")
    parser.add_argument("--port", type=int, default=8501, help="server port (default 8501)")
    args = parser.parse_args()

    try:
        import streamlit  # noqa: F401
    except ImportError:
        if VENV_PYTHON.exists():
            os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(__file__), "--port", str(args.port)])
        print("streamlit is not installed.", file=sys.stderr)
        print("Fix: pip install -e 'modules/ui[dev]' (from the repository root)", file=sys.stderr)
        raise SystemExit(1)

    # ensure the package itself is importable when started outside the repo
    for candidate in (str(MODULE_DIR / "src"),):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    from crypto_ui.launcher import main as start_ui

    start_ui(port=args.port)


if __name__ == "__main__":
    main()
