"""Multi-timeframe alignment tests: completed 4H candles only."""

from __future__ import annotations

import pandas as pd
import pytest
from helpers import make_4h_frame

from crypto_strategy.data.adapter import (
    ContractError,
    align_regime_to_entry,
    load_symbol_data,
)


def test_alignment_uses_completed_4h_candle_only() -> None:
    # 4H candles open at 00:00, 04:00, 08:00 (open-time index) and close at
    # open+4h: 00:00→04:00, 04:00→08:00, 08:00→12:00
    regimes = ["TREND_UP", "RANGE", "TREND_DOWN", "TREND_UP"]
    regime_frame = make_4h_frame(regimes, start="2024-01-01 00:00")
    entry_index = pd.DatetimeIndex(
        [
            "2024-01-01 10:00",  # newest completed: 04:00 candle (closed 08:00) -> RANGE
            "2024-01-01 11:00",  # same (08:00 candle closes 12:00 > 11:00) -> RANGE
            "2024-01-01 12:00",  # 08:00 candle closes exactly at 12:00 -> TREND_DOWN
            "2024-01-01 13:00",  # still the 08:00 candle -> TREND_DOWN
            "2024-01-01 16:00",  # 12:00 candle closes exactly at 16:00 -> TREND_UP
        ],
        name="timestamp",
    ).tz_localize("UTC")

    aligned = align_regime_to_entry(regime_frame, entry_index, pd.Timedelta(hours=4))
    assert list(aligned["regime"]) == ["RANGE", "RANGE", "TREND_DOWN", "TREND_DOWN", "TREND_UP"]
    # the aligned regime close time never exceeds the 1H candle open time
    assert (aligned["regime_close_time"] <= aligned.index).all()


def test_alignment_never_uses_future_regime() -> None:
    # regime flips on the 4H candle opening 04:00 (closes 08:00):
    # 1H candles 04:00..07:00 must see the PREVIOUS regime (00:00 candle);
    # the flip becomes visible exactly at 08:00 when the 04:00 candle closes
    regimes = ["TREND_UP", "TREND_DOWN", "TREND_UP"]
    regime_frame = make_4h_frame(regimes, start="2024-01-01 00:00")
    entry_index = pd.date_range("2024-01-01 00:00", periods=12, freq="1h", tz="UTC")
    aligned = align_regime_to_entry(regime_frame, entry_index, pd.Timedelta(hours=4))
    assert aligned.loc[:"2024-01-01 03:00", "regime"].isna().all()  # nothing completed yet
    assert (aligned.loc["2024-01-01 04:00":"2024-01-01 07:00", "regime"] == "TREND_UP").all()
    assert (aligned.loc["2024-01-01 08:00":, "regime"] == "TREND_DOWN").all()


def test_alignment_warmup_before_first_4h_close() -> None:
    regimes = ["TREND_UP"] * 3
    regime_frame = make_4h_frame(regimes, start="2024-01-01 00:00")  # first close: 04:00
    entry_index = pd.date_range("2024-01-01 00:00", periods=6, freq="1h", tz="UTC")
    aligned = align_regime_to_entry(regime_frame, entry_index, pd.Timedelta(hours=4))
    assert aligned["regime"].isna().tolist() == [True, True, True, True, False, False]


def test_contract_error_when_regime_column_missing(tmp_path) -> None:
    """`load_symbol_data` validates the regime column contract."""
    regimes = ["TREND_UP"]
    broken = make_4h_frame(regimes).drop(columns=["regime"])
    symbol_dir = tmp_path / "processed" / "bitunix" / "futures" / "BTCUSDT"
    symbol_dir.mkdir(parents=True)
    broken.to_parquet(symbol_dir / "4h_regimes.parquet")
    raw_dir = tmp_path / "raw" / "bitunix" / "futures" / "BTCUSDT"
    raw_dir.mkdir(parents=True)
    broken[["open", "high", "low", "close", "volume"]].to_parquet(raw_dir / "1h.parquet")

    with pytest.raises(ContractError, match="missing regime-contract columns"):
        load_symbol_data(tmp_path, "BTCUSDT", market="futures")


def test_load_symbol_data_contract_error_on_missing_files(tmp_path) -> None:
    with pytest.raises(ContractError, match="research dataset missing"):
        load_symbol_data(tmp_path, "BTCUSDT", market="futures")


def test_unknown_regime_labels_rejected(tmp_path) -> None:
    frame = make_4h_frame(["TREND_UP"])
    frame["regime"] = ["SUPER_BULL"]
    symbol_dir = tmp_path / "processed" / "bitunix" / "futures" / "BTCUSDT"
    symbol_dir.mkdir(parents=True)
    frame.to_parquet(symbol_dir / "4h_regimes.parquet")
    raw_dir = tmp_path / "raw" / "bitunix" / "futures" / "BTCUSDT"
    raw_dir.mkdir(parents=True)
    frame[["open", "high", "low", "close", "volume"]].to_parquet(raw_dir / "1h.parquet")

    with pytest.raises(ContractError, match="unknown regime labels"):
        load_symbol_data(tmp_path, "BTCUSDT", market="futures")
