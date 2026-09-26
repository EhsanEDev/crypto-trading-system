"""Candle-driven backtesting engine.

Deterministic, event-ordered, no lookahead. Event order per candle
(documented and enforced by construction):

    At candle t (1H, open time ts):
      1. EXECUTE pending orders scheduled at candle t-1, at this open:
         entries (risk re-validated with the actual fill price) and
         pending regime/EMA exits (market order at the open).
      2. STOP / TAKE-PROFIT checks for every open position using candle
         t's high/low. Positions opened at step 1 are checked too. If a
         candle touches BOTH levels, the STOP is assumed to trigger
         first (intentionally conservative; unit-tested).
      3. CLOSE-of-candle accounting: mark to market at close[t], record
         an EquityPoint.
      4. SIGNAL evaluation for candle t using ONLY data up to close[t]:
         strategy.evaluate(...) -> BUY (order scheduled for t+1 open),
         EXIT (scheduled for t+1 open), or NO_TRADE.

    After the last candle: open positions close at the final close with
    slippage and fees (END_OF_DATA); unexecuted pending orders are
    discarded (recorded as rejected).

No forward-filling of data gaps: the engine iterates the candles that
exist; a "next candle open" across a gap is the next available candle's
open (gap counts are reported as warnings).

Stop/TP anchoring: the signal plans stop/TP from the evaluating close;
at execution the planned distances are preserved relative to the
executed entry price (stop = fill - planned_distance).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import StrategyConfig
from ..execution import simulator as ex
from ..indicators import atr as atr_fn
from ..indicators import ema as ema_fn
from ..indicators import rolling_percentile_threshold
from ..indicators import rsi as rsi_fn
from ..models.equity import EquityPoint
from ..models.order import Order
from ..models.position import Position, PositionStatus
from ..models.signal import Side, Signal
from ..models.trade import ExitReason, Trade, TradeContext
from ..portfolio.portfolio import Portfolio
from ..risk.manager import RiskManager
from ..strategy.base import StrategyContext
from ..strategy.trend_pullback import TrendPullbackStrategy

logger = logging.getLogger(__name__)

REGIME_TIMEFRAME = pd.Timedelta(hours=4)


@dataclass
class BacktestResult:
    """Everything produced by one symbol backtest (auditable)."""

    symbol: str
    market: str
    config: StrategyConfig
    trades: list[Trade] = field(default_factory=list)
    equity_points: list[EquityPoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rejected_orders: list[dict] = field(default_factory=list)

    @property
    def equity_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame([p.to_row() for p in self.equity_points])
        return frame.set_index("timestamp")

    @property
    def trades_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.to_row() for t in self.trades])


class Backtester:
    def __init__(self, config: StrategyConfig, strategy: TrendPullbackStrategy | None = None) -> None:
        self.config = config
        self.strategy = strategy or TrendPullbackStrategy()
        self.portfolio = Portfolio(config)
        self.risk = RiskManager(config)

    # ---------------------------------------------------------------- #
    # Public entry point
    # ---------------------------------------------------------------- #

    def run(
        self,
        symbol: str,
        regime_frame: pd.DataFrame,
        entry_frame: pd.DataFrame,
        start: str | None = None,
        end: str | None = None,
    ) -> BacktestResult:
        entry = _slice(entry_frame, start, end)
        if len(entry) < 2:
            raise ValueError(f"not enough 1H candles in the requested window for {symbol}")

        pre = self._precompute(entry, regime_frame)
        result = BacktestResult(symbol=symbol, market=self.config.market, config=self.config)
        result.warnings.extend(_gap_warnings(entry.index, pre["timeframe"]))

        pending_entry: Order | None = None
        pending_exit: ExitReason | None = None
        next_order_id = 0
        peak_equity = self.config.backtest.initial_equity

        closes = entry["close"].to_numpy(dtype=float)
        opens = entry["open"].to_numpy(dtype=float)
        highs = entry["high"].to_numpy(dtype=float)
        lows = entry["low"].to_numpy(dtype=float)
        index = entry.index

        for i in range(len(entry)):
            ts = index[i]

            # -- 1) execute pending orders at this open --------------------- #
            if pending_exit is not None:
                position = self._find_open(symbol)
                if position is not None:
                    self._close_position(result, position, ts, opens[i],
                                         pending_exit, candle_open=opens[i])
                pending_exit = None
            if pending_entry is not None:
                self._execute_entry(result, pending_entry, ts, closes[i - 1] if i > 0 else opens[i],
                                    opens[i], closes)
                pending_entry = None

            # -- 2) stop / take-profit checks ------------------------------- #
            for position in list(self.portfolio.open_positions):
                self._check_exits(result, position, ts, candle_open=opens[i],
                                  high=highs[i], low=lows[i])

            # -- 3) close-of-candle accounting ------------------------------- #
            equity = self.portfolio.equity({symbol: closes[i]})
            peak_equity = max(peak_equity, equity)
            drawdown = (equity - peak_equity) / peak_equity if peak_equity > 0 else 0.0
            notional = self.portfolio.open_notional({symbol: closes[i]})
            result.equity_points.append(
                EquityPoint(
                    timestamp=ts,
                    equity=equity,
                    cash=self.portfolio.cash,
                    exposure=notional / equity if equity > 0 else 0.0,
                    unrealized_pnl=self.portfolio.unrealized_pnl({symbol: closes[i]}),
                    realized_pnl=self.portfolio.realized_pnl,
                    drawdown=drawdown,
                )
            )

            # -- 4) signal evaluation (data up to close[t] only) -------------- #
            context = StrategyContext(
                timestamp=ts,
                open=opens[i],
                high=highs[i],
                low=lows[i],
                close=closes[i],
                ema20=_value(pre["ema20"], i),
                rsi14=_value(pre["rsi14"], i),
                rsi14_prev=_value(pre["rsi14_prev"], i),
                atr14=_value(pre["atr14"], i),
                atr_pct=_value(pre["atr_pct"], i),
                atr_pct_threshold=_value(pre["vol_threshold"], i),
                regime=pre["regime"][i],
                regime_close_time=pre["regime_close_time"][i],
                regime_ema50=_value_or_none(pre["regime_ema50"], i),
                regime_ema200=_value_or_none(pre["regime_ema200"], i),
                regime_atr14=_value_or_none(pre["regime_atr14"], i),
                regime_rsi14=_value_or_none(pre["regime_rsi14"], i),
                regime_adx14=_value_or_none(pre["regime_adx14"], i),
            )
            signal = self.strategy.evaluate(context, self.config)
            if signal.symbol == "":
                # strategies evaluate one symbol; the engine binds the symbol
                from dataclasses import replace

                signal = replace(signal, symbol=symbol)

            if signal.side == Side.BUY and pending_entry is None and pending_exit is None:
                order = self._schedule_order(result, next_order_id, signal, ts, closes[i])
                if order is not None:
                    pending_entry = order
                    next_order_id += 1
            elif signal.side == Side.EXIT and pending_exit is None and self.portfolio.has_position(symbol):
                pending_exit = (
                    ExitReason.REGIME_EXIT if signal.reason.startswith("REGIME_EXIT")
                    else ExitReason.EMA_EXIT
                )

        # -- end of data ------------------------------------------------------ #
        if self.portfolio.open_positions:
            for position in list(self.portfolio.open_positions):
                self._close_position(result, position, index[-1], closes[-1],
                                     ExitReason.END_OF_DATA, candle_open=opens[-1])
        if pending_entry is not None:
            result.rejected_orders.append(
                {"order_id": pending_entry.order_id,
                 "reason": "END_OF_DATA before execution", "timestamp": index[-1]}
            )
        return result

    # ---------------------------------------------------------------- #
    # Engine steps
    # ---------------------------------------------------------------- #

    def _schedule_order(self, result: BacktestResult, order_id: int, signal: Signal, ts,
                        mark_close: float) -> Order | None:
        """Admission at decision time (uses close[t]; executes at open[t+1])."""
        reject = self.portfolio.admission_reason(signal.symbol)
        if reject:
            result.rejected_orders.append({"order_id": order_id, "reason": reject, "timestamp": ts})
            return None
        equity = self.portfolio.equity({result.symbol: mark_close}) \
            or self.config.backtest.initial_equity
        exposure_used = self.portfolio.open_notional({result.symbol: mark_close})
        sizing = self.risk.size_position(
            entry_price=signal.entry_price,
            stop_price=signal.stop_price,
            equity=equity,
            cash=self.portfolio.cash,
            exposure_used=exposure_used,
        )
        if not sizing.approved:
            result.rejected_orders.append(
                {"order_id": order_id, "reason": sizing.reason, "timestamp": ts}
            )
            return None
        return Order(
            order_id=order_id,
            symbol=signal.symbol,
            side=signal.side.value,
            strategy_version=signal.strategy_version,
            created_from_signal_ts=ts,
            execute_at=None,  # resolved at the next candle's open
            entry_price=signal.entry_price,
            stop_price=signal.stop_price,
            take_profit_price=signal.take_profit_price,
            regime=signal.regime,
            conditions_json=signal.conditions.to_json(),
            indicators=dict(signal.indicators or {}),
        )

    def _execute_entry(self, result: BacktestResult, order: Order, ts, last_close: float,
                       next_open: float, closes: np.ndarray) -> None:
        """Fill a scheduled order at this candle's open (with slippage/fees)."""
        exec_price = ex.entry_fill_price(next_open, self.config.execution.slippage)
        stop_distance = order.entry_price - order.stop_price  # planned risk distance
        planned_quantity = self.risk.size_position(
            entry_price=exec_price,
            stop_price=exec_price - stop_distance,
            equity=self.portfolio.equity({result.symbol: last_close})
            or self.config.backtest.initial_equity,
            cash=self.portfolio.cash,
            exposure_used=self.portfolio.open_notional({result.symbol: last_close}),
        )
        if not planned_quantity.approved or planned_quantity.quantity <= 0:
            result.rejected_orders.append(
                {"order_id": order.order_id,
                 "reason": planned_quantity.reason or "rejected at execution", "timestamp": ts}
            )
            return
        quantity = planned_quantity.quantity
        entry_fees = quantity * exec_price * self.config.execution.fee_rate
        position = Position(
            position_id=order.order_id,
            symbol=order.symbol,
            strategy_version=order.strategy_version,
            opened_at=ts,
            entry_price=exec_price,
            entry_quantity=quantity,
            stop_price=exec_price - stop_distance,
            take_profit_price=exec_price + (order.take_profit_price - order.entry_price),
            entry_fees=entry_fees,
            regime=order.regime,
            conditions_json=order.conditions_json,
            indicators=order.indicators,
            signal_timestamp=order.created_from_signal_ts,
            risk_per_unit=stop_distance,
            entry_reference_price=next_open,
        )
        self.portfolio.open_position(position)

    def _check_exits(self, result: BacktestResult, position: Position, ts,
                     candle_open: float, high: float, low: float) -> None:
        stop_touched = ex.stop_hit(position.stop_price, low)
        tp_touched = ex.take_profit_hit(position.take_profit_price, high)
        if stop_touched and tp_touched:
            # conservative assumption: STOP triggers first (documented + tested)
            self._close_position(result, position, ts,
                                 ex.stop_fill_price(position.stop_price, candle_open),
                                 ExitReason.STOP_LOSS, candle_open=candle_open)
        elif stop_touched:
            self._close_position(result, position, ts,
                                 ex.stop_fill_price(position.stop_price, candle_open),
                                 ExitReason.STOP_LOSS, candle_open=candle_open)
        elif tp_touched:
            self._close_position(result, position, ts,
                                 ex.take_profit_fill_price(position.take_profit_price, candle_open),
                                 ExitReason.TAKE_PROFIT, candle_open=candle_open)

    def _close_position(self, result: BacktestResult, position: Position, exit_ts,
                        fill_ref: float, exit_reason: ExitReason, candle_open: float) -> None:
        slippage = self.config.execution.slippage
        exit_price = fill_ref * (1.0 - slippage)
        exit_fees = position.entry_quantity * exit_price * self.config.execution.fee_rate

        position.exit_price = exit_price
        position.exit_fees = exit_fees
        position.exit_reason = exit_reason.value
        position.closed_at = exit_ts
        position.status = PositionStatus.CLOSED

        gross = position.entry_quantity * (position.exit_price - position.entry_price)
        slippage_cost = position.entry_quantity * slippage * (
            position.entry_reference_price + fill_ref
        )
        fees_total = position.entry_fees + exit_fees
        net = self.portfolio.net_pnl_of(position)
        self.portfolio.close_position(position)

        indicators = position.indicators or {}
        context = TradeContext(
            regime=position.regime,
            ema20=indicators.get("ema20"),
            ema50=indicators.get("regime_ema50"),
            ema200=indicators.get("regime_ema200"),
            atr14=indicators.get("atr14"),
            atr14_4h=indicators.get("regime_atr14"),
            rsi14=indicators.get("rsi14"),
            adx14=indicators.get("regime_adx14"),
            atr_pct=indicators.get("atr_pct"),
        )
        total_risk = position.risk_per_unit * position.entry_quantity
        r_multiple = net / total_risk if total_risk > 0 else 0.0
        result.trades.append(
            Trade(
                trade_id=position.position_id,
                symbol=position.symbol,
                strategy_version=position.strategy_version,
                entry_timestamp=position.opened_at,
                entry_price=position.entry_price,
                entry_quantity=position.entry_quantity,
                stop_price=position.stop_price,
                take_profit_price=position.take_profit_price,
                exit_timestamp=exit_ts,
                exit_price=exit_price,
                exit_reason=exit_reason,
                gross_pnl=gross,
                fees=fees_total,
                slippage=slippage_cost,
                net_pnl=net,
                r_multiple=r_multiple,
                risk_per_unit=position.risk_per_unit,
                signal_timestamp=position.signal_timestamp,
                context=context,
                conditions_json=position.conditions_json,
            )
        )

    # ---------------------------------------------------------------- #
    # Precompute (vectorized, point-in-time safe)
    # ---------------------------------------------------------------- #

    def _precompute(self, entry: pd.DataFrame, regime_frame: pd.DataFrame) -> dict:
        cfg = self.config
        ema20 = ema_fn(entry["close"], cfg.ema20_period)
        rsi14 = rsi_fn(entry["close"], cfg.rsi_period)
        rsi14_prev = rsi14.shift(1)
        atr14 = atr_fn(entry, cfg.atr_period)
        atr_pct = atr14 / entry["close"] * 100.0
        if cfg.volatility.enabled:
            vol_threshold = rolling_percentile_threshold(
                atr_pct, cfg.volatility.lookback, cfg.volatility.percentile
            )
        else:
            vol_threshold = pd.Series(np.inf, index=entry.index)

        timeframe = _infer_timeframe(entry.index)
        aligned = _align(regime_frame, entry.index, REGIME_TIMEFRAME)

        regime_values: list[str | None] = []
        close_times: list = []
        aligned_values = {
            "regime_ema50": [], "regime_ema200": [], "regime_atr14": [],
            "regime_rsi14": [], "regime_adx14": [],
        }
        for _, row in aligned.iterrows():
            regime = row["regime"]
            regime_values.append(
                None if regime is None or (isinstance(regime, float) and np.isnan(regime)) else str(regime)
            )
            close_times.append(row["regime_close_time"])
            for key in aligned_values:
                value = row[key.removeprefix("regime_")]
                aligned_values[key].append(None if value is None or pd.isna(value) else float(value))

        return {
            "ema20": ema20,
            "rsi14": rsi14,
            "rsi14_prev": rsi14_prev,
            "atr14": atr14,
            "atr_pct": atr_pct,
            "vol_threshold": vol_threshold,
            "timeframe": timeframe,
            "regime": regime_values,
            "regime_close_time": close_times,
            **aligned_values,
        }

    def _find_open(self, symbol: str) -> Position | None:
        for position in self.portfolio.open_positions:
            if position.symbol == symbol:
                return position
        return None


