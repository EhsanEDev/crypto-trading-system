"""Position model: explicit open-position lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class Position:
    """An open long position (spot, long-only)."""

    position_id: int
    symbol: str
    strategy_version: str
    opened_at: object  # execution candle open time
    entry_price: float  # executed (slippage-adjusted) price
    entry_quantity: float
    stop_price: float
    take_profit_price: float
    entry_fees: float
    regime: str | None
    conditions_json: str
    indicators: dict
    signal_timestamp: object  # evaluating candle that produced the order
    risk_per_unit: float  # entry_price - stop_price (per unit)
    entry_reference_price: float = 0.0  # candle open used for the fill (slippage base)
    status: PositionStatus = PositionStatus.OPEN
    exit_reason: str | None = None
    exit_price: float | None = None
    exit_fees: float = 0.0
    closed_at: object | None = None

    @property
    def unrealized(self, mark_price: float | None = None) -> float | None:
        if mark_price is None:
            return None
        return self.entry_quantity * (mark_price - self.entry_price)
