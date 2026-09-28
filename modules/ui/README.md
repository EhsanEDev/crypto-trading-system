# Module — Lab UI (`crypto_ui`)

Interactive shell for the crypto-trading-system modules: one app, one tab
per module. Phase 1 ships the **Regimes Explorer** — candlestick charts
with regime shading and live threshold calibration against the research
module's pure detector.

## Run

```bash
# from the repository root or modules/ui — works from any directory:
modules/ui/run.sh              # activates the project venv automatically
modules/ui/run.sh --port 8505  # custom port
# equivalents:
python modules/ui/run.py
python -m crypto_ui            # with the venv activated
crypto-ui                      # console script
```

The app boots at http://localhost:8501 (dark theme, telemetry off, browser
opens automatically). If Streamlit is missing from the current
interpreter, `run.py` re-executes itself with the project `.venv`.

## Architecture — swappable by design

```text
src/crypto_ui/
├── core/            # framework-agnostic logic (NO streamlit imports)
│   ├── dataset.py       # research artifacts discovery/loading (cached)
│   ├── calibration.py   # live recompute: research public API + overrides
│   └── presets.py       # named YAML presets with fingerprints
├── pages/regimes.py # presentation layer (streamlit + plotly)
├── app.py           # shell: sidebar calibration, tabs, cached loaders
├── launcher.py      # single entry: boots streamlit, dark theme, telemetry off
└── theme/           # regime palette + plotly dark template
```

**Swap rule:** `core/` depends only on pandas + the research public API
(`detect_regime`, `compute_indicators`). If the presentation framework
changes (Dash, NiceGUI, ...), only `app.py` + `pages/` are rewritten.

**Dependency direction:** research → (read-only) ← ui. The UI never
mutates research data; recalibration happens in memory via the same pure
detector the CLI uses (no lookahead, byte-consistent with CLI results —
asserted by a test).

## Regimes tab

- Candlestick chart (Plotly, dark) with one shaded band per contiguous
  regime run + a regime strip below the price panel
- EMA50/EMA200 overlays; RSI14/ADX14 sub-panels; hover shows OHLC +
  regime + `regime_reason`
- Sidebar calibration: ADX trend threshold, volatility percentile and
  lookback, slope lookback, EMA fast/slow — recomputed instantly on the
  selected trailing window
- Distribution chips for the window; save calibration as a named preset
  (`configs/presets/{name}.yaml`, with fingerprint + note)

## Presets

Saved presets are directly usable by the research CLI:

```bash
python -m crypto_research report --symbol BTCUSDT --timeframe 4h \
    --config configs/presets/loose_adx.yaml
```

## Roadmap (tabs)

- [x] Regimes Explorer (Phase 1)
- [ ] Compare (Phase 2): baseline vs candidate labels + delta statistics
- [ ] Presets manager (Phase 3): diff table vs defaults
- [ ] Strategy tab: equity curve + entry/exit markers (reads strategy reports)
- [ ] Paper Trading tab (Module 3)

## Testing

`core/` is fully tested (5 tests): artifact discovery/loading, live
calibration equivalence with the stored artifact (zero overrides),
override effects on regime distribution, config validation, preset
round-trip. The presentation layer is kept thin so core coverage matters.