# ---------------------------------------------------------------------- #
# helpers
# ---------------------------------------------------------------------- #

def _value(series: pd.Series, i: int) -> float | None:
    value = series.iloc[i] if i < len(series) else np.nan
    return None if value is None or pd.isna(value) else float(value)


def _value_or_none(values: list, i: int) -> float | None:
    return values[i] if i < len(values) else None


def _slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = df
    if start is not None:
        start_ts = pd.Timestamp(start)
        start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts
        out = out[out.index >= start_ts]  # date-only start -> 00:00 UTC inclusive
    if end is not None:
        end_ts = pd.Timestamp(end)
        end_ts = end_ts.tz_localize("UTC") if end_ts.tzinfo is None else end_ts
        out = out[out.index < end_ts + pd.Timedelta(days=1)]  # whole UTC day inclusive
    return out


def _infer_timeframe(index: pd.DatetimeIndex) -> pd.Timedelta:
    if len(index) < 2:
        return pd.Timedelta(hours=1)
    return pd.Timedelta(index.to_series().diff().median())


def _align(regime_frame: pd.DataFrame, entry_index: pd.DatetimeIndex,
           timeframe: pd.Timedelta) -> pd.DataFrame:
    from ..data.adapter import align_regime_to_entry

    return align_regime_to_entry(regime_frame, entry_index, timeframe)


def _gap_warnings(index: pd.DatetimeIndex, timeframe: pd.Timedelta) -> list[str]:
    warnings: list[str] = []
    gaps = index.to_series().diff() > timeframe
    for ts in index[gaps]:
        warnings.append(f"data gap before {ts} (next available candle used; not forward-filled)")
    return warnings
