"""Performance metrics.

Formulas (all computed on the strategy's own equity curve, after fees and
slippage; the equity is sampled once per 1H candle close):

    total_return   = equity_end / equity_start - 1
    cagr           = (equity_end / equity_start) ** (periods_per_year / n) - 1
                     with n = number of equity samples and periods_per_year
                     = 24 * 365 (crypto trades 24/7; sampling = 1H bars)
    max_drawdown   = max over t of (peak_equity(t) - equity(t)) / peak_equity(t)
    returns        = pct_change of the equity series
    sharpe         = mean(returns) / std(returns, ddof=0) * sqrt(periods_per_year)
                     (risk-free rate assumed 0; documented assumption)
    sortino        = mean(returns) / downside_std * sqrt(periods_per_year)
                     where downside_std = std of negative returns only
                     (zeros excluded; NaN when no losing periods)
    win_rate       = winning_trades / closed_trades  (net pnl > 0)
    profit_factor  = gross_profit / abs(gross_loss)  (net pnl sums; inf when no losses)
    expectancy     = (win_rate * avg_win) - (loss_rate * avg_loss)
    average_r      = mean of trade r_multiple
    exposure       = mean of per-candle exposure (open notional / equity)

Buy & Hold benchmark: same metrics computed on a synthetic equity curve
that buys quantity = initial_equity / first_open at the first candle open
(including the same fee/slippage) and marks to market at every close.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS_PER_YEAR_1H = 24 * 365  # crypto markets trade 24/7; 1H sampling


def compute_metrics_from_equity(equity: pd.DataFrame, sampling_period: pd.Timedelta) -> dict:
    """Equity-curve-only metrics (drawdown, returns, sharpe, sortino, CAGR)."""
    if equity.empty:
        return {}
    equity_values = equity["equity"].to_numpy(dtype=float)
    start_equity = equity_values[0]
    end_equity = equity_values[-1]
    n = len(equity_values)

    running_peak = np.maximum.accumulate(equity_values)
    drawdowns = (equity_values - running_peak) / running_peak
    max_drawdown = float(-drawdowns.min()) if n else 0.0

    returns = pd.Series(equity_values).pct_change().dropna()
    periods_per_year = PERIODS_PER_YEAR_1H if sampling_period == pd.Timedelta(hours=1) else (
        pd.Timedelta(days=365) / sampling_period
        if sampling_period > pd.Timedelta(0) else PERIODS_PER_YEAR_1H
    )
    sharpe = _sharpe(returns, periods_per_year)
    sortino = _sortino(returns, periods_per_year)
    cagr = _cagr(start_equity, end_equity, n, periods_per_year)

    return {
        "samples": int(n),
        "total_return": float(end_equity / start_equity - 1) if start_equity > 0 else 0.0,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "sortino": sortino,
        "start_equity": float(start_equity),
        "end_equity": float(end_equity),
        "annualization_periods_per_year": float(periods_per_year),
    }


def compute_metrics(
    equity: pd.DataFrame, trades: pd.DataFrame, exposure_series: pd.Series | None = None,
    sampling_period: pd.Timedelta = pd.Timedelta(hours=1),
) -> dict:
    """Full metric set: equity-curve metrics + trade-based metrics."""
    result = compute_metrics_from_equity(equity, sampling_period)
    if equity.empty:
        return result
    exposure_col = "exposure" if "exposure" in equity.columns else None
    if exposure_col:
        result["exposure"] = float(equity[exposure_col].mean())
    if trades is None or trades.empty:
        result.update(_empty_trade_metrics())
        return result

    net_pnl = trades["net_pnl"].astype(float)
    wins = net_pnl[net_pnl > 0]
    losses = net_pnl[net_pnl < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(losses.sum())
    trade_count = int(len(trades))
    win_rate = float(len(wins) / trade_count) if trade_count else 0.0
    loss_rate = float(len(losses) / trade_count) if trade_count else 0.0
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0  # negative value

    # longest losing streak (consecutive net pnl < 0)
    streak = max_streak = 0
    for value in net_pnl:
        if value < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    result.update(
        {
            "trade_count": trade_count,
            "win_rate": win_rate,
            "profit_factor": (gross_profit / abs(gross_loss)) if gross_loss < 0 else float("inf"),
            "expectancy": (win_rate * avg_win) - (loss_rate * abs(avg_loss)) if trade_count else 0.0,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "largest_win": float(wins.max()) if len(wins) else 0.0,
            "largest_loss": float(losses.min()) if len(losses) else 0.0,
            "max_losing_streak": max_streak,
            "average_r": float(trades["r_multiple"].astype(float).mean()) if trade_count else 0.0,
            "total_fees": float(trades["fees"].astype(float).sum()),
            "total_slippage": float(trades["slippage"].astype(float).sum()),
            "gross_pnl": float(trades["gross_pnl"].astype(float).sum()),
            "net_pnl": float(net_pnl.sum()),
        }
    )
    return result


def _sharpe(returns: pd.Series, periods_per_year: float) -> float:
    if len(returns) < 2 or returns.std(ddof=0) == 0:
        return float("nan")
    return float(returns.mean() / returns.std(ddof=0) * np.sqrt(periods_per_year))


def _sortino(returns: pd.Series, periods_per_year: float) -> float:
    downside = returns[returns < 0]
    if len(returns) < 2 or len(downside) == 0:
        return float("nan")
    downside_std = downside.std(ddof=0)
    if downside_std == 0:
        return float("nan")
    return float(returns.mean() / downside_std * np.sqrt(periods_per_year))


def _cagr(start: float, end: float, n: int, periods_per_year: float) -> float:
    if start <= 0 or end <= 0 or n <= 1:
        return float("nan")
    return float((end / start) ** (periods_per_year / n) - 1)


def _empty_trade_metrics() -> dict:
    return {
        "trade_count": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "expectancy": 0.0,
        "average_win": 0.0,
        "average_loss": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "max_losing_streak": 0,
        "average_r": 0.0,
        "total_fees": 0.0,
        "total_slippage": 0.0,
        "gross_pnl": 0.0,
        "net_pnl": 0.0,
        "exposure": 0.0,
    }
