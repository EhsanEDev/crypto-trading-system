"""Trade model: the closed-position audit record."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    REGIME_EXIT = "REGIME_EXIT"
    EMA_EXIT = "EMA_EXIT"
    END_OF_DATA = "END_OF_DATA"


@dataclass(frozen=True)
class TradeContext:
    """Indicator/regime snapshot at signal time (audit trail)."""

    regime: str | None
    ema20: float | None
    ema50: float | None
    ema200: float | None
    atr14: float | None  # 1H ATR (stop input)
    atr14_4h: float | None
    rsi14: float | None
    adx14: float | None
    atr_pct: float | None  # 1H volatility measure

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "ema20": self.ema20,
            "ema50_4h": self.ema50,
            "ema200_4h": self.ema200,
            "atr14_1h": self.atr14,
            "atr14_4h": self.atr14_4h,
            "rsi14_1h": self.rsi14,
            "adx14_4h": self.adx14,
            "atr_pct_1h": self.atr_pct,
        }


@dataclass(frozen=True)
class Trade:
    """A closed position with complete PnL accounting and audit context."""

    trade_id: int
    symbol: str
    strategy_version: str
    entry_timestamp: object  # execution open time
    entry_price: float
    entry_quantity: float
    stop_price: float
    take_profit_price: float
    exit_timestamp: object
    exit_price: float
    exit_reason: ExitReason
    gross_pnl: float  # before fees/slippage-vs-fill effects excluded: qty*(exit_ref-entry_ref)
    fees: float  # entry + exit fees
    slippage: float  # absolute slippage cost (entry + exit)
    net_pnl: float  # realized cash delta including fees and slippage
    r_multiple: float
    risk_per_unit: float
    signal_timestamp: object
    context: TradeContext
    conditions_json: str

    def to_row(self) -> dict:
        row = {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "strategy_version": self.strategy_version,
            "entry_timestamp": self.entry_timestamp,
            "entry_price": self.entry_price,
            "entry_quantity": self.entry_quantity,
            "stop_price": self.stop_price,
            "take_profit_price": self.take_profit_price,
            "exit_timestamp": self.exit_timestamp,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason.value,
            "gross_pnl": self.gross_pnl,
            "fees": self.fees,
            "slippage": self.slippage,
            "net_pnl": self.net_pnl,
            "r_multiple": self.r_multiple,
            "risk_per_unit": self.risk_per_unit,
            "signal_timestamp": self.signal_timestamp,
        }
        row.update({f"context_{k}": v for k, v in self.context.to_dict().items()})
        row["conditions"] = self.conditions_json
        return row
