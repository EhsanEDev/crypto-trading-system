"""Strategy v001 rule tests (pure evaluate() — no engine)."""

from __future__ import annotations

import pandas as pd
import pytest

from crypto_strategy.config import StrategyConfig
from crypto_strategy.models.signal import Side
from crypto_strategy.strategy.base import StrategyContext
from crypto_strategy.strategy.trend_pullback import TrendPullbackStrategy


def ctx(**overrides) -> StrategyContext:
    base = dict(
        timestamp=pd.Timestamp("2024-01-05 10:00", tz="UTC"),
        open=100.0, high=100.4, low=99.5, close=100.2,
        ema20=100.0,           # low 99.5 <= 100.0 (pullback ✓), close 100.2 > 100.0 ✓
        rsi14=52.0, rsi14_prev=48.0,   # > 50 and rising ✓
        atr14=1.0, atr_pct=1.0, atr_pct_threshold=2.0,  # vol ok ✓
        regime="TREND_UP", regime_close_time=pd.Timestamp("2024-01-05 08:00", tz="UTC"),
    )
    base.update(overrides)
    return StrategyContext(**base)


def test_valid_buy_signal() -> None:
    signal = TrendPullbackStrategy().evaluate(ctx(), StrategyConfig())
    assert signal.side == Side.BUY
    assert signal.entry_price == pytest.approx(100.2)
    # stop = close - ATR*1.5 ; tp = close + 2R
    assert signal.stop_price == pytest.approx(100.2 - 1.5)
    assert signal.take_profit_price == pytest.approx(100.2 + 3.0)
    assert signal.conditions.to_json() == (
        '{"acceptable_volatility":true,"close_above_ema20":true,'
        '"pullback":true,"regime_trend_up":true,"rsi_recovery":true}'
    )


def test_wrong_regime_exit_by_default_and_no_trade_when_exits_disabled() -> None:
    # default config has regime_exit=True: a non-TREND_UP regime on an open
    # position context produces an EXIT signal
    for regime in ("TREND_DOWN", "RANGE", "HIGH_VOLATILITY"):
        signal = TrendPullbackStrategy().evaluate(ctx(regime=regime), StrategyConfig())
        assert signal.side == Side.EXIT, regime
    # UNCERTAIN (e.g. regime missing) also triggers REGIME_EXIT
    signal = TrendPullbackStrategy().evaluate(ctx(regime="UNCERTAIN"), StrategyConfig())
    assert signal.side == Side.EXIT
    # with exits disabled, a wrong regime simply blocks entry (NO_TRADE)
    config = StrategyConfig(exits={"regime_exit": False, "ema_exit": False})
    for regime in ("TREND_DOWN", "RANGE", "HIGH_VOLATILITY", "UNCERTAIN", None):
        signal = TrendPullbackStrategy().evaluate(ctx(regime=regime), config)
        assert signal.side == Side.NO_TRADE, regime


def test_regime_exit_enabled_when_regime_flips() -> None:
    signal = TrendPullbackStrategy().evaluate(ctx(regime="RANGE"), StrategyConfig())
    assert signal.side == Side.EXIT
    assert signal.reason.startswith("REGIME_EXIT")


def test_pullback_missing() -> None:
    signal = TrendPullbackStrategy().evaluate(ctx(low=100.5), StrategyConfig())
    assert signal.side == Side.NO_TRADE
    assert "no EMA20 pullback" in signal.reason


def test_rsi_recovery_missing_below_threshold() -> None:
    signal = TrendPullbackStrategy().evaluate(ctx(rsi14=45.0, rsi14_prev=44.0), StrategyConfig())
    assert signal.side == Side.NO_TRADE


def test_rsi_recovery_missing_not_rising() -> None:
    signal = TrendPullbackStrategy().evaluate(ctx(rsi14=55.0, rsi14_prev=56.0), StrategyConfig())
    assert signal.side == Side.NO_TRADE


def test_close_above_ema20_missing() -> None:
    signal = TrendPullbackStrategy().evaluate(ctx(close=99.9, high=100.4), StrategyConfig())
    assert signal.side == Side.NO_TRADE


def test_excessive_volatility_blocks_entry() -> None:
    signal = TrendPullbackStrategy().evaluate(ctx(atr_pct=2.5, atr_pct_threshold=2.0), StrategyConfig())
    assert signal.side == Side.NO_TRADE
    assert "volatility too high" in signal.reason


def test_volatility_disabled_always_accepts() -> None:
    config = StrategyConfig(volatility={"enabled": False})
    signal = TrendPullbackStrategy().evaluate(ctx(atr_pct=None, atr_pct_threshold=None), config)
    assert signal.side == Side.BUY


def test_warmup_nan_conditions_never_buy() -> None:
    signal = TrendPullbackStrategy().evaluate(
        ctx(ema20=None, rsi14=None, rsi14_prev=None, atr14=None, atr_pct=None,
            atr_pct_threshold=None, regime=None),
        StrategyConfig(),
    )
    assert signal.side == Side.NO_TRADE


def test_custom_rsi_threshold_respected() -> None:
    config = StrategyConfig(rsi_recovery_threshold=60)
    signal = TrendPullbackStrategy().evaluate(ctx(rsi14=55.0, rsi14_prev=54.0), config)
    assert signal.side == Side.NO_TRADE
    signal = TrendPullbackStrategy().evaluate(ctx(rsi14=61.0, rsi14_prev=60.0), config)
    assert signal.side == Side.BUY


def test_degenerate_atr_never_buy() -> None:
    signal = TrendPullbackStrategy().evaluate(ctx(atr14=0.0), StrategyConfig())
    assert signal.side == Side.NO_TRADE


def test_ema_exit_toggle() -> None:
    # ema_exit disabled by default: close < ema20 alone does not emit EXIT
    signal = TrendPullbackStrategy().evaluate(ctx(close=99.9, high=100.4), StrategyConfig())
    assert signal.side == Side.NO_TRADE
    config = StrategyConfig(exits={"regime_exit": False, "ema_exit": True})
    signal = TrendPullbackStrategy().evaluate(ctx(close=99.9, high=100.4), config)
    assert signal.side == Side.EXIT
    assert signal.reason.startswith("EMA_EXIT")
