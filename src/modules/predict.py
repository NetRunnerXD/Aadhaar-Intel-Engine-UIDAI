"""Forecast module — top-4 model bake-off with published metrics."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ai.ollama_client import get_ollama_client
from src.config import FORECAST_CANDIDATES
from src.utils import theme
from src.utils.plots import apply_white_theme, show_plot


def _hist_col(df):
    if "total_enrolments" in df.columns:
        return "total_enrolments"
    if "adult_enrolments" in df.columns:
        return "adult_enrolments"
    return None


def render_forecast_chart(historical_df, forecast_df):
    col = _hist_col(historical_df)
    if col is None:
        st.warning("No volume column available for historical series.")
        return

    fig = go.Figure()
    recent_history = (
        historical_df.sort_values("date")
        .groupby("date", observed=True)[col]
        .sum()
        .reset_index()
        .tail(90)
    )
    fig.add_trace(
        go.Scatter(
            x=recent_history["date"],
            y=recent_history[col],
            mode="lines",
            name="Historical",
            line=dict(color="#2563eb", width=3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=pd.concat([forecast_df["date"], forecast_df["date"][::-1]]),
            y=pd.concat([forecast_df["upper"], forecast_df["lower"][::-1]]),
            fill="toself",
            fillcolor="rgba(37, 99, 235, 0.12)",
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            name="Interval",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast_df["date"],
            y=forecast_df["predicted"],
            mode="lines",
            name="Forecast",
            line=dict(color="#d97706", width=3, dash="dash"),
        )
    )
    apply_white_theme(
        fig,
        title="<b>Enrolment volume forecast</b>",
        height=460,
        margin=dict(l=48, r=24, t=64, b=48),
        rangemode="tozero",
        legend=dict(orientation="h", y=1.12, x=0),
        hovermode="x unified",
        xaxis_title="Date",
        yaxis_title="Daily enrolments",
    )
    show_plot(fig, height=460)


def render_resource_planning(forecast_df):
    theme.section_title("Resource planning")
    AVG_ENROL_PER_OP = 40
    peak_vol = float(forecast_df["predicted"].max())
    avg_vol = float(forecast_df["predicted"].mean())
    ops_needed = int(np.ceil(peak_vol / AVG_ENROL_PER_OP))
    theme.kpi_row(
        [
            {"label": "Operators (40/day)", "value": ops_needed, "accent": "blue", "format": False},
            {"label": "Peak daily", "value": int(peak_vol), "accent": "amber"},
            {"label": "Avg daily", "value": int(avg_vol), "accent": "slate"},
        ]
    )
    st.caption("Constants are configurable assumptions, not certified capacity standards.")


def render_tab(engine, df_enrol):
    theme.page_header("Forecast")
    st.caption(
        "Top-4 model bake-off (MovingAverage · Drift · Ensemble · SeasonalNaive). "
        "Auto ranks by MASE and only accepts a model that beats SeasonalNaive and MovingAverage. "
        "Intervals: split conformal residual quantile."
    )

    if df_enrol is None or df_enrol.empty:
        st.warning("No enrolment data for current filters.")
        return

    status = get_ollama_client().status()
    theme.status_pills(
        [
            (
                "ok" if status.available else "warn",
                f"LLM · {status.model}" if status.available else "LLM offline · engine analysis",
            )
        ]
    )

    c1, c2, c3, c4 = st.columns(4)
    horizon = c1.number_input("Horizon (days)", 7, 90, 30)
    model_choices = ["Auto (beat baselines)"] + list(FORECAST_CANDIDATES)
    model_type = c2.selectbox("Model", model_choices)
    sim_factor = c3.number_input("Shock %", -50, 50, 0)
    growth_factor = sim_factor / 100.0
    algo_arg = "Auto" if model_type.startswith("Auto") else model_type
    state_opts = ["(National)"]
    if "state" in df_enrol.columns:
        state_opts += sorted(df_enrol["state"].astype(str).unique().tolist())
    state_pick = c4.selectbox("Scope", state_opts)
    state_arg = None if state_pick == "(National)" else state_pick

    if "date" not in df_enrol.columns:
        st.error("Date column missing.")
        return

    theme.section_title("Model comparison")
    cmp_df = engine.compare_forecast_models(state=state_arg)
    if cmp_df.empty:
        st.warning("Insufficient history for model comparison.")
    else:
        display = cmp_df.copy()
        display.insert(0, "Rank", range(1, len(display) + 1))
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank": st.column_config.NumberColumn("Rank", format="%d"),
                "mase": st.column_config.NumberColumn("MASE ★", format="%.4f", help="Primary metric"),
                "smape_pct": st.column_config.NumberColumn("sMAPE %", format="%.1f"),
                "rmse": st.column_config.NumberColumn("RMSE", format="%.0f"),
                "nrmse": st.column_config.NumberColumn("nRMSE", format="%.3f"),
            },
        )
        best = cmp_df.iloc[0]
        primary = best.get("primary_metric", "mase")
        st.success(
            f"**#{1} by {primary}: {best['model']}** · MASE={best.get('mase')} · "
            f"sMAPE={best.get('smape_pct')}% · band={best.get('decision_band', '—')}"
        )

    forecast_df, trend_label = engine.forecast_trends(
        horizon=horizon,
        growth_factor=growth_factor,
        model_type=algo_arg,
        state=state_arg,
    )
    if forecast_df is None:
        st.warning("Insufficient history to forecast.")
        return

    meta = engine._last_forecast_meta or {}
    bt = meta.get("backtest") or {}
    roll = meta.get("rolling") or {}

    theme.kpi_row(
        [
            {"label": "Model", "value": trend_label, "accent": "blue", "format": False},
            {"label": "Selection", "value": str(meta.get("selection", "—"))[:18], "accent": "slate", "format": False},
            {
                "label": "MASE",
                "value": roll.get("rolling_mase") if roll.get("rolling_mase") is not None else "n/a",
                "accent": "violet",
                "format": False,
            },
            {
                "label": "sMAPE",
                "value": f"{roll.get('rolling_smape_pct')}%" if roll.get("rolling_smape_pct") is not None else "n/a",
                "accent": "amber",
                "format": False,
            },
            {"label": "Band", "value": meta.get("decision_band") or "—", "accent": "green", "format": False},
            {
                "label": "Conformal q",
                "value": meta.get("conformal_q") if meta.get("conformal_q") is not None else "n/a",
                "accent": "slate",
                "format": False,
            },
        ]
    )
    st.caption(
        f"Primary: **{meta.get('primary_metric', 'mase')}** · "
        f"Intervals: {meta.get('interval_method', 'n/a')} (α={meta.get('conformal_alpha', 'n/a')}) · "
        f"Scope: {state_pick}"
    )

    col_chart, col_text = st.columns([2, 1])
    with col_chart:
        render_forecast_chart(df_enrol, forecast_df)
    with col_text:
        fc_key = f"{trend_label}:{horizon}:{state_pick}:{sim_factor}"
        if st.session_state.get("fc_ai_key") != fc_key:
            st.session_state.pop("fc_ai_text", None)
            st.session_state.fc_ai_key = fc_key
        has_ai = bool(st.session_state.get("fc_ai_text"))
        theme.ai_panel_header(has_content=has_ai)
        if st.button("Generate" if not has_ai else "Regenerate", type="primary", key="fc_ai_btn"):
            with st.spinner("Analyzing current data…"):
                st.session_state.fc_ai_text = engine.generate_forecast_insight(
                    forecast_df, trend_label, use_llm=True
                )
            st.rerun()
        if st.session_state.get("fc_ai_text"):
            st.markdown(st.session_state.fc_ai_text)
        else:
            st.caption("Generate an insight for the current forecast view.")

    st.markdown("---")
    render_resource_planning(forecast_df)

    with st.expander("Forecast table & methods"):
        st.markdown(
            "- **MovingAverage** — 7-day level × DOW shape  \n"
            "- **Drift** — damped first→last trend  \n"
            "- **Ensemble** — median of MA + Drift + SeasonalNaive  \n"
            "- **SeasonalNaive** — lag-7 recursive (MASE scale)  \n"
            "- **Auto** — best MASE only if it beats SeasonalNaive and MA  \n"
            "- **Intervals** — split conformal absolute residual quantile"
        )
        display_df = forecast_df.copy()
        for col in ["predicted", "upper", "lower"]:
            display_df[col] = display_df[col].astype(int)
        display_df.columns = ["Date", "Predicted", "Upper", "Lower"]
        st.dataframe(display_df, use_container_width=True)
        st.download_button(
            "Download CSV",
            display_df.to_csv(index=False).encode("utf-8"),
            "forecast_data.csv",
            "text/csv",
        )
