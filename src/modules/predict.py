"""Predictive engine — multi-model selection with published holdout metrics."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ai.ollama_client import get_ollama_client


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
            line=dict(color="#00f2ff", width=3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=pd.concat([forecast_df["date"], forecast_df["date"][::-1]]),
            y=pd.concat([forecast_df["upper"], forecast_df["lower"][::-1]]),
            fill="toself",
            fillcolor="rgba(0, 242, 255, 0.12)",
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="skip",
            name="P10–P90",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast_df["date"],
            y=forecast_df["predicted"],
            mode="lines",
            name="Forecast",
            line=dict(color="#ff9f43", width=3, dash="dash"),
        )
    )
    fig.update_layout(
        title="<b>Enrolment volume forecast</b>",
        template="plotly_dark",
        height=450,
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(orientation="h", y=1.1),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_resource_planning(forecast_df):
    st.markdown("### Resource planning (illustrative)")
    AVG_ENROL_PER_OP = 40
    peak_vol = float(forecast_df["predicted"].max())
    avg_vol = float(forecast_df["predicted"].mean())
    ops_needed = int(np.ceil(peak_vol / AVG_ENROL_PER_OP))
    c1, c2, c3 = st.columns(3)
    c1.metric("Operators (40/day)", f"{ops_needed}")
    c2.metric("Peak daily", f"{int(peak_vol):,}")
    c3.metric("Avg daily", f"{int(avg_vol):,}")
    st.caption("Constants are configurable research assumptions, not certified capacity standards.")


def render_tab(engine, df_enrol):
    st.markdown("### Predictive Intelligence (research)")
    st.caption(
        "Holdout bake-off across Seasonal / Linear / MovingAverage; auto-select by minimum sMAPE. "
        "Bands are residual-bootstrap P10–P90 — not parametric prediction intervals."
    )

    if df_enrol is None or df_enrol.empty:
        st.warning("No enrolment data for current filters.")
        return

    status = get_ollama_client().status()
    st.caption(
        f"LLM: {'online · ' + status.model if status.available else 'offline (engine research draft)'}"
    )

    with st.expander("Forecast controls", expanded=True):
        c1, c2, c3 = st.columns(3)
        horizon = c1.slider("Horizon (days)", 7, 90, 30)
        model_type = c2.selectbox(
            "Model",
            ["Auto (holdout sMAPE)", "Seasonal", "Linear", "MovingAverage"],
        )
        sim_factor = c3.slider("Scenario shock (%)", -50, 50, 0)
        growth_factor = sim_factor / 100.0
        algo_arg = "Auto" if model_type.startswith("Auto") else model_type

    if "date" not in df_enrol.columns:
        st.error("Date column missing.")
        return

    # Always show bake-off
    st.markdown("#### Model comparison (holdout)")
    cmp_df = engine.compare_forecast_models()
    if cmp_df.empty:
        st.warning("Insufficient history for holdout comparison.")
    else:
        st.dataframe(cmp_df, use_container_width=True, hide_index=True)
        best = cmp_df.iloc[0]
        st.success(
            f"Selected under Auto would be **{best['model']}** "
            f"(sMAPE={best.get('smape_pct')}%, MAPE={best.get('mape_pct')}%, RMSE={best.get('rmse')})."
        )

    forecast_df, trend_label = engine.forecast_trends(
        horizon=horizon, growth_factor=growth_factor, model_type=algo_arg
    )
    if forecast_df is None:
        st.warning("Insufficient history to forecast.")
        return

    meta = engine._last_forecast_meta or {}
    bt = meta.get("backtest") or {}
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Active model", trend_label)
    m2.metric("Selection", meta.get("selection", "—"))
    m3.metric("Holdout MAPE", f"{bt.get('mape_pct')}%" if bt.get("mape_pct") is not None else "n/a")
    m4.metric("Holdout sMAPE", f"{bt.get('smape_pct')}%" if bt.get("smape_pct") is not None else "n/a")
    m5.metric("Holdout RMSE", bt.get("rmse") if bt.get("rmse") is not None else "n/a")

    col_chart, col_text = st.columns([2, 1])
    with col_chart:
        render_forecast_chart(df_enrol, forecast_df)
    with col_text:
        st.subheader("AI insight")
        st.caption("Grounded on holdout metrics + selected model")
        with st.spinner("Writing forecast insight..."):
            insight = engine.generate_forecast_insight(forecast_df, trend_label, use_llm=True)
        st.markdown(insight)

    st.markdown("---")
    render_resource_planning(forecast_df)

    with st.expander("Forecast table + methods note"):
        st.markdown(
            "- **Seasonal:** recent 14-day level × DOW factors + mild split-window trend  \n"
            "- **Linear:** Ridge on calendar day index  \n"
            "- **MovingAverage:** flat 7-day mean  \n"
            "- **Limitations:** no external regressors (holidays, policy); high volatility days inflate error."
        )
        display_df = forecast_df.copy()
        for col in ["predicted", "upper", "lower"]:
            display_df[col] = display_df[col].astype(int)
        display_df.columns = ["Date", "Predicted", "Upper (P90)", "Lower (P10)"]
        st.dataframe(display_df, use_container_width=True)
        st.download_button(
            "Download CSV",
            display_df.to_csv(index=False).encode("utf-8"),
            "forecast_data.csv",
            "text/csv",
        )
