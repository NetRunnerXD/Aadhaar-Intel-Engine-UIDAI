"""Shared Plotly styling — white backgrounds with correct axis scaling."""
from __future__ import annotations

from typing import Any, Optional

import streamlit as st

PLOTLY_TEMPLATE = "plotly_white"

DEFAULT_MARGIN = dict(l=48, r=24, t=52, b=48)

PLOTLY_CONFIG = {
    "responsive": True,
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}


def apply_white_theme(fig, *, rangemode: Optional[str] = None, **extra_layout):
    """
    White chart chrome without clobbering axis types / autorange / category order.

    Use update_xaxes / update_yaxes for styling so Plotly keeps the scale the
    chart builder already chose (linear, category, date, log, …).
    """
    xaxis_extra = extra_layout.pop("xaxis", None) or {}
    yaxis_extra = extra_layout.pop("yaxis", None) or {}
    xaxis_title = extra_layout.pop("xaxis_title", None)
    yaxis_title = extra_layout.pop("yaxis_title", None)
    legend_extra = extra_layout.pop("legend", None)

    margin = dict(DEFAULT_MARGIN)
    if extra_layout.get("margin") is not None:
        margin.update(extra_layout["margin"])
    extra_layout["margin"] = margin

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(color="#1e293b", family="Segoe UI, sans-serif", size=12),
        title_font=dict(color="#0f172a", size=14),
        autosize=True,
        **extra_layout,
    )

    legend = dict(
        bgcolor="rgba(255,255,255,0.95)",
        font=dict(color="#334155", size=11),
    )
    if isinstance(legend_extra, dict):
        legend.update(legend_extra)
    fig.update_layout(legend=legend)

    fig.update_layout(
        coloraxis_colorbar=dict(
            tickfont=dict(color="#475569"),
            title_font=dict(color="#334155"),
        )
    )

    x_kwargs: dict[str, Any] = dict(
        showgrid=True,
        gridcolor="#e2e8f0",
        gridwidth=1,
        zeroline=False,
        showline=True,
        linecolor="#94a3b8",
        tickfont=dict(color="#475569", size=11),
        title_font=dict(color="#334155", size=12),
        automargin=True,
        fixedrange=False,
        autorange=True,
    )
    y_kwargs: dict[str, Any] = dict(
        showgrid=True,
        gridcolor="#e2e8f0",
        gridwidth=1,
        zeroline=False,
        showline=True,
        linecolor="#94a3b8",
        tickfont=dict(color="#475569", size=11),
        title_font=dict(color="#334155", size=12),
        automargin=True,
        fixedrange=False,
        autorange=True,
    )

    if rangemode in ("tozero", "nonnegative", "normal"):
        y_kwargs["rangemode"] = rangemode

    if xaxis_title is not None:
        x_kwargs["title"] = xaxis_title
    if yaxis_title is not None:
        y_kwargs["title"] = yaxis_title

    if isinstance(xaxis_extra, dict):
        x_kwargs.update(xaxis_extra)
    if isinstance(yaxis_extra, dict):
        y_kwargs.update(yaxis_extra)

    # Drop empty range so autorange is not blocked
    for kwargs in (x_kwargs, y_kwargs):
        if kwargs.get("range") in (None, [], ()):
            kwargs.pop("range", None)
        # If an explicit range is set, don't force autorange
        if "range" in kwargs:
            kwargs["autorange"] = False

    fig.update_xaxes(**x_kwargs)
    fig.update_yaxes(**y_kwargs)
    return fig


def show_plot(fig, *, height: Optional[int] = None, key: Optional[str] = None):
    """Full-width responsive Plotly render."""
    if height is not None:
        fig.update_layout(height=int(height))
    kwargs = dict(use_container_width=True, config=PLOTLY_CONFIG)
    if key is not None:
        kwargs["key"] = key
    st.plotly_chart(fig, **kwargs)
