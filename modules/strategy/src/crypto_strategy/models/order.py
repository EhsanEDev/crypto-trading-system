"""Order model: a pending execution created by a signal at candle close."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "PENDING"  # executes at the next candle open
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"  # end of data before execution


@dataclass(frozen=True)
class Order:
    """Market order scheduled at candle close, executed at next candle open.

    Orders are never cancelled in v001 (documented simplification): a
    pending order executes at the next available candle open even if the
    regime flipped in between — the engine runs the risk/exit checks
    immediately after.
    """

    order_id: int
    symbol: str
    side: str  # BUY only in v001
    strategy_version: str
    created_from_signal_ts: object  # evaluating candle (open time)
    execute_at: object  # candle whose open fills this order (t+1 open)
    entry_price: float  # reference close (not the fill price)
    stop_price: float
    take_profit_price: float
    regime: str | None
    conditions_json: str
    indicators: dict
    status: OrderStatus = OrderStatus.PENDING
    reject_reason: str | None = None
