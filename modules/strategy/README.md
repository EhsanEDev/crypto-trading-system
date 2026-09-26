# Module 2 — Strategy + Backtester (`crypto_strategy`)

Strategy and backtesting module of `crypto-trading-system`. It consumes
**Research outputs** through an explicit data contract (never Research
internals) and turns them into an auditable, deterministic backtest.

> **Backtest results are experimental and do not imply future
> profitability.** v001 is a predefined baseline: no optimization, no
> parameter search, no rule changes to improve historical numbers.

## 1. Purpose

Implement the research → strategy → backtest pipeline:

```text
Research Data (parquet contract)
     ↓
Strategy v001 (trend pullback momentum recovery)
     ↓
Signal (BUY / EXIT / NO_TRADE)
     ↓
Risk Manager (risk-based sizing, admission checks)
     ↓
Execution Simulator (next-open fills, fees, slippage, stop/TP)
     ↓
Portfolio (cash/equity accounting, constraints)
     ↓
Backtester (candle-driven engine)
     ↓
Metrics + Reports (markdown / json / parquet)
```

Long-only, spot, no leverage, no shorts, no live trading.

## 2. Architecture

```text
modules/strategy/src/crypto_strategy/
├── config.py                # YAML + validated pydantic config (all thresholds)
├── cli.py                   # backtest / report / pipeline
├── models/                  # signal, order, position, trade, equity (typed)
├── strategy/
│   ├── base.py              # Strategy protocol + StrategyContext
│   └── trend_pullback.py    # v001 rules
├── indicators.py            # local 1H EMA/RSI/ATR (deliberately independent)
├── risk/manager.py          # risk-based sizing + admission
├── execution/simulator.py   # fill/fee/slippage primitives
├── portfolio/portfolio.py   # accounting + constraints
├── backtest/engine.py       # candle-driven engine (event order documented)
├── metrics/performance.py   # metric formulas (documented)
├── data/adapter.py          # THE Research integration boundary
├── reports/generator.py     # markdown/json/parquet artifacts
└── runner.py                # orchestration (adapter → engine → artifacts)
```

## 3. Research integration (the contract)

`data/adapter.py` is the **only** place that knows about Research. It
reads Research's parquet artifacts by path and validates a documented
column contract:

- raw candles: `modules/research/data/raw/bitunix/{market}/{SYMBOL}/{tf}.parquet`
- 4H regimes: `modules/research/data/processed/bitunix/{market}/{SYMBOL}/4h_regimes.parquet`
  (`ema50, ema200, atr14, rsi14, adx14, regime` + labels from the fixed set)

Strategy computes the 1H entry indicators (EMA20, RSI14, ATR14) **locally**
from the OHLCV contract — explicitly allowed by the module boundary rules
and deliberately NOT imported from Research. Replacing Research with
another provider = replacing `data/adapter.py` only.

## 4. Strategy v001 — Trend Pullback Momentum Recovery

Spot, long-only. Signal vocabulary: `BUY` / `EXIT` / `NO_TRADE` (no SHORT).

**BUY requires ALL of (evaluated at a 1H candle close):**

1. **4H regime == TREND_UP** (the most recent *completed* 4H candle)
2. **Pullback**: 1H `low <= EMA20`
3. **RSI recovery**: 1H `RSI14 > 50` AND `RSI14 > previous RSI14`
4. **Confirmation**: 1H `close > EMA20`
5. **Volatility filter**: 1H `ATR14/Close <=` trailing rolling 90th
   percentile (200-bar window, `shift(1)` — strictly past-only)

**EXIT (for open positions, decided at close, executed next open):**
- `REGIME_EXIT`: aligned 4H regime != TREND_UP (default: on)
- `EMA_EXIT`: `close < EMA20` (default: off)

**NO_TRADE otherwise** — the signal records which conditions failed.
Warm-up/NaN values never generate a BUY. A degenerate stop
(ATR <= 0) is never emitted.

## 5. Multi-timeframe correctness

4H candles are indexed by **open time**; a 4H candle opening at `T` covers
`[T, T+4h)` and is *completed* at `T+4h`. A 1H candle opening at `t` may
only use the 4H candle with `close time <= t` — never the forming candle,
never a future one. Implemented via `merge_asof` on 4H close times and
proved by dedicated tests (including a regime-flip timing test).

## 6. Risk model

```text
max_loss      = equity * risk_per_trade          (default 0.5%)
stop_distance = 1H ATR14 * atr_stop_multiplier   (default 1.5)
quantity      = max_loss / stop_distance
stop          = entry - stop_distance
take_profit   = entry + reward_ratio * R         (default 2.0)
notional      = quantity * entry                 (exposure-capped)
```

Admission checks (rejected orders are recorded with reasons): invalid
stop distance, insufficient equity/cash, exposure cap headroom,
`max_open_positions`, `one_position_per_symbol`.

