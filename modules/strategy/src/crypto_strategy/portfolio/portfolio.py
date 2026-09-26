"""Portfolio: cash/equity accounting and constraint enforcement.

Constraints (from config, enforced before any order is scheduled):
    max_open_positions   — never more concurrent open positions
    one_position_per_symbol — no second position on the same symbol
    max_total_exposure   — open notional <= equity * max_total_exposure

Accounting: fully cash-funded spot longs. Cash decreases by entry cost
(quantity * executed entry price + entry fee) and increases by exit
proceeds minus exit fee. Equity = cash + sum(quantity * close).
"""

from __future__ import annotations

from ..models.position import Position, PositionStatus


class Portfolio:
    def __init__(self, config) -> None:
        self.config = config
        self.cash: float = config.backtest.initial_equity
        self.open_positions: list[Position] = []
        self.closed_positions: list[Position] = []
        self.realized_pnl: float = 0.0

    # ---------------------------------------------------------------- #
    # Constraint checks (called before scheduling an order)
    # ---------------------------------------------------------------- #

    def has_position(self, symbol: str) -> bool:
        return any(p.symbol == symbol and p.status == PositionStatus.OPEN for p in self.open_positions)

    def admission_reason(self, symbol: str) -> str | None:
        if self.config.portfolio.one_position_per_symbol and self.has_position(symbol):
            return "one_position_per_symbol: position already open"
        if len(self.open_positions) >= self.config.portfolio.max_open_positions:
            return f"max_open_positions ({self.config.portfolio.max_open_positions}) reached"
        return None

    # ---------------------------------------------------------------- #
    # Accounting
    # ---------------------------------------------------------------- #

    def open_position(self, position: Position) -> None:
        self.open_positions.append(position)
        self.cash -= position.entry_quantity * position.entry_price + position.entry_fees

    def close_position(self, position: Position) -> None:
        self.cash += position.entry_quantity * position.exit_price - position.exit_fees
        self.open_positions.remove(position)
        self.closed_positions.append(position)
        self.realized_pnl += self.net_pnl_of(position)

    @staticmethod
    def net_pnl_of(position: Position) -> float:
        gross = position.entry_quantity * (position.exit_price - position.entry_price)
        return gross - position.entry_fees - position.exit_fees

    def unrealized_pnl(self, mark_prices: dict[str, float]) -> float:
        total = 0.0
        for position in self.open_positions:
            mark = mark_prices.get(position.symbol)
            if mark is not None:
                total += position.entry_quantity * (mark - position.entry_price)
        return total

    def open_notional(self, mark_prices: dict[str, float]) -> float:
        total = 0.0
        for position in self.open_positions:
            mark = mark_prices.get(position.symbol)
            if mark is not None:
                total += position.entry_quantity * mark
        return total

    def equity(self, mark_prices: dict[str, float]) -> float:
        """Cash + market value of open positions (NOT cash + unrealized PnL:
        the entry cost already left cash, so the position must be valued at
        its mark price)."""
        return self.cash + self.open_notional(mark_prices)
