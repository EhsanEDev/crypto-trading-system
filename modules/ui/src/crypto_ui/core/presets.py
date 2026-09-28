"""Preset store: named calibration presets with provenance.

Presets are YAML files under ``configs/presets/`` at the repository root;
they contain the overrides plus a config fingerprint so every experiment
stays reproducible (and is directly usable with the research CLI:
``python -m crypto_research report --config configs/presets/X.yaml``).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from crypto_research.config import PROJECT_ROOT as RESEARCH_PROJECT_ROOT

PRESETS_DIR = Path(RESEARCH_PROJECT_ROOT).parents[1] / "configs" / "presets"


class PresetStore:
    def __init__(self, presets_dir: Path | str | None = None) -> None:
        self.dir = Path(presets_dir) if presets_dir else PRESETS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.dir.glob("*.yaml"))

    def save(self, name: str, overrides: dict[str, Any], note: str = "") -> Path:
        if not name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"preset name {name!r} must be alphanumeric/dash")
        payload = {
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "fingerprint": _fingerprint(overrides),
            "overrides": overrides,
            "note": note,
        }
        path = self.dir / f"{name}.yaml"
        tmp = path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, name: str) -> dict[str, Any]:
        path = self.dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"preset {name!r} not found in {self.dir}")
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return payload.get("overrides", {})

    def load_full(self, name: str) -> dict[str, Any]:
        path = self.dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"preset {name!r} not found")
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _fingerprint(overrides: dict[str, Any]) -> str:
    payload = json.dumps(overrides, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]
