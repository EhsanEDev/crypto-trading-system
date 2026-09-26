"""Metrics tests on small deterministic datasets (hand-computed formulas)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from crypto_strategy.metrics.performance import (
    compute_metrics,
    compute_metrics_from_equity,
)


def equity_frame(values: list[float], freq: str = "1h") -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(values), freq=freq, tz="UTC")
    return pd.DataFrame(
        {"equity": values, "cash": values, "exposure": [0.0] * len(values),
         "unrealized_pnl": [0.0] * len(values), "realized_pnl": [0.0] * len(values),
         "drawdown": [0.0] * len(values)},
        index=index,
    )


def test_total_return_and_drawdown_hand_computed() -> None:
    # equity: 1000 -> 1100 -> 900 -> 1200 -> 1080
    frame = equity_frame([1000.0, 1100.0, 900.0, 1200.0, 1080.0])
    metrics = compute_metrics_from_equity(frame, pd.Timedelta(hours=1))
    assert metrics["total_return"] == pytest.approx(0.08)
    # worst peak-to-trough: peak 1100 -> trough 900 = 200/1100
    assert metrics["max_drawdown"] == pytest.approx(200.0 / 1100.0)


def test_max_drawdown_peak_to_trough() -> None:
    frame = equity_frame([100.0, 120.0, 60.0, 90.0])
    metrics = compute_metrics_from_equity(frame, pd.Timedelta(hours=1))
    assert metrics["max_drawdown"] == pytest.approx(0.5)


def test_trade_metrics_hand_computed() -> None:
    frame = equity_frame([10_000.0] * 5)
    trades = pd.DataFrame(
        {
            "net_pnl": [200.0, -100.0, 300.0, -100.0, 100.0],
            "fees": [1.0, 1.0, 1.0, 1.0, 1.0],
            "slippage": [0.5, 0.5, 0.5, 0.5, 0.5],
            "gross_pnl": [201.5, -98.5, 301.5, -98.5, 101.5],
            "r_multiple": [2.0, -1.0, 3.0, -1.0, 1.0],
        }
    )
    metrics = compute_metrics(frame, trades)
    assert metrics["trade_count"] == 5
    assert metrics["win_rate"] == pytest.approx(3 / 5)
    # profit factor = gross profit / |gross loss| = 600/200
    assert metrics["profit_factor"] == pytest.approx(3.0)
    # expectancy = (0.6*200) - (0.4*100)
    assert metrics["expectancy"] == pytest.approx(0.6 * 200 - 0.4 * 100)
    assert metrics["average_win"] == pytest.approx(200.0)
    assert metrics["average_loss"] == pytest.approx(-100.0)
    assert metrics["largest_win"] == pytest.approx(300.0)
    assert metrics["largest_loss"] == pytest.approx(-100.0)
    assert metrics["max_losing_streak"] == 1
    assert metrics["average_r"] == pytest.approx(0.8)
    assert metrics["total_fees"] == pytest.approx(5.0)
    assert metrics["total_slippage"] == pytest.approx(2.5)
    assert metrics["net_pnl"] == pytest.approx(400.0)


def test_losing_streak_counted() -> None:
    frame = equity_frame([10_000.0] * 8)
    trades = pd.DataFrame(
        {
            "net_pnl": [-10.0, -20.0, -30.0, 5.0, -40.0, -50.0, 60.0, 10.0],
            "fees": [0.0] * 8, "slippage": [0.0] * 8, "gross_pnl": [0.0] * 8,
            "r_multiple": [0.0] * 8,
        }
    )
    metrics = compute_metrics(frame, trades)
    assert metrics["max_losing_streak"] == 3


def test_sharpe_annualization_documented() -> None:
    # 24 periods of +1% then -1% alternating; annualization = sqrt(24*365)
    values = np.concatenate([[10_000.0], np.tile([10_100.0, 10_000.0], 12)])
    frame = equity_frame(values.tolist())
    metrics = compute_metrics_from_equity(frame, pd.Timedelta(hours=1))
    returns = pd.Series(values).pct_change().dropna()
    expected = float(returns.mean() / returns.std(ddof=0) * math.sqrt(24 * 365))
    assert metrics["sharpe"] == pytest.approx(expected)
    assert metrics["annualization_periods_per_year"] == pytest.approx(24 * 365)


def test_cagr_hand_computed() -> None:
    # 24*365 samples: doubling equity -> CAGR = 100% per year
    n = 24 * 365
    values = [10_000.0 * (2.0 ** (i / (n - 1))) for i in range(n)]
    frame = equity_frame(values)
    metrics = compute_metrics_from_equity(frame, pd.Timedelta(hours=1))
    assert metrics["cagr"] == pytest.approx(1.0, rel=1e-3)


def test_no_trades_zero_trade_metrics() -> None:
    frame = equity_frame([10_000.0, 10_100.0])
    metrics = compute_metrics(frame, pd.DataFrame())
    assert metrics["trade_count"] == 0
    assert metrics["total_fees"] == 0.0
    assert metrics["net_pnl"] == 0.0
