"""Compare page: baseline vs candidate regimes (Phase 2).

Presentation layer: candlestick + three label strips (baseline / candidate
/ diff) and a grouped distribution bar chart. Logic comes from core.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..theme import DARK_LAYOUT, REGIME_EDGE_COLORS

STRIP_ROW = {"baseline": 2, "candidate": 3, "diff": 4}


def build_strips_figure(
    frame: pd.DataFrame, baseline_labels: pd.Series, candidate_labels: pd.Series
) -> go.Figure:
    """Thin price panel + baseline/candidate strips + change markers."""
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.52, 0.16, 0.16, 0.16],
        subplot_titles=("Price", "Baseline (defaults)", "Candidate (sidebar)", "Differences"),
    )

    fig.add_trace(
        go.Candlestick(
            x=frame.index, open=frame["open"], high=frame["high"],
            low=frame["low"], close=frame["close"], name="OHLC",
            increasing_line_color="#3a3f4b", decreasing_line_color="#3a3f4b",
            increasing_fillcolor="#3a3f4b", decreasing_fillcolor="#22252e",
        ),
        row=1, col=1,
    )

    _add_strip(fig, frame.index, baseline_labels, "Baseline", STRIP_ROW["baseline"])
    _add_strip(fig, frame.index, candidate_labels, "Candidate", STRIP_ROW["candidate"])

    changed = baseline_labels != candidate_labels
    fig.add_trace(
        go.Scatter(
            x=frame.index[changed], y=[1.0] * int(changed.sum()),
            mode="markers", marker=dict(symbol="x", size=6, color="#ff5470"),
            name="changed", hovertemplate="%{x}: %{customdata}<extra></extra>",
            customdata=[
                f"{a} → {b}" for a, b in zip(baseline_labels[changed], candidate_labels[changed])
            ],
        ),
        row=STRIP_ROW["diff"], col=1,
    )
    fig.update_layout(**DARK_LAYOUT, height=620)
    fig.update_yaxes(visible=False, range=[0, 1.4])
    fig.update_yaxes(title_text="Price", row=1, col=1, showticklabels=True, visible=True)
    fig.update_layout(legend=dict(orientation="h", y=1.06))
    return fig


def _add_strip(fig: go.Figure, index, labels: pd.Series, name: str, row: int) -> None:
    """Draw one contiguous colored segment per regime run."""
    values = labels.tolist()
    start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[start]:
            label = values[start]
            fig.add_trace(
                go.Scatter(
                    x=[index[start], index[i - 1]], y=[1, 1],
                    mode="lines",
                    line=dict(width=10, color=REGIME_EDGE_COLORS.get(label, "#8c8c96")),
                    name=name, showlegend=(row == STRIP_ROW["baseline"] and start == 0),
                    hovertemplate=f"{name}: {label}<extra></extra>",
                ),
                row=row, col=1,
            )
            start = i


def distribution_bars(baseline_dist: dict[str, float], candidate_dist: dict[str, float]) -> go.Figure:
    """Grouped bars: baseline vs candidate share per regime."""
    labels = list(baseline_dist.keys())
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=[baseline_dist[k] for k in labels], name="Baseline",
        marker_color=[REGIME_EDGE_COLORS.get(k, "#8c8c96") for k in labels],
        opacity=0.45,
    ))
    fig.add_trace(go.Bar(
        x=labels, y=[candidate_dist[k] for k in labels], name="Candidate",
        marker_color=[REGIME_EDGE_COLORS.get(k, "#8c8c96") for k in labels],
    ))
    fig.update_layout(**DARK_LAYOUT, height=320, barmode="group")
    fig.update_yaxes(title_text="share %")
    return fig


def transition_rows(diff: dict) -> list[tuple[str, int]]:
    """Sorted (baseline -> candidate, count) pairs for table rendering."""
    return sorted(diff.get("pairs", {}).items(), key=lambda kv: -kv[1])
