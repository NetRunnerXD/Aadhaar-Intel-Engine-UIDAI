"""Executive / research dashboard."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.ai.ollama_client import get_ollama_client
from src.config import ANOMALY_CONTAMINATION, ANOMALY_MIN_VOLUME


def go_to_governance():
    st.session_state.current_page = "Data Governance"


def _safe_sum(df, col):
    if df is None or df.empty or col not in df.columns:
        return 0
    return float(df[col].sum())


def render_kpi_row(df_enrol, df_bio, df_demo, anomaly_count, forecast_growth, mape=None, smape=None):
    total_enrol = _safe_sum(df_enrol, "total_enrolments")
    adult_enrol = _safe_sum(df_enrol, "adult_enrolments")
    if total_enrol == 0 and adult_enrol > 0:
        total_enrol = adult_enrol
    total_bio = _safe_sum(df_bio, "bio_stress")
    total_demo = _safe_sum(df_demo, "update_volume")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Enrolments", f"{total_enrol:,.0f}", delta=f"18+: {adult_enrol:,.0f}")
    c2.metric("Biometric Updates", f"{total_bio:,.0f}")
    c3.metric("Demographic Updates", f"{total_demo:,.0f}")
    c4.metric(
        "Risk cells",
        f"{anomaly_count}",
        delta="IsolationForest",
        delta_color="inverse" if anomaly_count else "off",
    )
    delta = f"sMAPE {smape}%" if smape is not None else (f"MAPE {mape}%" if mape is not None else "30d")
    c5.metric("Forecast Δ", f"{forecast_growth:.1f}%", delta=delta)


def render_age_mix(df_enrol):
    if df_enrol is None or df_enrol.empty:
        return
    parts = []
    for col, label in (("age_0_5", "0–5"), ("age_5_17", "5–17"), ("age_18_greater", "18+")):
        if col in df_enrol.columns:
            parts.append({"Band": label, "Volume": float(df_enrol[col].sum())})
    if not parts or sum(p["Volume"] for p in parts) <= 0:
        return
    fig = px.pie(
        pd.DataFrame(parts),
        values="Volume",
        names="Band",
        hole=0.55,
        title="<b>Enrolment age mix</b>",
        color_discrete_sequence=["#38bdf8", "#818cf8", "#00f2ff"],
    )
    fig.update_layout(height=280, margin=dict(l=0, r=0, t=40, b=0), template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)


def render_anomaly_section(engine, contamination, min_volume):
    st.markdown("---")
    st.subheader("Anomaly investigation (state × district)")
    anom_df = engine.get_anomalies(contamination=contamination, min_volume=min_volume, force=True)
    anomaly_count = len(anom_df) if anom_df is not None else 0

    if anomaly_count == 0:
        st.success("No multi-feature outliers under current thresholds.")
        return anomaly_count

    st.warning(
        f"{anomaly_count} cells flagged · contamination={contamination} · min_volume={min_volume}. "
        "Flags are statistical outliers, not verified fraud."
    )
    c1, c2 = st.columns([3, 1])
    with c1:
        y_col = "district" if "district" in anom_df.columns else anom_df.columns[0]
        fig = px.bar(
            anom_df.head(10),
            x="risk_score",
            y=y_col,
            orientation="h",
            color="risk_score",
            color_continuous_scale="Reds",
            hover_data=[c for c in ("state", "reason", "volume", "driver_z") if c in anom_df.columns],
            title="<b>Top risk cells</b>",
        )
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig, use_container_width=True)
        show_cols = [
            c
            for c in (
                "state",
                "district",
                "volume",
                "risk_score",
                "reason",
                "bio_ratio",
                "demo_ratio",
                "cv",
                "investigation_notes",
            )
            if c in anom_df.columns
        ]
        st.dataframe(anom_df[show_cols].head(15), use_container_width=True, hide_index=True)
    with c2:
        st.info("**Unit of analysis** is composite `(state, district)`.")
        st.button("Open Governance", type="primary", use_container_width=True, on_click=go_to_governance)
        with st.expander("Top investigation note"):
            if "investigation_notes" in anom_df.columns:
                st.write(anom_df.iloc[0]["investigation_notes"])
    return anomaly_count


def render_recent_activity(logs):
    with st.expander("System logs", expanded=False):
        if logs:
            st.dataframe(pd.DataFrame({"Log": logs}).tail(20), use_container_width=True, hide_index=True)
        else:
            st.info("No logs.")


def render_dashboard(engine, df_enrol, df_bio, df_demo, logs, anomaly_count):
    st.markdown("## Research Dashboard")
    st.caption(
        f"Updated {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} · correlational / operational analytics"
    )

    status = get_ollama_client().status()
    if status.available:
        st.success(f"LLM online · `{status.model}`")
    else:
        st.warning(f"LLM offline — insights use engine research drafts ({status.error})")

    if df_enrol is None or df_enrol.empty:
        st.warning("No enrolment rows in current filter.")
        render_recent_activity(logs)
        return

    with st.expander("Anomaly parameters", expanded=False):
        c1, c2 = st.columns(2)
        contamination = c1.slider("Contamination", 0.01, 0.15, float(ANOMALY_CONTAMINATION), 0.01)
        min_volume = c2.number_input("Min volume (cell)", 0, 100000, int(ANOMALY_MIN_VOLUME), 10)

    fc_df, model_label = engine.forecast_trends(horizon=30, model_type="Auto")
    growth = 0.0
    mape = smape = None
    if fc_df is not None and not fc_df.empty:
        start, end = fc_df.iloc[0]["predicted"], fc_df.iloc[-1]["predicted"]
        if start > 0:
            growth = ((end - start) / start) * 100
        bt = (engine._last_forecast_meta or {}).get("backtest") or {}
        mape, smape = bt.get("mape_pct"), bt.get("smape_pct")

    # recompute anomalies with UI params for count + section
    anom_count = len(engine.get_anomalies(contamination=contamination, min_volume=min_volume, force=True))

    render_kpi_row(df_enrol, df_bio, df_demo, anom_count, growth, mape=mape, smape=smape)

    with st.expander("AI research brief", expanded=True):
        st.caption("Narrative from LLM (if online) · numbers always from the analytics engine")
        c_r1, c_r2 = st.columns([1, 3])
        with c_r1:
            if st.button("Refresh brief", type="primary"):
                st.session_state.pop("dash_ai_text", None)
                st.session_state.pop("dash_ai_key", None)
        # Refresh when anomaly count changes
        brief_key = f"{anom_count}:{int(_safe_sum(df_enrol, 'total_enrolments'))}"
        if st.session_state.get("dash_ai_key") != brief_key:
            st.session_state.pop("dash_ai_text", None)
            st.session_state.dash_ai_key = brief_key
        if "dash_ai_text" not in st.session_state:
            with st.spinner("Writing grounded research brief..."):
                st.session_state.dash_ai_text = engine.generate_dashboard_insight(
                    anom_count, use_llm=True
                )
        st.markdown(st.session_state.dash_ai_text)

    left, right = st.columns(2)
    with left:
        render_age_mix(df_enrol)
    with right:
        corr = engine.get_correlation()
        if not corr.empty:
            vals = [corr["Enrolments"].sum(), corr["Bio_Updates"].sum(), corr["Demo_Updates"].sum()]
            fig = px.pie(
                values=vals,
                names=["Enrolments", "Bio", "Demo"],
                hole=0.55,
                title="<b>Workload mix</b>",
                color_discrete_sequence=["#10b981", "#f59e0b", "#8b5cf6"],
            )
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=40, b=0), template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

    render_anomaly_section(engine, contamination, min_volume)

    st.markdown("---")
    st.subheader(f"30-day outlook · model **{model_label}**")
    if fc_df is not None and not fc_df.empty:
        c1, c2 = st.columns([3, 1])
        with c1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=fc_df["date"], y=fc_df["upper"], line=dict(width=0), showlegend=False))
            fig.add_trace(
                go.Scatter(
                    x=fc_df["date"],
                    y=fc_df["lower"],
                    fill="tonexty",
                    fillcolor="rgba(0,242,255,0.12)",
                    line=dict(width=0),
                    name="P10–P90",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=fc_df["date"],
                    y=fc_df["predicted"],
                    line=dict(color="#00f2ff", width=2),
                    name="Point forecast",
                )
            )
            fig.update_layout(height=240, template="plotly_dark", margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.metric("Peak", f"{int(fc_df['predicted'].max()):,}")
            st.metric("Floor", f"{int(fc_df['predicted'].min()):,}")
            if smape is not None:
                st.metric("Holdout sMAPE", f"{smape}%")
            cmp = (engine._last_forecast_meta or {}).get("model_comparison") or []
            if cmp:
                st.caption("Bake-off: " + ", ".join(f"{r['model']}={r.get('smape_pct')}%" for r in cmp))

    render_recent_activity(logs)
