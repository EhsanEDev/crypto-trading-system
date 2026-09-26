"""Signal model: auditable, typed, with the conditions that produced it."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    EXIT = "EXIT"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class SignalConditions:
    """Machine-readable entry conditions (stored as JSON on signals/trades)."""

    regime_trend_up: bool = False
    pullback: bool = False
    rsi_recovery: bool = False
    close_above_ema20: bool = False
    acceptable_volatility: bool = False

    @property
    def all_entry_conditions(self) -> bool:
        return all(
            (
                self.regime_trend_up,
                self.pullback,
                self.rsi_recovery,
                self.close_above_ema20,
                self.acceptable_volatility,
            )
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class Signal:
    """One strategy evaluation at a candle close (executed at next open)."""

    timestamp: object  # pd.Timestamp of the evaluating candle (open time)
    symbol: str
    side: Side
    strategy_version: str
    regime: str | None
    reason: str
    conditions: SignalConditions
    # reference prices at the evaluating candle's close (BUY only)
    entry_price: float | None = None  # candle close (reference; entry at next open)
    stop_price: float | None = None
    take_profit_price: float | None = None
    indicators: dict | None = None  # indicator snapshot for audit

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "side": self.side.value,
            "strategy_version": self.strategy_version,
            "regime": self.regime,
            "reason": self.reason,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "take_profit_price": self.take_profit_price,
            "indicators": self.indicators or {},
            "conditions": self.conditions.to_json(),
        }
