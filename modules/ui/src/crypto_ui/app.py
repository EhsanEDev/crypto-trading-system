"""Lab shell: one app, one tab per module.

Framework-specific (Streamlit). Swapping the UI framework means rewriting
this file + pages/, while core/ stays intact.
"""

from __future__ import annotations

import json as _json

import pandas as pd
import streamlit as st

from crypto_ui.core import dataset
from crypto_ui.core.calibration import diff_labels, recompute_regimes, regime_distribution
from crypto_ui.core.presets import PresetStore
from crypto_ui.theme import register_theme

register_theme()
st.set_page_config(page_title="Crypto Lab", page_icon="🧪", layout="wide", initial_sidebar_state="expanded")


# --------------------------------------------------------------------- #
# cached loaders (streamlit layer around the framework-agnostic core)
# --------------------------------------------------------------------- #

@st.cache_data(show_spinner=False)
def _load_symbol(symbol: str, market: str, timeframe: str = "4h") -> pd.DataFrame:
    return dataset.load_symbol_data(symbol, market, timeframe)


def _recalibrate(ohlcv: pd.DataFrame, overrides: dict):
    return recompute_regimes(ohlcv, overrides)


def _tail(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.iloc[max(0, len(frame) - window):]


# --------------------------------------------------------------------- #
# shell
# --------------------------------------------------------------------- #

st.title("🧪 Crypto Lab")
st.caption("Research · Strategy · Paper Trading — one shell, one tab per module")

markets = dataset.available_markets()
market = st.sidebar.selectbox("Market", markets or ["futures"], index=0)
symbols = dataset.available_symbols(dataset.RESEARCH_DATA_DIR, market)
if not symbols:
    st.error(
        "No research artifacts found. Generate them first:\n\n"
        "```bash\npython -m crypto_research pipeline --all --allow-non-ready\n```"
    )
    st.stop()
symbol = st.sidebar.selectbox("Symbol", symbols)

overrides: dict = {}
with st.sidebar:
    st.subheader("Calibration")
    st.caption("Overrides applied live · baseline = config/default.yaml")
    overrides["adx_trend_threshold"] = st.slider("ADX trend threshold", 0.0, 60.0, 20.0, 1.0)
    overrides["volatility_percentile"] = st.slider("Volatility percentile", 50.0, 100.0, 90.0, 1.0)
    overrides["volatility_lookback"] = st.slider("Volatility lookback (bars)", 20, 500, 200, 10)
    overrides["slope_lookback"] = st.slider("EMA slope lookback (bars)", 1, 30, 5, 1)
    fast = st.slider("EMA fast", 5, 100, 50, 5)
    slow = st.slider("EMA slow", 100, 400, 200, 25)
    if fast >= slow:
        st.error("EMA fast must be < EMA slow")
    else:
        overrides["ema_fast"], overrides["ema_slow"] = fast, slow

tab_regimes, tab_compare, tab_presets = st.tabs(
    ["📊 Regimes", "🔍 Compare", "💾 Presets"]
)
with tab_presets:
    st.info("Phase 3 — saved calibration presets come here.")

# --------------------------------------------------------------------- #
# shared computation (one recalibration per run, reused by both tabs)
# --------------------------------------------------------------------- #

raw_frame = _load_symbol(symbol, market)
ohlcv = raw_frame[["open", "high", "low", "close", "volume"]]



@st.cache_data(show_spinner="Recalibrating…")
def _calibrate(_ohlcv: pd.DataFrame, overrides_json: str) -> pd.DataFrame:
    """Candidate frame cached on the override set (baseline cached too)."""
    return _recalibrate(_ohlcv, dict(_json.loads(overrides_json))).frame


overrides_json = _json.dumps(overrides, sort_keys=True)
baseline_frame = _calibrate(ohlcv, "{}")
candidate_frame = _calibrate(ohlcv, overrides_json)
window = st.slider(
    "Window (trailing candles)", min_value=300, max_value=len(raw_frame),
    value=min(2000, len(raw_frame)), step=100,
    help="Displayed trailing window (calibration always uses full history)",
)


diff = diff_labels(baseline_frame["regime"], candidate_frame["regime"])

with tab_compare:
    from crypto_ui.pages import compare as compare_page

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Changed candles",
        f"{diff['changed_candles']:,}",
        f"{diff['changed_pct']:.1f}% of {len(baseline_frame):,}",
    )
    c2.metric(
        "Baseline top regime",
        max(diff["baseline_distribution"], key=diff["baseline_distribution"].get),
    )
    c3.metric(
        "Candidate top regime",
        max(diff["candidate_distribution"], key=diff["candidate_distribution"].get),
    )

    frame = _tail(candidate_frame, window)
    baseline_labels = baseline_frame["regime"].loc[frame.index]
    candidate_labels = candidate_frame["regime"].loc[frame.index]

    st.plotly_chart(
        compare_page.build_strips_figure(frame, baseline_labels, candidate_labels),
        width="stretch", config={"displaylogo": False},
    )

    bar1, bar2 = st.columns(2)
    with bar1:
        st.plotly_chart(
            compare_page.distribution_bars(
                diff["baseline_distribution"], diff["candidate_distribution"]
            ),
            width="stretch", config={"displaylogo": False},
        )
    with bar2:
        st.markdown("**Label changes (baseline → candidate)**")
        if diff["pairs"]:
            for pair, count in compare_page.transition_rows(diff):
                st.markdown(f"- `{pair}` — **{count:,}** candles")
        else:
            st.caption("No label changes — the candidate config equals the baseline.")

    st.caption(
        "Both label sets come from the same pure detector the CLI uses "
        "(no lookahead); overrides are exactly the sidebar sliders."
    )

with tab_regimes:
    st.markdown("Regime labels over candles — recalibrate thresholds live.")

    col1, col2 = st.columns([2, 3])
    col1.metric("Candles (total)", f"{len(raw_frame):,}")
    col2.metric(
        "Range",
        f"{raw_frame.index.min():%Y-%m-%d} → {raw_frame.index.max():%Y-%m-%d}",
    )

    frame = _tail(candidate_frame, window)

    from crypto_ui.pages import regimes as regimes_page

    fig = regimes_page.build_figure(frame, timeframe="4h")
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

    st.markdown(
        f"**Distribution (this window)** · "
        f"{regimes_page.distribution_html(regime_distribution(frame))}",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Overrides: {overrides or 'none (baseline)'} — labels come from the "
        f"same pure detector the CLI uses (no lookahead)."
    )

    st.divider()
    st.subheader("Save as preset")
    pcol1, pcol2 = st.columns([3, 1])
    preset_name = pcol1.text_input("Preset name", placeholder="e.g. looser_adx_25",
                                   label_visibility="collapsed")
    if pcol2.button("💾 Save preset", disabled=not preset_name, use_container_width=True):
        try:
            path = PresetStore().save(preset_name, dict(overrides), note=f"{symbol} {market}")
            st.success(f"Saved → {path}")
        except Exception as exc:
            st.error(str(exc))