## 7. Execution simulation

- Signal at candle **close** → execution at **next candle open** (never same-bar close).
- Entry fill `= next_open * (1 + slippage_bps/1e4)`; exit fill `= trigger * (1 - slippage)`.
- Gap handling: stop fills at `min(stop, open)`; TP fills at `max(tp, open)`.
- **Same-candle stop & TP → STOP first** (conservative; unit-tested).
- Fees (default 6 bps) applied on entry and exit, stored per trade.
- `END_OF_DATA` closes open positions at the final close; unexecuted
  pending orders are discarded (recorded as rejected).
- Pending orders are never cancelled in v001 (documented simplification).

## 8. Backtesting methodology

Event order per candle (documented in `engine.py` and enforced by
construction): ① execute pending orders at this open → ② stop/TP checks
on candle high/low → ③ mark-to-market + EquityPoint → ④ signal
evaluation (data ≤ close[t] only). Deterministic: same data + config +
strategy version → identical artifacts. Data gaps are never
forward-filled; they are reported as warnings and the next available
candle is used.

## 9. Metrics

Documented formulas in `metrics/performance.py` and docstrings:
Total Return, CAGR, Max Drawdown, Sharpe, Sortino, Win Rate, Profit
Factor, Expectancy, Average/Largest Win & Loss, Max Losing Streak,
Trade Count, Total Fees, Total Slippage, Average R, Exposure, Gross/Net
PnL. Annualization assumption: **1H equity sampling, crypto 24/7 →
√(24·365)**; risk-free rate 0. Fees/slippage reported separately from
gross PnL. A **Buy & Hold** benchmark (same fee/slippage at entry) is
computed for comparison — never used to tune the strategy.

## 10. Lookahead prevention

Hard requirements, all tested:
- signals use only data ≤ the evaluating candle's close;
- the 4H regime/indicators come from candles **completed before** the 1H
  candle opens;
- the volatility threshold is a trailing `shift(1)` percentile;
- engine prefix-invariance: a backtest over the first k candles produces
  byte-identical trades/equity for that prefix;
- tampering future regime rows cannot change past signals.

## 11. Configuration

`configs/default.yaml` (all thresholds externalized — see the file for
the full schema): entry rules, volatility filter, risk (sizing/stop/TP),
portfolio constraints, execution (fees/slippage), exits, initial equity,
research data path. `--config` overrides on every CLI command.

## 12. CLI

```bash
cd modules/strategy
python -m crypto_strategy backtest --symbol BTCUSDT --start 2022-05-01 --end 2026-01-01
python -m crypto_strategy backtest --all
python -m crypto_strategy report                  # regenerate summary from stored metrics
python -m crypto_strategy pipeline                # backtest --all + backtest_summary.md
```

Console script: `strategy` (e.g. `strategy backtest --all`).

## 13. Reports & artifacts

`modules/strategy/reports/`:
- `{SYMBOL}_{market}_backtest.md` — per-symbol report with metrics,
  benchmark comparison, full trade table, a trade-audit JSON example,
  assumptions, configuration, warnings, rejected orders
- `{SYMBOL}_{market}_metrics.json`, `_trades.parquet`, `_equity.parquet`
- `backtest_summary.md` — cross-symbol comparison vs Buy & Hold

Every trade answers "why was this opened": entry conditions JSON,
regime, EMA/ATR/RSI/ADX context, signal → entry timestamps, R multiple.

## 14. Testing

`pytest` from `modules/strategy/`: strategy rules (happy path + every
failing condition), risk sizing math and caps, execution fills (next-open,
slippage, fees, stop/TP, same-candle stop-first), portfolio constraints,
MTF alignment timing, lookahead proofs (prefix invariance + future-tamper),
metric formulas on hand-computed datasets, and end-to-end engine tests
with hand-computed PnL/fees/exit prices.

## 15. Limitations

- v001 baseline **loses money** on the 2022-04→2026 research datasets
  (~31% win rate, negative expectancy after fees) — documented, not tuned.
- Risk-based sizing with a wide 1H-ATR stop can allocate ~100% of cash to
  one position (exposure cap 1.0 permits it); equity stays positive but
  concentration is high.
- Pending orders are never cancelled; they fill at the next available
  open even if the regime flipped in between.
- Single-symbol engine loop (portfolio constraints enforced per symbol);
  multi-symbol portfolio simulation is future work.
- Backtest models: no partial fills, no funding, no intrabar path
  uncertainty beyond the documented fill rules.

## 16. Future work

- Walk-forward evaluation framework (before any optimization).
- Portfolio-level multi-symbol backtesting with shared equity.
- Position-size granularity (lot steps) and configurable max notional.
- Module 3 — Paper Trading will consume Strategy signals + Risk + market
  data to simulate real-time (non-money) trading.
