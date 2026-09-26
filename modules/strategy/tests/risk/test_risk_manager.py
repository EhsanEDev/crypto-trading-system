"""Risk manager tests: sizing math, degenerate stops, caps."""

from __future__ import annotations

import pytest

from crypto_strategy.config import StrategyConfig
from crypto_strategy.risk.manager import RiskManager


def test_position_sizing_formula() -> None:
    # equity 10,000, risk 0.5% -> max_loss 50 ; entry 100, stop 95 -> 5/unit
    manager = RiskManager(StrategyConfig())
    decision = manager.size_position(entry_price=100.0, stop_price=95.0,
                                     equity=10_000.0, cash=10_000.0, exposure_used=0.0)
    assert decision.approved
    assert decision.max_loss == pytest.approx(50.0)
    assert decision.stop_distance == pytest.approx(5.0)
    assert decision.quantity == pytest.approx(10.0)
    assert decision.notional == pytest.approx(1_000.0)


def test_risk_percentage_configurable() -> None:
    config = StrategyConfig(risk={"risk_per_trade": 0.01, "atr_stop_multiplier": 1.0})
    manager = RiskManager(config)
    decision = manager.size_position(entry_price=100.0, stop_price=90.0,
                                     equity=50_000.0, cash=50_000.0, exposure_used=0.0)
    assert decision.approved
    assert decision.max_loss == pytest.approx(500.0)
    assert decision.quantity == pytest.approx(50.0)


def test_zero_and_negative_stop_distance_rejected() -> None:
    manager = RiskManager(StrategyConfig())
    for stop in (100.0, 101.0):  # stop >= entry -> no risk-based sizing possible
        decision = manager.size_position(entry_price=100.0, stop_price=stop,
                                         equity=10_000.0, cash=10_000.0, exposure_used=0.0)
        assert not decision.approved
        assert "stop distance" in decision.reason


def test_insufficient_equity_rejected() -> None:
    manager = RiskManager(StrategyConfig())
    decision = manager.size_position(entry_price=100.0, stop_price=95.0,
                                     equity=0.0, cash=0.0, exposure_used=0.0)
    assert not decision.approved
    assert "insufficient equity" in decision.reason


def test_exposure_cap_trims_quantity() -> None:
    # cap = equity * 1.0 = 50,000 ; naive notional = 100*... would exceed
    config = StrategyConfig(
        risk={"risk_per_trade": 0.05, "atr_stop_multiplier": 0.5},  # huge size
        portfolio={"max_total_exposure": 1.0},
    )
    manager = RiskManager(config)
    decision = manager.size_position(entry_price=100.0, stop_price=95.0,
                                     equity=50_000.0, cash=100_000.0, exposure_used=0.0)
    assert decision.approved
    assert decision.notional <= 50_000.0 + 1e-6


def test_exposure_headroom_reduces_size() -> None:
    config = StrategyConfig(
        risk={"risk_per_trade": 0.05, "atr_stop_multiplier": 0.5},
        portfolio={"max_total_exposure": 1.0},
    )
    manager = RiskManager(config)
    decision = manager.size_position(entry_price=100.0, stop_price=95.0,
                                     equity=50_000.0, cash=100_000.0, exposure_used=30_000.0)
    assert decision.approved
    assert decision.notional <= 20_000.0 + 1e-6


def test_cash_constraint_trims_size() -> None:
    manager = RiskManager(StrategyConfig(risk={"risk_per_trade": 0.05}))
    decision = manager.size_position(entry_price=100.0, stop_price=95.0,
                                     equity=10_000.0, cash=200.0, exposure_used=0.0)
    assert decision.approved
    assert decision.notional <= 200.0 + 1e-6
