"""Report generation: markdown backtest reports + metrics/trades/equity artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..backtest.engine import BacktestResult
from ..config import StrategyConfig

ASSUMPTIONS = [
    "Signals are evaluated at candle close; entries/exits execute at the NEXT candle open.",
    "Long entry fills at next_open * (1 + slippage); exits fill at the trigger level * (1 - slippage).",
    "If a candle gaps through a stop, the fill happens at the candle open (worse than the stop level).",
    "If a candle touches BOTH stop and take-profit, the stop is assumed to trigger first (conservative).",
    "A pending order is never cancelled in v001; it fills at the next available candle open.",
    "Positions opened at a candle open can be stopped out within that same candle.",
    "End of data closes open positions at the final close (END_OF_DATA).",
    "Data gaps are not forward-filled; the next available candle is used (gap count reported).",
]


def _fmt(value: Any, kind: str = "float") -> str:
    if value is None or (isinstance(value, float) and (value != value)):  # NaN
        return "n/a"
    if isinstance(value, float) and value in (float("inf"), float("-inf")):
        return "inf"
    if kind == "pct":
        return f"{value * 100:.1f}%"
    if kind == "money":
        return f"{value:,.2f}"
    if kind == "ratio":
        return f"{value:.3f}"
    return str(value)


def build_backtest_report(
    symbol: str,
    result: BacktestResult,
    metrics: dict,
    benchmark_metrics: dict | None,
    start: str | None,
    end: str | None,
) -> str:
    config = result.config
    trades = result.trades_frame
    lines: list[str] = []
    lines.append(f"# {symbol} — {config.market} Backtest Report")
    lines.append("")
    lines.append(f"Strategy: **{config.strategy_name} {config.strategy_version}** "
                 f"(spot, long-only, 4H regime + 1H entry)")
    lines.append("")
    lines.append("> Backtest results are experimental and do not imply future profitability.")
    lines.append("")

    lines.append("## Run")
    lines.append("")
    lines.append(f"- Date range: `{start or 'full history'} → {end or 'latest'}`")
    lines.append(f"- Equity samples: {len(result.equity_points):,} (1H closes)")
    lines.append(f"- Regime source: research 4h regimes artifact "
                 f"(`modules/research/data`, market `{config.market}`)")
    lines.append("")

    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for key, label in (
        ("total_return", "Total Return"), ("cagr", "CAGR"), ("max_drawdown", "Max Drawdown"),
        ("sharpe", "Sharpe (1H sampling, rf=0)"), ("sortino", "Sortino"),
        ("trade_count", "Trades"), ("win_rate", "Win Rate"), ("profit_factor", "Profit Factor"),
        ("expectancy", "Expectancy (net, $)"), ("average_r", "Average R"),
        ("average_win", "Average Win ($)"), ("average_loss", "Average Loss ($)"),
        ("largest_win", "Largest Win ($)"), ("largest_loss", "Largest Loss ($)"),
        ("max_losing_streak", "Max Losing Streak"), ("exposure", "Exposure (mean)"),
        ("total_fees", "Total Fees ($)"), ("total_slippage", "Total Slippage ($)"),
        ("gross_pnl", "Gross PnL ($)"), ("net_pnl", "Net PnL ($)"),
        ("end_equity", "End Equity ($)"),
    ):
        kind = "pct" if key in ("total_return", "cagr", "max_drawdown", "win_rate", "exposure") else "money"
        if key in ("average_r", "sharpe", "sortino", "profit_factor", "max_losing_streak"):
            kind = "ratio" if key not in ("profit_factor",) else "ratio"
        lines.append(f"| {label} | {_fmt(metrics.get(key), kind)} |")
    lines.append("")

    if benchmark_metrics:
        lines.append("## Benchmark: Buy & Hold")
        lines.append("")
        lines.append("| Metric | Strategy | Buy & Hold |")
        lines.append("| --- | --- | --- |")
        for key in ("total_return", "cagr", "max_drawdown", "sharpe"):
            kind = "pct" if key in ("total_return", "cagr", "max_drawdown") else "ratio"
            lines.append(
                f"| {key} | {_fmt(metrics.get(key), kind)} | {_fmt(benchmark_metrics.get(key), kind)} |"
            )
        lines.append("")

    lines.append("## Trades")
    lines.append("")
    if trades.empty:
        lines.append("_No closed trades in this window._")
    else:
        by_reason = trades["exit_reason"].value_counts().to_dict()
        lines.append(f"- Closed trades: **{len(trades)}** — exits: {by_reason}")
        lines.append("")
        lines.append("| # | Signal ts | Entry ts | Entry | Stop | TP | Exit ts | Exit | Reason | Net PnL | R |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for _, row in trades.iterrows():
            lines.append(
                f"| {int(row['trade_id'])} | {row['signal_timestamp']:%m-%d %H:%M} "
                f"| {row['entry_timestamp']:%m-%d %H:%M} | {row['entry_price']:.2f} "
                f"| {row['stop_price']:.2f} | {row['take_profit_price']:.2f} "
                f"| {row['exit_timestamp']:%m-%d %H:%M} | {row['exit_price']:.2f} "
                f"| {row['exit_reason']} | {row['net_pnl']:+.2f} | {row['r_multiple']:+.2f} |"
            )
        lines.append("")

    lines.append("## Trade audit example")
    lines.append("")
    if not trades.empty:
        row = trades.iloc[0]
        lines.append("```json")
        lines.append(json.dumps({
            "trade_id": int(row["trade_id"]),
            "entry_conditions": json.loads(row["conditions"]),
            "context": {k: row[k] for k in row.index if k.startswith("context_")},
            "regime": row["context_regime"],
        }, indent=2, default=str))
        lines.append("```")
    else:
        lines.append("_n/a_")
    lines.append("")

    lines.append("## Assumptions")
    lines.append("")
    for assumption in ASSUMPTIONS:
        lines.append(f"- {assumption}")
    lines.append("")

    lines.append("## Configuration")
    lines.append("")
    lines.append("```yaml")
    lines.append(json.dumps(json.loads(config.model_dump_json()), indent=2, default=str))
    lines.append("```")
    lines.append("")

    if result.warnings:
        lines.append("## Warnings")
        lines.append("")
        gap_count = sum(1 for w in result.warnings if "data gap" in w)
        lines.append(f"- Data gaps detected: {gap_count} (not forward-filled)")
        for warning in result.warnings[:10]:
            lines.append(f"- {warning}")
        if len(result.warnings) > 10:
            lines.append(f"- ... and {len(result.warnings) - 10} more")
        lines.append("")

    if result.rejected_orders:
        lines.append("## Rejected orders")
        lines.append("")
        reasons: dict[str, int] = {}
        for item in result.rejected_orders:
            reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {count}× {reason}")
        lines.append("")

    return "\n".join(lines)


def build_summary(
    per_symbol: dict[str, tuple[dict, dict | None]],
    config: StrategyConfig,
    start: str | None,
    end: str | None,
) -> str:
    lines: list[str] = []
    lines.append("# Backtest Summary")
    lines.append("")
    lines.append(f"Strategy: **{config.strategy_name} {config.strategy_version}** | "
                 f"market: `{config.market}` | range: `{start or 'full'} → {end or 'latest'}`")
    lines.append("")
    lines.append("> Backtest results are experimental and do not imply future profitability.")
    lines.append("")
    lines.append("| Symbol | Trades | Win Rate | Total Return | CAGR | Max DD | Sharpe | Net PnL | Fees | BH Return |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for symbol, (metrics, benchmark) in per_symbol.items():
        bh = (benchmark or {}).get("total_return")
        lines.append(
            f"| {symbol} | {metrics.get('trade_count', 0)} "
            f"| {_fmt(metrics.get('win_rate'), 'pct')} "
            f"| {_fmt(metrics.get('total_return'), 'pct')} "
            f"| {_fmt(metrics.get('cagr'), 'pct')} "
            f"| {_fmt(metrics.get('max_drawdown'), 'pct')} "
            f"| {_fmt(metrics.get('sharpe'), 'ratio')} "
            f"| {_fmt(metrics.get('net_pnl'), 'money')} "
            f"| {_fmt(metrics.get('total_fees'), 'money')} "
            f"| {_fmt(bh, 'pct')} |"
        )
    lines.append("")
    lines.append("Assumptions: " + " ".join(f"- {a}" for a in ASSUMPTIONS))
    lines.append("")
    return "\n".join(lines)


def write_artifacts(
    config: StrategyConfig,
    symbol: str,
    result: BacktestResult,
    metrics: dict,
    benchmark_metrics: dict | None,
    start: str | None,
    end: str | None,
    reports_dir: Path | None = None,
) -> dict[str, Path]:
    """Write {SYMBOL}_backtest.md, metrics.json, trades.parquet, equity.parquet."""
    reports_dir = reports_dir or (Path(__file__).resolve().parents[3] / "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    report_path = reports_dir / f"{symbol}_{config.market}_backtest.md"
    report_path.write_text(
        build_backtest_report(symbol, result, metrics, benchmark_metrics, start, end),
        encoding="utf-8",
    )
    written["report"] = report_path

    metrics_path = reports_dir / f"{symbol}_{config.market}_metrics.json"
    payload: dict[str, Any] = {
        "strategy": {
            "name": config.strategy_name,
            "version": config.strategy_version,
            "market": config.market,
            "symbol": symbol,
            "timeframes": {"regime": config.regime_timeframe, "entry": config.entry_timeframe},
        },
        "range": {"start": start, "end": end},
        "config": json.loads(config.model_dump_json()),
        "metrics": metrics,
        "benchmark": benchmark_metrics,
        "warnings": result.warnings,
        "assumptions": ASSUMPTIONS,
    }
    metrics_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    written["metrics"] = metrics_path

    trades_frame = result.trades_frame
    trades_path = reports_dir / f"{symbol}_{config.market}_trades.parquet"
    if trades_frame.empty:
        pd.DataFrame({"trade_id": pd.Series(dtype="int64")}).to_parquet(trades_path)
    else:
        trades_frame.to_parquet(trades_path, index=False)
    written["trades"] = trades_path

    equity_frame = result.equity_frame
    equity_path = reports_dir / f"{symbol}_{config.market}_equity.parquet"
    equity_frame.to_parquet(equity_path)
    written["equity"] = equity_path
    return written
