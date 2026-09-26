"""Strategy interface.

A strategy evaluates one candle's context (entry timeframe OHLCV +
indicators + the aligned higher-timeframe regime) and returns a typed
Signal. It knows nothing about orders, execution, portfolio or the
backtester — the engine handles those.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import StrategyConfig
from ..models.signal import Side, Signal, SignalConditions


@dataclass(frozen=True)
class StrategyContext:
    """Everything a strategy may use to decide — candle-close scope only."""

    timestamp: object  # entry candle open time (decision happens at its close)
    open: float
    high: float
    low: float
    close: float
    # 1H entry-timeframe indicators (computed locally by the adapter layer)
    ema20: float | None
    rsi14: float | None
    rsi14_prev: float | None
    atr14: float | None
    atr_pct: float | None
    atr_pct_threshold: float | None  # past-only rolling percentile (volatility filter)
    # aligned 4H regime (completed candle only) + its indicator values
    regime: str | None
    regime_close_time: object | None
    regime_ema50: float | None = None
    regime_ema200: float | None = None
    regime_atr14: float | None = None
    regime_rsi14: float | None = None
    regime_adx14: float | None = None

    def indicator_snapshot(self) -> dict:
        return {
            "ema20": self.ema20,
            "rsi14": self.rsi14,
            "atr14": self.atr14,
            "atr_pct": self.atr_pct,
            "regime": self.regime,
            "regime_close_time": self.regime_close_time,
            "regime_ema50": self.regime_ema50,
            "regime_ema200": self.regime_ema200,
            "regime_atr14": self.regime_atr14,
            "regime_rsi14": self.regime_rsi14,
            "regime_adx14": self.regime_adx14,
        }


class Strategy(Protocol):
    """Strategy contract implemented by concrete strategies."""

    name: str
    version: str

    def evaluate(self, context: StrategyContext, config: StrategyConfig) -> Signal:
        ...


def _conditions_to_signal(
    context: StrategyContext,
    config: StrategyConfig,
    conditions: SignalConditions,
    failed_reason: str,
) -> Signal:
    if conditions.all_entry_conditions:
        stop_distance = context.atr14 * config.risk.atr_stop_multiplier
        if stop_distance <= 0:
            # degenerate stop (ATR<=0): never emit a BUY with an invalid stop
            return Signal(
                timestamp=context.timestamp,
                symbol="",
                side=Side.NO_TRADE,
                strategy_version=config.strategy_version,
                regime=context.regime,
                reason="NO_TRADE: invalid stop distance (ATR-based risk <= 0)",
                conditions=conditions,
                indicators=context.indicator_snapshot(),
            )
        stop_price = context.close - stop_distance
        take_profit = context.close + config.risk.reward_ratio * stop_distance
        return Signal(
            timestamp=context.timestamp,
            symbol="",  # filled by the engine (strategy evaluates one symbol)
            side=Side.BUY,
            strategy_version=config.strategy_version,
            regime=context.regime,
            reason="; ".join(
                [
                    "4H regime TREND_UP",
                    "1H pullback to EMA20",
                    "RSI14 recovery",
                    "close > EMA20",
                    "volatility acceptable",
                ]
            ),
            conditions=conditions,
            entry_price=context.close,
            stop_price=stop_price,
            take_profit_price=take_profit,
            indicators=context.indicator_snapshot(),
        )
    return Signal(
        timestamp=context.timestamp,
        symbol="",
        side=Side.NO_TRADE,
        strategy_version=config.strategy_version,
        regime=context.regime,
        reason=failed_reason,
        conditions=conditions,
        indicators=context.indicator_snapshot(),
    )
