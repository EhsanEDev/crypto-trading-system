"""Execution simulator primitive tests."""

from __future__ import annotations

import pytest

from crypto_strategy.execution import simulator as ex


def test_entry_fill_applies_slippage_up() -> None:
    assert ex.entry_fill_price(100.0, 0.0005) == pytest.approx(100.05)


def test_exit_fill_applies_slippage_down() -> None:
    assert ex.exit_fill_price(100.0, 0.0005) == pytest.approx(99.95)


def test_stop_gap_through_fills_at_open() -> None:
    # candle opens below the stop -> worse fill at the open
    assert ex.stop_fill_price(stop=95.0, candle_open=93.0) == pytest.approx(93.0)
    # normal case -> fill at the stop level
    assert ex.stop_fill_price(stop=95.0, candle_open=96.0) == pytest.approx(95.0)


def test_tp_gap_up_fills_at_open() -> None:
    assert ex.take_profit_fill_price(tp=110.0, candle_open=112.0) == pytest.approx(112.0)
    assert ex.take_profit_fill_price(tp=110.0, candle_open=109.0) == pytest.approx(110.0)


def test_hit_detection() -> None:
    assert ex.stop_hit(95.0, candle_low=94.9)
    assert not ex.stop_hit(95.0, candle_low=95.1)
    assert ex.take_profit_hit(110.0, candle_high=110.1)
    assert not ex.take_profit_hit(110.0, candle_high=109.9)


def test_same_candle_stop_and_tp_detected() -> None:
    # both levels within one candle range -> both touched (engine resolves
    # to STOP first; covered in the engine tests)
    assert ex.both_touched(stop=95.0, tp=110.0, candle_high=115.0, candle_low=94.0)
