"""Test bootstrap: make ``helpers`` importable as a top-level module.

The monorepo has one ``tests`` package per module; importing
``tests.helpers`` from here would clash with the research module's
``tests`` package under some invocation styles, so strategy tests import
``helpers`` directly with this directory on ``sys.path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
