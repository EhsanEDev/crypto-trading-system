"""Strategy-local indicator computation for the 1H entry timeframe.

Deliberate duplication of research formulas (module independence contract):
Strategy must never import ``crypto_research``; it computes the few
indicators it needs on the OHLCV data contract it consumes. Conventions
are documented here and mirror the research module so numbers agree:

* EMA: SMA-seeded, ``alpha = 2/(period+1)``; first value at bar
  ``period - 1`` (bars before are NaN — honest warm-up).
* RSI: Wilder, SMA seed of the first ``period`` deltas, mean-preserving
  recursion; first value at bar ``period``. Zero-gain+zero-loss windows
  yield NaN (undefined RS).
* ATR: Wilder in the TA-Lib ``ta_ATR.c`` convention: first ATR at bar
  ``period`` = mean(TR of bars 1..period), then mean-preserving recursion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    if series.isna().any():
        raise ValueError("ema() requires a series without NaN values")
    values = series.to_numpy(dtype=float)
    n = len(values)
    out = np.full(n, np.nan)
    if n < period:
        return pd.Series(out, index=series.index)
    out[period - 1] = values[:period].mean()
    alpha = 2.0 / (period + 1)
    for i in range(period, n):
        out[i] = out[i - 1] + alpha * (values[i] - out[i - 1])
    return pd.Series(out, index=series.index)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    if series.isna().any():
        raise ValueError("rsi() requires a series without NaN values")
    close = series.astype(float)
    delta = close.diff().iloc[1:]
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    def smooth(values: pd.Series) -> pd.Series:
        arr = values.to_numpy(dtype=float)
        n = len(arr)
        out = np.full(n, np.nan)
        if n < period:
            return pd.Series(out, index=values.index)
        out[period - 1] = arr[:period].mean()
        inv = 1.0 / period
        for i in range(period, n):
            out[i] = out[i - 1] + inv * (arr[i] - out[i - 1])
        return pd.Series(out, index=values.index)

    avg_gain = smooth(gain)
    avg_loss = smooth(loss)
    with np.errstate(invalid="ignore", divide="ignore"):
        denom = avg_gain + avg_loss
        values = np.where(denom > 0, 100.0 * avg_gain / denom, np.nan)
    result = pd.Series(np.nan, index=close.index)
    result.iloc[1:] = values
    return result


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    tr = tr.astype(float)
    if len(df) > 0:
        tr.iloc[0] = float(df["high"].iloc[0] - df["low"].iloc[0])
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR (Wilder, TA-Lib convention): first value at bar ``period``."""
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    tr = true_range(df).to_numpy(dtype=float)
    n = len(tr)
    out = np.full(n, np.nan)
    if n < period + 1:
        return pd.Series(out, index=df.index)
    out[period] = tr[1 : period + 1].mean()
    for t in range(period + 1, n):
        out[t] = (out[t - 1] * (period - 1) + tr[t]) / period
    return pd.Series(out, index=df.index)


def rolling_percentile_threshold(
    series: pd.Series, lookback: int, percentile: float
) -> pd.Series:
    """Past-only rolling percentile of ``series``.

    At bar ``t`` the threshold is the ``percentile`` of the series over
    bars ``t-lookback .. t-1`` (``shift(1)`` trailing window) — the current
    bar can never set its own threshold. NaN until the window is full.
    """
    return series.shift(1).rolling(lookback, min_periods=lookback).quantile(percentile / 100.0)
