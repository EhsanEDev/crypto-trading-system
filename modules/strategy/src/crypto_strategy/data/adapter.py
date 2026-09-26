"""Research integration adapter — the boundary between the modules.

Strategy consumes Research *outputs* (parquet files + documented columns)
through this adapter only. It must never import ``crypto_research``:
replacing Research with another provider means replacing this file.

Research data contract (produced by the research module, stable):
    raw candles:
        modules/research/data/raw/bitunix/{market}/{SYMBOL}/{tf}.parquet
        index: timestamp (UTC), columns: open high low close volume
        (+ optional quote_volume) — CLOSED candles only.
    4h regime artifact:
        modules/research/data/processed/bitunix/{market}/{SYMBOL}/4h_regimes.parquet
        index: timestamp (UTC, 4h candle OPEN time), columns include:
        open high low close volume, ema50, ema200, atr14, atr_pct,
        rsi14, adx14, regime (TREND_UP/TREND_DOWN/RANGE/HIGH_VOLATILITY/
        UNCERTAIN), regime_reason, regime_flags.

4H candles are indexed by OPEN time; a 4H candle opening at T covers
[T, T+4h). A 4H candle is *completed* for a 1H candle opening at t when
T + 4h <= t. The alignment helper below implements exactly that rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REGIME_LABELS = {"TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY", "UNCERTAIN"}
REQUIRED_REGIME_COLUMNS = ("close", "ema50", "ema200", "atr14", "rsi14", "adx14", "regime")
REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


class ContractError(RuntimeError):
    """Research outputs do not satisfy the data contract."""


def _load_utc_indexed_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ContractError(
            f"research dataset missing: {path}. Generate it with the research module, e.g.\n"
            f"  python -m crypto_research download --symbol {path.parent.name} "
            f"--timeframe <tf> --market <market>\n"
            f"(run inside modules/research)"
        )
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ContractError(f"{path}: index must be a DatetimeIndex, got {type(df.index)}")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert("UTC").as_unit("us")  # normalize unit for merge_asof
    return df.sort_index()


@dataclass(frozen=True)
class ResearchData:
    """The strategy-facing view of one symbol's research outputs."""

    symbol: str
    market: str
    regime_frame: pd.DataFrame  # 4h: OHLCV + indicators + regime (open-time index)
    entry_frame: pd.DataFrame  # 1h raw OHLCV (open-time index)

    @property
    def timeframe_duration(self) -> pd.Timedelta:
        return pd.Timedelta(hours=4)


def load_symbol_data(
    research_data_dir: Path | str, symbol: str, market: str = "futures",
    regime_timeframe: str = "4h", entry_timeframe: str = "1h",
) -> ResearchData:
    """Load and validate the research outputs for one symbol.

    Raises ``ContractError`` with an actionable message when the datasets
    are missing or violate the column contract.
    """
    symbol = symbol.upper()
    root = Path(research_data_dir)
    raw_path = root / "raw" / "bitunix" / market / symbol / f"{entry_timeframe}.parquet"
    regime_path = (
        root / "processed" / "bitunix" / market / symbol / f"{regime_timeframe}_regimes.parquet"
    )

    entry_frame = _load_utc_indexed_parquet(raw_path)
    regime_frame = _load_utc_indexed_parquet(regime_path)

    missing_ohlcv = [c for c in REQUIRED_OHLCV_COLUMNS if c not in entry_frame.columns]
    if missing_ohlcv:
        raise ContractError(f"{raw_path}: missing OHLCV columns {missing_ohlcv}")

    missing_regime = [c for c in REQUIRED_REGIME_COLUMNS if c not in regime_frame.columns]
    if missing_regime:
        raise ContractError(
            f"{regime_path}: missing regime-contract columns {missing_regime}. "
            f"Regenerate the artifact with: python -m crypto_research regime "
            f"--symbol {symbol} --timeframe {regime_timeframe} --market {market}"
        )
    unknown_labels = set(regime_frame["regime"].dropna().unique()) - REGIME_LABELS
    if unknown_labels:
        raise ContractError(
            f"{regime_path}: unknown regime labels {sorted(unknown_labels)}; "
            f"expected subset of {sorted(REGIME_LABELS)}"
        )
    if regime_frame.index.is_monotonic_increasing is False or regime_frame.index.is_unique is False:
        raise ContractError(f"{regime_path}: 4h index must be unique and ascending")

    return ResearchData(symbol=symbol, market=market, regime_frame=regime_frame, entry_frame=entry_frame)


def align_regime_to_entry(
    regime_frame: pd.DataFrame, entry_index: pd.DatetimeIndex, timeframe: pd.Timedelta
) -> pd.DataFrame:
    """Attach the most recent COMPLETED 4H regime to every 1H candle.

    A 4H candle opening at T is completed at close time ``T + timeframe``.
    A 1H candle opening at t may only use a 4H candle whose close time is
    ``<= t`` (never the currently forming 4H candle, never a future one).

    Returns a frame aligned to ``entry_index`` with columns:
    ``regime, regime_close_time, regime_open_time, ema50, ema200, atr14,
    atr_pct, rsi14, adx14, close_4h`` — NaN where no completed 4H candle
    exists yet (warm-up before the first 4H close).
    """
    if len(regime_frame) == 0:
        empty = pd.DataFrame(index=entry_index)
        for col in ("regime", "regime_close_time", "regime_open_time", "ema50", "ema200",
                    "atr14", "atr_pct", "rsi14", "adx14", "close_4h"):
            empty[col] = pd.Series(dtype="object" if col.startswith("regime") else "float64")
        return empty

    completed_at = regime_frame.index + timeframe  # close times (open + tf)
    aligned = pd.merge_asof(
        left=pd.DataFrame({"entry_time": entry_index}),
        right=pd.DataFrame(
            {
                "regime_close_time": completed_at,
                "regime_open_time": regime_frame.index,
                "close_4h": regime_frame["close"].to_numpy(),
                "ema50": regime_frame["ema50"].to_numpy(),
                "ema200": regime_frame["ema200"].to_numpy(),
                "atr14": regime_frame["atr14"].to_numpy(),
                "atr_pct": regime_frame["atr_pct"].to_numpy(),
                "rsi14": regime_frame["rsi14"].to_numpy(),
                "adx14": regime_frame["adx14"].to_numpy(),
                "regime": regime_frame["regime"].to_numpy(),
            }
        ).sort_values("regime_close_time"),
        left_on="entry_time",
        right_on="regime_close_time",
        direction="backward",
        allow_exact_matches=True,  # a 4H candle closing exactly at t is completed
    ).set_index("entry_time")
    aligned.index.name = entry_index.name or "timestamp"
    return aligned.reindex(entry_index)
