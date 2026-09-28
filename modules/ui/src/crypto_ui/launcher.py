"""Single executable entry: boots the Streamlit app (all tabs)."""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent / "app.py"

# no usage-stats prompt, no telemetry (must be set before streamlit import)
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")


def main(port: int = 8501) -> None:
    """Run the Lab UI: boots the Streamlit server and opens the browser."""
    from streamlit.web import cli as stcli

    if not APP_PATH.exists():
        print(f"app module missing: {APP_PATH}", file=sys.stderr)
        raise SystemExit(1)

    theme_flags = [
        "--theme.base", "dark",
        "--theme.primaryColor", "#4da3ff",
        "--theme.backgroundColor", "#0e1117",
        "--theme.secondaryBackgroundColor", "#161a23",
        "--theme.textColor", "#e8eaf0",
    ]
    threading.Timer(
        3.0, lambda: webbrowser.open(f"http://localhost:{port}")
    ).start()
    sys.argv = [
        "streamlit", "run", str(APP_PATH),
        f"--server.port={port}",
        "--server.headless=true",  # skips the first-run email prompt
        *theme_flags,
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
