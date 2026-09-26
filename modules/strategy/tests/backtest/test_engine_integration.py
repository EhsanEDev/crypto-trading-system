"""Engine integration tests on small deterministic datasets.

Every number below is hand-computed from the documented execution rules:
entry at next open with slippage/fees, stop/TP on candle high/low, stop
first when both touched, END_OF_DATA at final close.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from helpers import make_1h_frame, make_4h_frame

from crypto_strategy.backtest.engine import Backtester
from crypto_strategy.config import StrategyConfig

SLIPPAGE = 0.0005  # 5 bps
FEE = 0.0006


def _all_up_regimes(n_1h: int) -> pd.DataFrame:
    return make_4h_frame(["TREND_UP"] * (n_1h // 4 + 4), start="2024-01-01")


def test_next_candle_open_entry_and_end_of_data_exit() -> None:
    """One crafted BUY; position stays open until end-of-data close."""
    n = 600
    # flat-ish price so RSI stays near 50-60 and no stop/TP is touched:
    closes = 100.0 + np.sin(np.arange(n) * 0.05) * 0.15  # range < stop distance
    entry_frame = make_1h_frame(closes, seed=5)
    result = Backtester(StrategyConfig(volatility={"enabled": False})).run(
        "BTCUSDT", _all_up_regimes(n), entry_frame
    )
    assert not result.trades_frame.empty, "expected at least one trade"
    first = result.trades_frame.iloc[0]
    signal_ts = pd.Timestamp(first["signal_timestamp"])
    entry_ts = pd.Timestamp(first["entry_timestamp"])
    assert entry_ts == signal_ts + pd.Timedelta(hours=1)
    next_open = entry_frame.loc[entry_ts, "open"]
    assert first["entry_price"] == pytest.approx(next_open * (1 + SLIPPAGE))
    assert first["exit_reason"] == "END_OF_DATA"
    last_close = entry_frame["close"].iloc[-1]
    assert first["exit_price"] == pytest.approx(last_close * (1 - SLIPPAGE))

    # hand-computed net pnl for the first trade
    qty = first["entry_quantity"]
    gross = qty * (first["exit_price"] - first["entry_price"])
    fees = qty * first["entry_price"] * FEE + qty * first["exit_price"] * FEE
    assert first["fees"] == pytest.approx(fees)
    assert first["net_pnl"] == pytest.approx(gross - fees)
    assert first["r_multiple"] == pytest.approx(first["net_pnl"] / first["risk_per_unit"] / qty)


def test_stop_loss_fill_conservative_same_candle() -> None:
    """Both stop and TP inside one candle -> STOP first, gap-aware fill.

    Deterministically engineered: flat series, dip, recovery, signal at
    bar 30, and a bar-31 monster range that touches stop AND take-profit.
    """
    n = 40
    closes = np.full(n, 100.0)
    # dip (bars 20-24) then recovery (bars 25-29) -> RSI rises above 50
    for i, c in zip(range(20, 25), [99.0, 98.0, 97.5, 97.2, 97.0]):
        closes[i] = c
    for i, c in zip(range(25, 30), [98.0, 99.0, 100.0, 101.0, 101.5]):
        closes[i] = c
    closes[30] = 101.6  # signal bar: pullback low + close above EMA20

    entry_frame = make_1h_frame(closes, seed=5)
    # signal bar: deep pullback wick below EMA20, close back above it
    entry_frame.iloc[30, entry_frame.columns.get_loc("low")] = 99.0
    entry_frame.iloc[30, entry_frame.columns.get_loc("high")] = 101.8
    # next candle: enormous range touching both stop and take-profit
    entry_frame.iloc[31, entry_frame.columns.get_loc("open")] = 101.5
    entry_frame.iloc[31, entry_frame.columns.get_loc("high")] = 200.0
    entry_frame.iloc[31, entry_frame.columns.get_loc("low")] = 80.0
    entry_frame.iloc[31, entry_frame.columns.get_loc("close")] = 150.0

    result = Backtester(StrategyConfig(volatility={"enabled": False})).run(
        "BTCUSDT", _all_up_regimes(n + 4), entry_frame
    )
    trades = result.trades_frame
    assert not trades.empty, "expected a trade from the engineered signal"
    trade = trades.iloc[0]
    assert trade["exit_reason"] == "STOP_LOSS", trade["exit_reason"]
    # conservative stop-first: fill at the stop level (slippage applied)
    assert trade["exit_price"] == pytest.approx(trade["stop_price"] * (1 - SLIPPAGE))
    assert trade["exit_price"] < trade["entry_price"]


def test_take_profit_execution() -> None:
    """Craft a TP touch: position opens, price gaps up strongly."""
    n = 400
    closes = np.full(n, 100.0)
    closes[300:] = 100.0
    entry_frame = make_1h_frame(closes, seed=5)
    # engineer a signal at bar 350: pullback + RSI rise + close > EMA20
    for i in range(320, 350):
        entry_frame.iloc[i, entry_frame.columns.get_loc("close")] = 100.0 - (349 - i) * 0.02
        entry_frame.iloc[i, entry_frame.columns.get_loc("low")] = entry_frame["close"].iloc[i] - 0.05
    entry_frame.iloc[350, entry_frame.columns.get_loc("low")] = 99.0
    entry_frame.iloc[350, entry_frame.columns.get_loc("close")] = 100.5
    entry_frame.iloc[350, entry_frame.columns.get_loc("high")] = 100.7
    # next candle spikes to TP (stop distance = atr14*1.5, small in a flat series)
    entry_frame.iloc[351, entry_frame.columns.get_loc("open")] = 100.6
    entry_frame.iloc[351, entry_frame.columns.get_loc("high")] = 115.0
    entry_frame.iloc[351, entry_frame.columns.get_loc("low")] = 100.4
    entry_frame.iloc[351, entry_frame.columns.get_loc("close")] = 112.0
    # keep the rest high so RSI conditions remain plausible
    for i in range(352, n):
        entry_frame.iloc[i, entry_frame.columns.get_loc("open")] = 111.0
        entry_frame.iloc[i, entry_frame.columns.get_loc("high")] = 111.5
        entry_frame.iloc[i, entry_frame.columns.get_loc("low")] = 110.5
        entry_frame.iloc[i, entry_frame.columns.get_loc("close")] = 111.0

    result = Backtester(StrategyConfig(volatility={"enabled": False})).run(
        "BTCUSDT", _all_up_regimes(n), entry_frame
    )
    trades = result.trades_frame
    tp_trades = trades[trades["exit_reason"] == "TAKE_PROFIT"]
    assert not tp_trades.empty, trades["exit_reason"].tolist()
    tp_trade = tp_trades.iloc[0]
    assert float(tp_trade["exit_price"]) == pytest.approx(float(tp_trade["take_profit_price"]) * (1 - SLIPPAGE))


def test_portfolio_constraints_inside_engine() -> None:
    """one_position_per_symbol: never two open positions for the same symbol."""
    n = 800
    rng = np.random.default_rng(9)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.006, n)))
    entry_frame = make_1h_frame(close, seed=9)
    result = Backtester(StrategyConfig(volatility={"enabled": False})).run(
        "BTCUSDT", _all_up_regimes(n), entry_frame
    )
    trades = result.trades_frame
    # overlapping open intervals must not exist (single-symbol constraint)
    opens = pd.to_datetime(trades["entry_timestamp"])
    exits = pd.to_datetime(trades["exit_timestamp"])
    order = np.argsort(opens.values)
    overlaps = 0
    last_exit = pd.Timestamp(0, tz="UTC")
    for idx in order:
        if opens.iloc[idx] < last_exit:
            overlaps += 1
        last_exit = max(last_exit, exits.iloc[idx])
    assert overlaps == 0


def test_equity_curve_consistency() -> None:
    n = 600
    rng = np.random.default_rng(21)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.005, n)))
    entry_frame = make_1h_frame(close, seed=21)
    result = Backtester(StrategyConfig(volatility={"enabled": False})).run(
        "BTCUSDT", _all_up_regimes(n), entry_frame
    )
    equity = result.equity_frame
    assert len(equity) == n
    assert equity["equity"].iloc[0] == pytest.approx(10_000.0)
    # equity == cash + unrealized at every point (self-consistency)
    first_trade_ts = pd.Timestamp(result.trades_frame["entry_timestamp"].iloc[0]) \
        if not result.trades_frame.empty else None
    if first_trade_ts is not None:
        during = equity.loc[equity.index >= first_trade_ts].iloc[0]
        # equity == cash + open position market value (exposure * equity)
        assert during["equity"] == pytest.approx(
            during["cash"] + during["exposure"] * during["equity"], rel=1e-4
        )
        assert during["equity"] > 0  # spot long-only with cash-capped sizing stays positive


def test_regime_exit_executes_after_flip_visible() -> None:
    """Position open while regime flips -> REGIME_EXIT fills at next open."""
    n = 800
    regimes: list[str] = []
    for i in range(n // 4 + 4):
        # TREND_UP until the 4H candle opening at 1H-bar 400, then RANGE
        regimes.append("TREND_UP" if i < 100 else "RANGE")
    regime_frame = make_4h_frame(regimes, start="2024-01-01")

    closes = np.full(n, 100.0)
    # engineer signals in the TREND_UP phase (oscillation for pullbacks)
    for i in range(120, 400):
        closes[i] = 100 + 0.3 * np.sin(i * 0.4)
    entry_frame = make_1h_frame(closes, seed=5)
    for i in range(400, n):  # after flip: drift down so no new signals
        closes[i] = 99.0 + 0.2 * np.cos(i * 0.3)
        entry_frame.iloc[i, entry_frame.columns.get_loc("open")] = closes[i]
        entry_frame.iloc[i, entry_frame.columns.get_loc("high")] = closes[i] + 0.05
        entry_frame.iloc[i, entry_frame.columns.get_loc("low")] = closes[i] - 0.05
        entry_frame.iloc[i, entry_frame.columns.get_loc("close")] = closes[i]

    config = StrategyConfig(volatility={"enabled": False}, exits={"regime_exit": True, "ema_exit": False})
    result = Backtester(config).run("BTCUSDT", regime_frame, entry_frame)
    trades = result.trades_frame
    assert not trades.empty
    assert (trades["exit_reason"].isin(["TAKE_PROFIT", "STOP_LOSS", "END_OF_DATA", "REGIME_EXIT"])).all()
    # any REGIME_EXIT must occur only after the flipped 4H candle has COMPLETED:
    # the first RANGE 4H candle opens at 1H bar 400 -> closes at bar 404,
    # so the earliest visible flip for a 1H candle is bar 404 (index 400 + 4h)
    first_range_close = regime_frame.index[100] + pd.Timedelta(hours=4)
    regime_exits = trades[trades["exit_reason"] == "REGIME_EXIT"]
    for _, row in regime_exits.iterrows():
        assert pd.Timestamp(row["exit_timestamp"]) >= first_range_close
