"""Risk management: position sizing from risk, plus trade admission checks.

Formulas (documented; no magic numbers — all thresholds from config):

    max_loss      = current_equity * risk_per_trade
    stop_distance = entry_price - stop_price          (per unit risk)
    quantity      = max_loss / stop_distance
    notional      = quantity * entry_price
    risk_per_unit = stop_distance

Admission rules enforced here (a rejected admission is skipped with a
recorded reason — never silently ignored):

    stop_distance > 0 (degenerate/invalid stops rejected)
    equity > 0
    notional <= available exposure headroom (portfolio constraint)
    entry cost <= available cash
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SizingDecision:
    approved: bool
    reason: str
    quantity: float = 0.0
    max_loss: float = 0.0
    stop_distance: float = 0.0
    notional: float = 0.0


class RiskManager:
    def __init__(self, config) -> None:
        self.config = config

    def size_position(
        self,
        entry_price: float,
        stop_price: float,
        equity: float,
        cash: float,
        exposure_used: float,
    ) -> SizingDecision:
        risk = self.config.risk
        if equity <= 0:
            return SizingDecision(False, "insufficient equity", 0.0, 0.0, 0.0, 0.0)
        stop_distance = entry_price - stop_price
        if stop_distance <= 0:
            return SizingDecision(
                False,
                f"invalid stop distance ({stop_distance:.6f} <= 0)",
                0.0,
                0.0,
                0.0,
                0.0,
            )
        max_loss = equity * risk.risk_per_trade
        quantity = max_loss / stop_distance
        notional = quantity * entry_price

        # portfolio exposure headroom
        exposure_cap = equity * self.config.portfolio.max_total_exposure
        headroom = exposure_cap - exposure_used
        if notional > headroom + 1e-9:
            quantity = headroom / entry_price
            notional = quantity * entry_price
            if notional <= 0:
                return SizingDecision(
                    False,
                    f"exposure cap reached (used {exposure_used:.2f} / cap {exposure_cap:.2f})",
                    0.0,
                    max_loss,
                    stop_distance,
                    0.0,
                )

        # cash constraint (spot: buy fully cash-funded)
        fee_rate = self.config.execution.fee_rate
        entry_cost = notional * (1 + fee_rate)
        if entry_cost > cash + 1e-9:
            quantity = max(0.0, cash) / (entry_price * (1 + fee_rate))
            notional = quantity * entry_price
            if notional <= 0:
                return SizingDecision(False, "insufficient cash", 0.0, max_loss, stop_distance, 0.0)

        return SizingDecision(
            True,
            "approved",
            quantity,
            max_loss,
            stop_distance,
            notional,
        )
