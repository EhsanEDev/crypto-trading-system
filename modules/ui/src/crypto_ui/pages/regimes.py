"""Regimes Explorer page: candlestick + regime shading + live calibration.

Presentation layer only: all data/logic comes from ``crypto_ui.core`` and
the research public API. Swapping the UI framework means rewriting this
file (and app.py), nothing else.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..theme import DARK_LAYOUT, REGIME_COLORS, REGIME_EDGE_COLORS


def build_figure(
    frame: pd.DataFrame,
    timeframe: str = "4h",
    show_emas: bool = True,
) -> go.Figure:
    """Candlestick chart with per-regime background bands + indicator panels."""
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.56, 0.16, 0.16, 0.06],
        subplot_titles=("Price / Regime", "RSI14", "ADX14", None),
    )

    fig.add_trace(
        go.Candlestick(
            x=frame.index, open=frame["open"], high=frame["high"],
            low=frame["low"], close=frame["close"],
            name="OHLC", increasing_line_color="#26a65b", decreasing_line_color="#d93e3e",
            increasing_fillcolor="#26a65b", decreasing_fillcolor="#d93e3e",
            customdata=_hover_customdata(frame),
            hovertemplate=(
                "%{x}<br>"
                "O %{customdata[0]:.4g} · H %{customdata[1]:.4g} "
                "L %{customdata[2]:.4g} C %{customdata[3]:.4g}<br>"
                "Regime: %{customdata[4]}<br>"
                "<span style='font-size:11px'>%{customdata[5]}</span>"
                "<extra></extra>"
            ),
        ),
        row=1, col=1,
    )
    if show_emas:
        for column, name, color in (
            ("ema50", "EMA50", "#f2c94c"), ("ema200", "EMA200", "#8d7df2"),
        ):
            if column in frame.columns:
                fig.add_trace(
                    go.Scatter(x=frame.index, y=frame[column], name=name,
                               line=dict(color=color, width=1.4)),
                    row=1, col=1,
                )

    fig.add_trace(
        go.Scatter(x=frame.index, y=frame["rsi14"], name="RSI14",
                   line=dict(color="#4da3ff", width=1.2)),
        row=2, col=1,
    )
    fig.add_hline(y=50, line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dot"), row=2, col=1)
    fig.add_trace(
        go.Scatter(x=frame.index, y=frame["adx14"], name="ADX14",
                   line=dict(color="#e6a22a", width=1.2)),
        row=3, col=1,
    )

    _add_regime_bands(fig, frame)
    fig.update_layout(**DARK_LAYOUT, height=780)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
    fig.update_yaxes(title_text="ADX", row=3, col=1)
    fig.update_yaxes(visible=False, range=[0, 1.4], row=4, col=1)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])] if timeframe == "1d" else [])
    return fig


def _hover_customdata(frame: pd.DataFrame) -> list[list]:
    return [
        [row["open"], row["high"], row["low"], row["close"],
         row["regime"], row.get("regime_reason", "")]
        for _, row in frame.iterrows()
    ]


def _add_regime_bands(fig: go.Figure, frame: pd.DataFrame) -> None:
    """One shaded band per contiguous regime run.

    Bulk-applied: shapes and strip segments are collected first and added
    in single calls (per-shape add_vrect re-serializes the whole figure
    and is O(n) per call — minutes slow for 2000 candles).
    """
    regimes = frame["regime"].tolist()
    index = frame.index
    bands: list[dict] = []
    strip: dict[str, list] = {}
    start = 0
    for i in range(1, len(regimes) + 1):
        if i == len(regimes) or regimes[i] != regimes[start]:
            label = regimes[start]
            bands.append({
                "type": "rect", "xref": "x", "yref": "paper",
                "x0": index[start], "x1": index[i - 1], "y0": 0.0, "y1": 1.0,
                "fillcolor": REGIME_COLORS.get(label, "rgba(140,140,150,0.1)"),
                "line": {"width": 0}, "layer": "below",
            })
            color = REGIME_EDGE_COLORS.get(label, "#8c8c96")
            segment = strip.setdefault(color, [[], []])
            segment[0] += [index[start], index[i - 1], None]
            segment[1] += [1.0, 1.0, None]
            start = i
    if bands:
        fig.update_layout(shapes=bands)
    for color, (xs, ys) in strip.items():
        fig.add_trace(
            go.Scatter(
                x=xs, y=ys, mode="lines",
                line=dict(width=6, color=color),
                name="Regime strip", showlegend=False, hoverinfo="skip",
                connectgaps=False,
            ),
            row=4, col=1,
        )


def distribution_html(distribution: dict[str, float]) -> str:
    parts = []
    for label, pct in distribution.items():
        color = REGIME_EDGE_COLORS.get(label, "#8c8c96")
        parts.append(
            f"<span style='color:{color}; font-weight:600'>{label}</span> {pct:.1f}%"
        )
    return " · ".join(parts)
