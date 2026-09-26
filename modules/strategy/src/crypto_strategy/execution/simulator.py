"""Execution simulation primitives (fees + slippage fills).

Timing rules (documented and tested):
    * signals are evaluated at candle CLOSE, executed at the NEXT candle OPEN
    * long entry fill  = next_open * (1 + slippage)
    * long exit fill   = trigger_price * (1 - slippage)
      where trigger_price is the stop / take-profit level, or the candle
      open when the candle GAPS through the level (worse-or-equal fills
      only — see below)
    * gap handling (long positions, conservative):
        stop  : fill at min(stop, candle_open)  (open below stop -> worse)
        TP    : fill at max(tp, candle_open)    (open above tp fills better)

Same-candle stop & take-profit: if BOTH levels lie within one candle's
range, the STOP is assumed to trigger first (intentionally conservative;
documented and unit-tested).
"""

from __future__ import annotations


def entry_fill_price(next_open: float, slippage: float) -> float:
    return next_open * (1.0 + slippage)


def exit_fill_price(trigger_price: float, slippage: float) -> float:
    return trigger_price * (1.0 - slippage)


def stop_fill_price(stop: float, candle_open: float) -> float:
    """Price at which the stop fills for a long position (gap-aware)."""
    return min(stop, candle_open)


def take_profit_fill_price(tp: float, candle_open: float) -> float:
    """Take-profit fill for a long, gap-aware (open above TP fills at open)."""
    return max(tp, candle_open)


def stop_hit(stop: float, candle_low: float) -> bool:
    return candle_low <= stop


def take_profit_hit(tp: float, candle_high: float) -> bool:
    return candle_high >= tp


def both_touched(stop: float, tp: float, candle_high: float, candle_low: float) -> bool:
    return stop_hit(stop, candle_low) and take_profit_hit(tp, candle_high)
