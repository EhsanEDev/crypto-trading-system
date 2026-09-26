"""Equity curve point model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EquityPoint:
    """Mark-to-market snapshot at each candle close."""

    timestamp: object
    equity: float  # cash + open position market value
    cash: float
    exposure: float  # open notional / equity
    unrealized_pnl: float
    realized_pnl: float  # cumulative realized net pnl
    drawdown: float  # fractional drawdown from running peak equity

    def to_row(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "equity": self.equity,
            "cash": self.cash,
            "exposure": self.exposure,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "drawdown": self.drawdown,
        }
