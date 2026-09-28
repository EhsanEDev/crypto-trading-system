"""UI core tests (framework-agnostic logic)."""

from __future__ import annotations

import pandas as pd
import pytest

from crypto_ui.core.calibration import (
    merged_config,
    recompute_regimes,
    regime_distribution,
)
from crypto_ui.core.dataset import available_symbols, load_symbol_data
from crypto_ui.core.presets import PresetStore


def _sample_regimes_artifact(tmp_path, symbol="TESTUSDT"):
    return _build(tmp_path, symbol)


def test_available_symbols_and_load(tmp_path):
    frame, _ = _sample_regimes_artifact(tmp_path)
    symbols = available_symbols(tmp_path, "futures")
    assert "TESTUSDT" in symbols
    loaded = load_symbol_data("TESTUSDT", "futures", research_data_dir=str(tmp_path))
    assert loaded.equals(frame)


def _build(tmp_path, symbol="TESTUSDT"):
    import numpy as np
    from crypto_research.config import RegimeConfig
    from crypto_research.regime.detector import detect_regime

    n = 300
    index = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.006, n)))
    ohlcv = pd.DataFrame(
        {"open": close * 0.999, "high": close * 1.002, "low": close * 0.998,
         "close": close, "volume": 100.0}, index=index)
    frame = detect_regime(ohlcv, RegimeConfig())
    path = tmp_path / "processed" / "bitunix" / "futures" / symbol
    path.mkdir(parents=True)
    frame.to_parquet(path / "4h_regimes.parquet")
    return frame, ohlcv


def test_calibration_zero_overrides_matches_stored_artifact(tmp_path):
    """UI recalibration with no overrides must reproduce the stored artifact
    labels exactly (same pure detector, same config)."""
    stored, ohlcv = _sample_regimes_artifact(tmp_path)
    recalibrated = recompute_regimes(ohlcv, overrides=None)
    assert recalibrated.frame["regime"].equals(stored["regime"])


def test_calibration_overrides_change_labels(tmp_path):
    stored, ohlcv = _sample_regimes_artifact(tmp_path)
    strict = recompute_regimes(ohlcv, overrides={"adx_trend_threshold": 40})
    relaxed = recompute_regimes(ohlcv, overrides={"adx_trend_threshold": 5})
    # stricter ADX threshold -> fewer trend labels; relaxed -> more
    dist_strict = regime_distribution(strict.frame)
    dist_relaxed = regime_distribution(relaxed.frame)
    assert (dist_strict["TREND_UP"] + dist_strict["TREND_DOWN"]) <= (
        dist_relaxed["TREND_UP"] + dist_relaxed["TREND_DOWN"]
    )


def test_merged_config_validates() -> None:
    with pytest.raises(ValueError, match="ema_fast"):
        merged_config({"ema_fast": 300, "ema_slow": 200})


def test_preset_store_roundtrip(tmp_path):
    store = PresetStore(tmp_path)
    assert store.list() == []
    store.save("loose_adx", {"adx_trend_threshold": 25.0}, note="test")
    assert "loose_adx" in store.list()
    assert store.load("loose_adx") == {"adx_trend_threshold": 25.0}
    full = store.load_full("loose_adx")
    assert full["fingerprint"] and full["note"] == "test"
    with pytest.raises(FileNotFoundError):
        store.load("missing")
    with pytest.raises(ValueError):
        store.save("bad name!", {})
