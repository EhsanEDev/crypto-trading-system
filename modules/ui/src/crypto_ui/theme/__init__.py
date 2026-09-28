"""Theme: regime palette + dark plotly templates (framework-light)."""

from __future__ import annotations

import plotly.io as pio

REGIME_COLORS = {
    "TREND_UP": "rgba(38, 166, 91, 0.14)",        # green
    "TREND_DOWN": "rgba(217, 62, 62, 0.14)",      # red
    "RANGE": "rgba(86, 130, 187, 0.12)",          # steel blue
    "HIGH_VOLATILITY": "rgba(230, 162, 42, 0.18)",  # amber
    "UNCERTAIN": "rgba(140, 140, 150, 0.10)",     # light gray
}

REGIME_EDGE_COLORS = {
    "TREND_UP": "#26a65b",
    "TREND_DOWN": "#d93e3e",
    "RANGE": "#5682bb",
    "HIGH_VOLATILITY": "#e6a22a",
    "UNCERTAIN": "#8c8c96",
}

# streamlit theme flags (passed by the launcher; independent of CWD)
STREAMLIT_THEME_FLAGS = {
    "theme.base": "dark",
    "theme.primaryColor": "#4da3ff",
    "theme.backgroundColor": "#0e1117",
    "theme.secondaryBackgroundColor": "#161a23",
    "theme.textColor": "#e8eaf0",
}

DARK_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, Segoe UI, sans-serif", color="#e8eaf0"),
    margin=dict(l=8, r=16, t=28, b=8),
    hovermode="x unified",
    xaxis=dict(gridcolor="rgba(255,255,255,0.06)", rangeslider=dict(visible=False)),
    yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
    legend=dict(orientation="h", yanchor="bottom", y=1.0, bgcolor="rgba(0,0,0,0)"),
)


def register_theme() -> None:
    """Register the lab dark template for plotly."""
    if "lab_dark" not in pio.templates:
        import plotly.graph_objects as go

        template = go.layout.Template()
        template.layout = go.Layout(**{k: v for k, v in DARK_LAYOUT.items()
                                       if k not in ("template", "hovermode")})
        template.layout.hovermode = "x unified"
        pio.templates["lab_dark"] = template
        pio.templates.default = "plotly_dark+lab_dark"
