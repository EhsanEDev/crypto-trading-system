"""Starter-script tests (run.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_run_module():
    path = Path(__file__).resolve().parents[1] / "run.py"
    spec = importlib.util.spec_from_file_location("ui_run", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_module_resolves_paths() -> None:
    run = _load_run_module()
    assert run.MODULE_DIR.name == "ui"
    assert run.REPO_ROOT.name == "crypto-strategy-lab"
    assert run.VENV_PYTHON.name == "python"


def test_run_module_help(capsys) -> None:
    run = _load_run_module()
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        # argparse exits on --help
        import sys

        argv_backup = sys.argv
        sys.argv = ["run.py", "--help"]
        try:
            run.main()
        finally:
            sys.argv = argv_backup
    assert exc_info.value.code == 0
    assert "--port" in capsys.readouterr().out
