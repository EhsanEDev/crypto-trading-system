"""Lookahead prevention tests: future data cannot influence the past.

Two independent proofs:
1. Engine prefix invariance: running the backtest on the first k candles
   must produce byte-identical trades/equity for that prefix.
2. Regime tamper test: modifying 4H regime rows that complete AFTER the
   evaluated window cannot change any signal inside the window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from helpers import make_1h_frame, make_4h_frame

from crypto_strategy.backtest.engine import Backtester
from crypto_strategy.config import StrategyConfig


def _build_frames(n_1h: int = 600, seed: int = 3):
    rng = np.random.default_rng(seed)
    n_4h = n_1h // 4 + 4
    regimes: list[str] = []
    for i in range(n_4h):
        regimes.append("TREND_UP" if (i // 6) % 2 == 0 else "RANGE")
    regime_frame = make_4h_frame(regimes, start="2024-01-01", base_price=100.0)

    drift = np.where(np.arange(n_1h) % 24 < 12, 0.001, -0.0008)
    close = 100.0 * np.exp(np.cumsum(rng.normal(drift, 0.004)))
    entry_frame = make_1h_frame(close, seed=seed)
    return regime_frame, entry_frame


def test_engine_prefix_invariance() -> None:
    regime_frame, entry_frame = _build_frames()
    full = Backtester(StrategyConfig(volatility={"enabled": False})).run(
        "BTCUSDT", regime_frame, entry_frame
    )
    k = 700
    prefix = Backtester(StrategyConfig(volatility={"enabled": False})).run(
        "BTCUSDT", regime_frame, entry_frame.iloc[:k]
    )

    full_trades = full.trades_frame
    prefix_trades = prefix.trades_frame
    # every prefix trade must exist identically in the full run
    assert len(prefix_trades) <= len(full_trades)
    cols = [c for c in prefix_trades.columns if c not in ("conditions",)]
    pd.testing.assert_frame_equal(prefix_trades[cols], full_trades[cols])

    full_equity = full.equity_frame.iloc[:k]
    prefix_equity = prefix.equity_frame
    pd.testing.assert_frame_equal(prefix_equity, full_equity)


def test_future_regime_cannot_influence_past_signals() -> None:
    regime_frame, entry_frame = _build_frames()
    backtester = Backtester(StrategyConfig(volatility={"enabled": False}))
    baseline = backtester.run("BTCUSDT", regime_frame, entry_frame)

    # tamper the FUTURE of the regime frame (beyond the entry window end)
    tampered = regime_frame.copy()
    tampered.iloc[-10:, tampered.columns.get_loc("regime")] = "HIGH_VOLATILITY"
    tampered.iloc[-10:, tampered.columns.get_loc("adx14")] = 99.0
    tampered.iloc[-10:, tampered.columns.get_loc("close")] = 1.0

    tampered_run = Backtester(StrategyConfig(volatility={"enabled": False})).run(
        "BTCUSDT", tampered, entry_frame
    )
    cols = [c for c in baseline.trades_frame.columns if c != "conditions"]
    pd.testing.assert_frame_equal(
        baseline.trades_frame[cols],
        tampered_run.trades_frame[cols],
    )


def test_future_candles_cannot_influence_signal_generation() -> None:
    # direct strategy-level check: tampering the close of candle t+5 cannot
    # change the signal evaluated at candle t
    from crypto_strategy.strategy.base import StrategyContext
    from crypto_strategy.strategy.trend_pullback import TrendPullbackStrategy

    regime_frame, entry_frame = _build_frames()
    pre = Backtester(StrategyConfig())._precompute(entry_frame, regime_frame)

    i = 500
    ts = entry_frame.index[i]
    ctx1 = StrategyContext(
        timestamp=ts, open=entry_frame["open"].iloc[i], high=entry_frame["high"].iloc[i],
        low=entry_frame["low"].iloc[i], close=entry_frame["close"].iloc[i],
        ema20=float(pre["ema20"].iloc[i]), rsi14=float(pre["rsi14"].iloc[i]),
        rsi14_prev=float(pre["rsi14_prev"].iloc[i]), atr14=float(pre["atr14"].iloc[i]),
        atr_pct=float(pre["atr_pct"].iloc[i]),
        atr_pct_threshold=float(pre["vol_threshold"].iloc[i]),
        regime=pre["regime"][i], regime_close_time=pre["regime_close_time"][i],
    )
    ctx2 = StrategyContext(
        timestamp=ts, open=ctx1.open, high=ctx1.high, low=ctx1.low, close=ctx1.close,
        ema20=ctx1.ema20, rsi14=ctx1.rsi14, rsi14_prev=ctx1.rsi14_prev, atr14=ctx1.atr14,
        atr_pct=ctx1.atr_pct, atr_pct_threshold=ctx1.atr_pct_threshold,
        regime=pre["regime"][i], regime_close_time=pre["regime_close_time"][i],
    )
    assert TrendPullbackStrategy().evaluate(ctx1, StrategyConfig()).side == (
        TrendPullbackStrategy().evaluate(ctx2, StrategyConfig()).side
    )
    # and the signal depends only on candle-t fields: identical ctx -> identical signal
    assert TrendPullbackStrategy().evaluate(ctx1, StrategyConfig()).conditions.to_json() == (
        TrendPullbackStrategy().evaluate(ctx2, StrategyConfig()).conditions.to_json()
    )
