"""Dataset discovery/loading from the research module's artifacts.

Reads the research parquet contract by path (like the strategy adapter):
    modules/research/data/processed/bitunix/{market}/{SYMBOL}/{tf}_regimes.parquet

No copying, no moving: the research module stays the data owner.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from crypto_research.config import PROJECT_ROOT as RESEARCH_MODULE_ROOT

RESEARCH_DATA_DIR = Path(RESEARCH_MODULE_ROOT) / "data"
REGIME_TIMEFRAME = "4h"


def _processed_root(research_data_dir: Path, market: str) -> Path:
    return Path(research_data_dir) / "processed" / "bitunix" / market


def available_markets(research_data_dir: Path | str = RESEARCH_DATA_DIR) -> list[str]:
    root = Path(research_data_dir) / "processed" / "bitunix"
    if not root.exists():
        return ["futures"]
    return sorted(d.name for d in root.iterdir() if d.is_dir())


def available_symbols(research_data_dir: Path | str, market: str = "futures",
                      timeframe: str = "4h") -> list[str]:
    """Symbols with a stored regimes artifact for the given market/timeframe."""
    root = _processed_root(Path(research_data_dir), market)
    if not root.exists():
        return []
    return sorted(p.parent.name for p in root.glob(f"*/{timeframe}_regimes.parquet"))


@lru_cache(maxsize=32)
def load_symbol_data(
    symbol: str, market: str, timeframe: str = "4h",
    research_data_dir: str | None = None,
) -> pd.DataFrame:
    """Load the regimes artifact for one symbol (OHLCV + indicators + regime)."""
    root = Path(research_data_dir) if research_data_dir else RESEARCH_DATA_DIR
    path = _processed_root(root, market) / symbol / f"{timeframe}_regimes.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"no regimes artifact for {symbol} ({market}, {timeframe}). "
            f"Generate it: python -m crypto_research regime --symbol {symbol} "
            f"--timeframe {timeframe} --market {market}"
        )
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    df.index = df.index.tz_convert("UTC").as_unit("us")
    return df.sort_index()


def invalidate_cache() -> None:
    load_symbol_data.cache_clear()
