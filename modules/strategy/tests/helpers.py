"""Deterministic synthetic data builders for strategy tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_1h_frame(
    closes: np.ndarray | list[float],
    spread_pct: float = 0.002,
    start: str = "2024-01-01",
    seed: int = 7,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = np.asarray(closes, dtype=float)
    n = len(close)
    open_ = close * (1 + rng.normal(0, 0.0005, n))
    high = np.maximum(open_, close) * (1 + spread_pct)
    low = np.minimum(open_, close) * (1 - spread_pct)
    index = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.integers(50, 500, n).astype(float)},
        index=index,
    )


def make_4h_frame(
    regimes: list[str],
    start: str = "2024-01-01 00:00",
    base_price: float = 100.0,
) -> pd.DataFrame:
    """4H regimes artifact with the full contract column set."""
    n = len(regimes)
    rng = np.random.default_rng(11)
    index = pd.date_range(start, periods=n, freq="4h", tz="UTC")
    close = base_price * (1 + 0.01 * np.sin(np.arange(n) * 0.3))
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.003,
            "low": close * 0.997,
            "close": close,
            "volume": rng.integers(100, 900, n).astype(float),
            "quote_volume": close * 100.0,
            "ema50": close * 0.99,
            "ema200": close * 0.98,
            "atr14": close * 0.01,
            "atr_pct": [1.0] * n,
            "rsi14": [55.0] * n,
            "adx14": [25.0] * n,
            "adx_plus_di": [20.0] * n,
            "adx_minus_di": [10.0] * n,
            "regime": regimes,
            "trend_condition": [r == "TREND_UP" for r in regimes],
            "volatility_condition": [False] * n,
            "range_condition": [r == "RANGE" for r in regimes],
            "regime_reason": [f"synthetic {r}" for r in regimes],
            "regime_flags": ["{}"] * n,
        },
        index=index,
    )


def constant_up_regimes(n: int) -> list[str]:
    return ["TREND_UP"] * n


def candle_row(ts: str, o: float, h: float, low: float, c: float) -> dict:
    return {"timestamp": pd.Timestamp(ts, tz="UTC"), "open": o, "high": h, "low": low, "close": c}
