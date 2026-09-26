"""Portfolio constraint tests."""

from __future__ import annotations

import pandas as pd

from crypto_strategy.config import StrategyConfig
from crypto_strategy.models.position import Position
from crypto_strategy.portfolio.portfolio import Portfolio


def make_position(pid: int, symbol: str, qty: float, price: float) -> Position:
    return Position(
        position_id=pid, symbol=symbol, strategy_version="v001",
        opened_at=pd.Timestamp("2024-01-01", tz="UTC"), entry_price=price,
        entry_quantity=qty, stop_price=price * 0.95, take_profit_price=price * 1.10,
        entry_fees=0.0, regime="TREND_UP", conditions_json="{}", indicators={},
        signal_timestamp=pd.Timestamp("2023-12-31", tz="UTC"), risk_per_unit=price * 0.05,
    )


def test_max_open_positions() -> None:
    portfolio = Portfolio(StrategyConfig(portfolio={"max_open_positions": 2}))
    portfolio.open_position(make_position(0, "BTCUSDT", 1.0, 100.0))
    portfolio.open_position(make_position(1, "ETHUSDT", 1.0, 50.0))
    assert portfolio.admission_reason("SOLUSDT") is not None
    assert "max_open_positions" in portfolio.admission_reason("SOLUSDT")


def test_one_position_per_symbol() -> None:
    portfolio = Portfolio(StrategyConfig())
    portfolio.open_position(make_position(0, "BTCUSDT", 1.0, 100.0))
    reason = portfolio.admission_reason("BTCUSDT")
    assert reason is not None and "one_position_per_symbol" in reason


def test_cash_and_equity_accounting() -> None:
    config = StrategyConfig(backtest={"initial_equity": 10_000.0})
    portfolio = Portfolio(config)
    position = make_position(0, "BTCUSDT", 10.0, 100.0)
    portfolio.open_position(position)
    assert portfolio.cash == 10_000.0 - 1_000.0  # no fees in fixture
    mark = {"BTCUSDT": 101.0}
    # equity = cash + position MARKET value (entry cost already left cash)
    assert portfolio.equity(mark) == 9_000.0 + 10.0 * 101.0
    assert portfolio.unrealized_pnl(mark) == 10.0  # PnL vs entry price

    position.exit_price = 102.0
    portfolio.close_position(position)
    assert portfolio.cash == 9_000.0 + 1_020.0
    assert portfolio.realized_pnl == 20.0
    assert len(portfolio.closed_positions) == 1
    assert portfolio.open_positions == []


def test_exposure_accounting() -> None:
    portfolio = Portfolio(StrategyConfig(backtest={"initial_equity": 10_000.0}))
    portfolio.open_position(make_position(0, "BTCUSDT", 10.0, 100.0))
    mark = {"BTCUSDT": 105.0}
    assert portfolio.open_notional(mark) == 1_050.0
    assert portfolio.unrealized_pnl(mark) == 50.0
