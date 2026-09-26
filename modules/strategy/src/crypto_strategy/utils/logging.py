"""Logging setup for the strategy module."""

from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        for handler in root.handlers:
            handler.setLevel(level.upper())
        root.setLevel(level.upper())
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root.addHandler(handler)
    root.setLevel(level.upper())
