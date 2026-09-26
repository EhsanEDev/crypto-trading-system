"""Strategy v001 — Trend Pullback Momentum Recovery (spot, long-only).

Rules (all evaluated at a 1H candle's close, executed at the NEXT open):

    BUY when ALL hold:
      1. regime_trend_up        : aligned 4H regime == TREND_UP
      2. pullback               : 1H low <= EMA20
      3. rsi_recovery           : 1H RSI14 > threshold AND RSI14 > prev RSI14
      4. close_above_ema20      : 1H close > EMA20
      5. acceptable_volatility  : 1H ATR% <= trailing percentile threshold

    NO_TRADE otherwise (reason lists the failed conditions).

    EXIT (for open positions, decided at candle close, executed next open):
      - REGIME_EXIT : aligned 4H regime != TREND_UP (if enabled)
      - EMA_EXIT    : close < EMA20 (if enabled)

Missing/warm-up values (NaN indicators, no completed 4H regime, empty
volatility window) never generate a BUY — they fail conditions.
"""

from __future__ import annotations

from ..config import StrategyConfig
from ..models.signal import Side, Signal, SignalConditions
from .base import StrategyContext, _conditions_to_signal


class TrendPullbackStrategy:
    name = "trend_pullback_momentum"
    version = "v001"

    def evaluate(self, context: StrategyContext, config: StrategyConfig) -> Signal:
        # EXIT evaluation first (open-position exits; engine applies to
        # positions it owns — a BUY is never issued here anyway).
        if config.exits.regime_exit and context.regime is not None and context.regime != "TREND_UP":
            return Signal(
                timestamp=context.timestamp,
                symbol="",
                side=Side.EXIT,
                strategy_version=config.strategy_version,
                regime=context.regime,
                reason=f"REGIME_EXIT: aligned 4H regime is {context.regime}",
                conditions=SignalConditions(),
                indicators=context.indicator_snapshot(),
            )
        if config.exits.ema_exit and context.ema20 is not None and context.close < context.ema20:
            return Signal(
                timestamp=context.timestamp,
                symbol="",
                side=Side.EXIT,
                strategy_version=config.strategy_version,
                regime=context.regime,
                reason="EMA_EXIT: close < EMA20",
                conditions=SignalConditions(),
                indicators=context.indicator_snapshot(),
            )

        conditions = self._conditions(context, config)
        return _conditions_to_signal(context, config, conditions, self._failure_reason(conditions))

    def _conditions(self, context: StrategyContext, config: StrategyConfig) -> SignalConditions:
        regime_ok = context.regime == "TREND_UP"

        pullback = (
            context.ema20 is not None and context.low <= context.ema20
        )
        confirmation = (
            context.ema20 is not None and context.close > context.ema20
        ) if config.require_close_above_ema20 else True

        rsi_recovery = False
        if context.rsi14 is not None and context.rsi14_prev is not None:
            rsi_recovery = (
                context.rsi14 > config.rsi_recovery_threshold
                and context.rsi14 > context.rsi14_prev
            )

        acceptable_volatility = False
        if not config.volatility.enabled:
            acceptable_volatility = True
        elif context.atr_pct is not None and context.atr_pct_threshold is not None:
            acceptable_volatility = context.atr_pct <= context.atr_pct_threshold

        return SignalConditions(
            regime_trend_up=bool(regime_ok),
            pullback=bool(pullback),
            rsi_recovery=bool(rsi_recovery),
            close_above_ema20=bool(confirmation),
            acceptable_volatility=bool(acceptable_volatility),
        )

    def _failure_reason(self, conditions: SignalConditions) -> str:
        if conditions.all_entry_conditions:
            return "BUY"
        failed = []
        if not conditions.regime_trend_up:
            failed.append("4H regime not TREND_UP")
        if not conditions.pullback:
            failed.append("no EMA20 pullback")
        if not conditions.rsi_recovery:
            failed.append("RSI14 recovery missing")
        if not conditions.close_above_ema20:
            failed.append("close not above EMA20")
        if not conditions.acceptable_volatility:
            failed.append("volatility too high")
        return "NO_TRADE: " + "; ".join(failed)
