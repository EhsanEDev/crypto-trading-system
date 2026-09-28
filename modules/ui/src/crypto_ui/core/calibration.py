"""Live calibration: recompute indicators + regimes with config overrides.

Uses ONLY the research module's public, pure API (``detect_regime`` /
``compute_indicators``) — the same functions the CLI uses, so UI results
are byte-consistent with command-line results. No lookahead: the regime
detector itself is strictly point-in-time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from crypto_research.config import RegimeConfig
from crypto_research.regime.detector import detect_regime

BASE_CONFIG_FIELDS = (
    "ema_fast", "ema_slow", "adx_period", "adx_trend_threshold",
    "atr_period", "rsi_period", "volatility_percentile", "volatility_lookback",
    "range_volatility_percentile", "slope_lookback",
)


def base_config() -> RegimeConfig:
    """The repository default thresholds (config/default.yaml values)."""
    return RegimeConfig()


def merged_config(overrides: dict[str, Any] | None) -> RegimeConfig:
    """Baseline config + user overrides (validated by pydantic)."""
    payload = {f: getattr(base_config(), f) for f in BASE_CONFIG_FIELDS}
    payload.update({k: v for k, v in (overrides or {}).items() if k in BASE_CONFIG_FIELDS})
    return RegimeConfig(**payload)


@dataclass
class CalibrationResult:
    """A recalibrated regime frame + the config that produced it."""

    frame: pd.DataFrame  # indicators + regime columns (same schema as the artifact)
    config: RegimeConfig
    overrides: dict[str, Any] = field(default_factory=dict)

    @property
    def regime(self) -> pd.Series:
        return self.frame["regime"]


def recompute_regimes(
    ohlcv: pd.DataFrame, overrides: dict[str, Any] | None = None
) -> CalibrationResult:
    """Recompute indicators + regimes on a 4h OHLCV frame with overrides.

    ``ohlcv`` must be the canonical frame (open/high/low/close/volume,
    UTC index) — e.g. the OHLCV columns of the stored regimes artifact.
    """
    config = merged_config(overrides or {})
    frame = detect_regime(ohlcv, config)
    return CalibrationResult(frame=frame, config=config, overrides=dict(overrides or {}))


def regime_distribution(frame: pd.DataFrame) -> dict[str, float]:
    counts = frame["regime"].value_counts(normalize=True)
    return {label: float(counts.get(label, 0.0) * 100) for label in
            ("TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY", "UNCERTAIN")}


def diff_labels(baseline: pd.Series, candidate: pd.Series) -> dict[str, Any]:
    """Compare two regime label series (aligned indexes) for the Compare tab."""
    assert_index_equal(baseline.index, candidate.index)
    changed = baseline != candidate
    total = len(baseline)
    pairs: dict[str, int] = {}
    for base_label, cand_label in zip(baseline[changed], candidate[changed]):
        key = f"{base_label} -> {cand_label}"
        pairs[key] = pairs.get(key, 0) + 1
    from_regime = baseline[changed].value_counts().to_dict()
    to_regime = candidate[changed].value_counts().to_dict()
    return {
        "changed_candles": int(changed.sum()),
        "changed_pct": float(changed.sum() / total * 100) if total else 0.0,
        "pairs": dict(sorted(pairs.items(), key=lambda kv: -kv[1])),
        "transitions_out_of": from_regime,
        "transitions_into": to_regime,
        "baseline_distribution": regime_distribution(pd.DataFrame({"regime": baseline})),
        "candidate_distribution": regime_distribution(pd.DataFrame({"regime": candidate})),
    }


def assert_index_equal(a: pd.Index, b: pd.Index) -> None:
    if not a.equals(b):
        raise ValueError("label series must share the same index for comparison")
