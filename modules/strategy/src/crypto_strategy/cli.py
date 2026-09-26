"""CLI for the Strategy + Backtester module (research-only, no live trading).

Commands::

    python -m crypto_strategy backtest --symbol BTCUSDT [--start ...] [--end ...] [--market futures]
    python -m crypto_strategy backtest --all
    python -m crypto_strategy report [--symbol BTCUSDT]     # regenerate summary from stored metrics
    python -m crypto_strategy pipeline --all                # backtest --all + summary
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import load_config
from .utils.logging import setup_logging

app = typer.Typer(
    help="crypto-strategy: strategy v001 backtesting (spot, long-only, research-only).",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _resolve_symbol(config, symbol: str) -> str:
    normalized = symbol.upper()
    if normalized not in config.assets:
        raise typer.BadParameter(f"symbol {normalized!r} is not in configured assets {config.assets}")
    return normalized


@app.command()
def backtest(
    symbol: str = typer.Option(None, "--symbol", help="e.g. BTCUSDT"),
    start: str | None = typer.Option(None, "--start", help="YYYY-MM-DD (UTC, inclusive)"),
    end: str | None = typer.Option(None, "--end", help="YYYY-MM-DD (UTC, whole day included)"),
    all_assets: bool = typer.Option(False, "--all", help="backtest every configured asset"),
    market: str | None = typer.Option(None, "--market", help="futures (default) | spot"),
    config_path: str | None = typer.Option(None, "--config"),
) -> None:
    """Run a deterministic backtest and write reports/artifacts."""
    config = load_config(config_path, market=market)
    setup_logging("INFO")
    symbols = list(config.assets) if all_assets else [_resolve_symbol(config, symbol or "")]

    exit_code = 0
    for sym in symbols:
        try:
            run = _run_one(config, sym, start, end)
            typer.secho(f"[INFO] {sym}: trades={run.metrics.get('trade_count', 0)} "
                        f"return={run.metrics.get('total_return', 0) * 100:.1f}% "
                        f"maxDD={run.metrics.get('max_drawdown', 0) * 100:.1f}% "
                        f"netPnL={run.metrics.get('net_pnl', 0):,.2f}", fg=typer.colors.GREEN)
        except Exception as exc:
            typer.secho(f"[ERROR] {sym}: {exc}", fg=typer.colors.RED, err=True)
            exit_code = 1
    raise typer.Exit(code=exit_code)


@app.command()
def report(
    symbol: str | None = typer.Option(None, "--symbol"),
    market: str | None = typer.Option(None, "--market"),
    config_path: str | None = typer.Option(None, "--config"),
) -> None:
    """Regenerate the cross-symbol summary from stored per-symbol metrics."""
    config = load_config(config_path, market=market)
    setup_logging("INFO")
    reports_dir = Path(__file__).resolve().parents[3] / "reports"
    per_symbol: dict[str, tuple[dict, dict | None]] = {}
    symbols = [_resolve_symbol(config, symbol)] if symbol else list(config.assets)
    for sym in symbols:
        metrics_path = reports_dir / f"{sym}_{config.market}_metrics.json"
        if not metrics_path.exists():
            typer.secho(f"[WARN] no stored metrics for {sym}: {metrics_path}", fg=typer.colors.YELLOW)
            continue
        payload = json.loads(metrics_path.read_text())
        per_symbol[sym] = (payload.get("metrics", {}), payload.get("benchmark"))

    from .reports.generator import build_summary

    summary_path = reports_dir / "backtest_summary.md"
    summary_path.write_text(build_summary(per_symbol, config, None, None), encoding="utf-8")
    typer.echo(f"[INFO] Summary written: {summary_path}")


@app.command()
def pipeline(
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    market: str | None = typer.Option(None, "--market"),
    config_path: str | None = typer.Option(None, "--config"),
) -> None:
    """Backtest every configured asset and write the summary report."""
    config = load_config(config_path, market=market)
    setup_logging("INFO")
    per_symbol: dict[str, tuple[dict, dict | None]] = {}
    exit_code = 0
    for sym in config.assets:
        try:
            run = _run_one(config, sym, start, end)
            per_symbol[sym] = (run.metrics, run.benchmark_metrics)
        except Exception as exc:
            typer.secho(f"[ERROR] {sym}: {exc}", fg=typer.colors.RED, err=True)
            exit_code = 1
    reports_dir = Path(__file__).resolve().parents[3] / "reports"
    summary_path = reports_dir / "backtest_summary.md"
    summary_path.write_text(
        __import__("crypto_strategy.reports.generator", fromlist=["build_summary"])
        .build_summary(per_symbol, config, start, end),
        encoding="utf-8",
    )
    typer.echo(f"[INFO] Summary written: {summary_path}")
    raise typer.Exit(code=exit_code)


def _run_one(config, symbol: str, start: str | None, end: str | None):
    from .runner import run_symbol_backtest

    typer.secho(f"=== Backtest {symbol} ({config.market}) ===", fg=typer.colors.CYAN, bold=True)
    return run_symbol_backtest(config, symbol, start=start, end=end, write_reports=True)


if __name__ == "__main__":
    app()
