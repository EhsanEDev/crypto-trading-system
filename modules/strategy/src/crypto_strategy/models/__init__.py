"""Typed models for signals, orders, positions, trades and equity.

Plain frozen dataclasses (typed, auditable, parquet-exportable). These are
Strategy-internal contracts; Research is not involved.
"""

from .equity import EquityPoint
from .order import Order, OrderStatus
from .position import Position, PositionStatus
from .signal import Side, Signal, SignalConditions
from .trade import ExitReason, Trade, TradeContext

__all__ = [
    "Side",
    "Signal",
    "SignalConditions",
    "Order",
    "OrderStatus",
    "Position",
    "PositionStatus",
    "ExitReason",
    "Trade",
    "TradeContext",
    "EquityPoint",
]
