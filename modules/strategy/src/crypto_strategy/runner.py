"""Backtest orchestration: adapter -> engine -> metrics -> artifacts.

This is the highest-level entry point used by the CLI. It keeps Strategy
consumption of Research behind ``data.adapter`` only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .backtest.engine import Backtester, BacktestResult
from .config import StrategyConfig
from .data.adapter import load_symbol_data
from .metrics.performance import compute_metrics
from .reports.generator import write_artifacts


@dataclass
class SymbolRun:
    symbol: str
    result: BacktestResult
    metrics: dict
    benchmark_metrics: dict | None
    artifacts: dict[str, Path] = field(default_factory=dict)


def run_symbol_backtest(
    config: StrategyConfig,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    write_reports: bool = True,
) -> SymbolRun:
    data = load_symbol_data(
        config.research_data_dir, symbol,
        market=config.market, regime_timeframe=config.regime_timeframe,
        entry_timeframe=config.entry_timeframe,
    )
    backtester = Backtester(config)
    result = backtester.run(
        symbol=data.symbol, regime_frame=data.regime_frame,
        entry_frame=data.entry_frame, start=start, end=end,
    )

    equity = result.equity_frame
    trades = result.trades_frame
    metrics = compute_metrics(equity, trades)

    benchmark_metrics = _buy_and_hold_metrics(
        data.entry_frame, config.backtest.initial_equity,
        config.execution.fee_rate, config.execution.slippage,
        start, end,
    )

    artifacts: dict[str, Path] = {}
    if write_reports:
        artifacts = write_artifacts(
            config, symbol, result, metrics, benchmark_metrics, start, end,
        )
    return SymbolRun(
        symbol=symbol, result=result, metrics=metrics,
        benchmark_metrics=benchmark_metrics, artifacts=artifacts,
    )


def _buy_and_hold_metrics(
    entry_frame: pd.DataFrame, initial_equity: float, fee_rate: float, slippage: float,
    start: str | None, end: str | None,
) -> dict | None:
    """Buy & Hold benchmark: buy at the first open (fee+slippage), mark at closes."""
    from .backtest.engine import _infer_timeframe, _slice

    window = _slice(entry_frame, start, end)
    if len(window) < 2:
        return None
    first_open = float(window["open"].iloc[0])
    quantity = initial_equity / (first_open * (1.0 + slippage))
    entry_cost = quantity * first_open * (1.0 + slippage) * (1.0 + fee_rate)
    cash_after_buy = initial_equity - entry_cost
    fees_total = quantity * first_open * (1.0 + slippage) * fee_rate

    equity_values = cash_after_buy + quantity * window["close"].to_numpy(dtype=float)
    frame = pd.DataFrame({"equity": equity_values}, index=window.index)
    from .metrics.performance import compute_metrics_from_equity

    metrics = compute_metrics_from_equity(frame, _infer_timeframe(window.index))
    metrics.update(
        {
            "total_fees": fees_total,
            "total_slippage": quantity * slippage * first_open,
            "end_equity": float(equity_values[-1]),
        }
    )
    return metrics
