"""Executive / research dashboard."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.ai.ollama_client import get_ollama_client
from src.components.navigation import go_to_governance
from src.config import ANOMALY_CONTAMINATION, ANOMALY_MIN_VOLUME
from src.utils import theme
from src.utils.plots import apply_white_theme, show_plot


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
    growth_positive = (forecast_growth or 0) >= 0
    delta = f"sMAPE {smape}%" if smape is not None else (f"MAPE {mape}%" if mape is not None else "30-day horizon")
    theme.kpi_row(
        [
            {
                "label": "Total enrolments",
                "value": total_enrol,
                "delta": f"18+: {theme.fmt_num(adult_enrol)}",
                "accent": "blue",
                "icon": "users",
            },
            {"label": "Biometric updates", "value": total_bio, "accent": "green", "icon": "fingerprint"},
            {"label": "Demographic updates", "value": total_demo, "accent": "violet", "icon": "id"},
            {
                "label": "Risk cells",
                "value": anomaly_count,
                "delta": "IsolationForest",
                "accent": "rose" if anomaly_count else "slate",
                "icon": "shield",
            },
            {
                "label": "Forecast Δ",
                "value": f"{'+' if growth_positive else ''}{forecast_growth:.1f}%",
                "delta": delta,
                "accent": "amber" if growth_positive else "rose",
                "icon": "trend",
                "format": False,
            },
        ]
    )


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
        color_discrete_sequence=["#0ea5e9", "#6366f1", "#2563eb"],
    )
    apply_white_theme(fig, height=300, margin=dict(l=20, r=20, t=48, b=20))
    show_plot(fig, height=300)


def render_anomaly_section(engine, contamination, min_volume):
    head_l, head_r = st.columns([4, 1.3])
    with head_l:
        theme.section_title("Anomaly investigation")
    with head_r:
        st.button("Open Governance", type="primary", use_container_width=True, on_click=go_to_governance)

    anom_df = engine.get_anomalies(contamination=contamination, min_volume=min_volume, force=True)
    anomaly_count = len(anom_df) if anom_df is not None else 0

    if anomaly_count == 0:
        st.success("No multi-feature outliers under current contamination and volume thresholds.")
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
        apply_white_theme(
            fig,
            height=360,
            margin=dict(l=8, r=20, t=48, b=24),
            rangemode="tozero",
            xaxis_title="Risk score",
            yaxis_title=None,
        )
        show_plot(fig, height=360)
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
        with st.expander("Show investigation note"):
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
    theme.page_header("Dashboard")

    if df_enrol is None or df_enrol.empty:
        st.warning("No enrolment rows in current filter.")
        render_recent_activity(logs)
        return

    c1, c2 = st.columns(2)
    contamination = c1.number_input("Contamination", 0.01, 0.15, float(ANOMALY_CONTAMINATION), 0.01)
    min_volume = c2.number_input("Min volume", 0, 100000, int(ANOMALY_MIN_VOLUME), 10)

    fc_df, model_label = engine.forecast_trends(horizon=30, model_type="Auto")
    growth = 0.0
    mape = smape = None
    if fc_df is not None and not fc_df.empty:
        start, end = fc_df.iloc[0]["predicted"], fc_df.iloc[-1]["predicted"]
        if start > 0:
            growth = ((end - start) / start) * 100
        bt = (engine._last_forecast_meta or {}).get("backtest") or {}
        mape, smape = bt.get("mape_pct"), bt.get("smape_pct")

    status = get_ollama_client().status()
    theme.status_pills(
        [
            (
                "ok" if status.available else "warn",
                f"LLM · {status.model}" if status.available else "LLM offline · engine-only insights",
            ),
            ("info", f"Forecast · {model_label}" if model_label else "Ready"),
        ]
    )

    # recompute anomalies with UI params for count + section
    anom_count = len(engine.get_anomalies(contamination=contamination, min_volume=min_volume, force=True))

    render_kpi_row(df_enrol, df_bio, df_demo, anom_count, growth, mape=mape, smape=smape)

    mix_col, ai_col = st.columns([1.15, 1])
    with mix_col:
        age_tab, work_tab = st.tabs(["Enrolment age mix", "Workload mix"])
        with age_tab:
            render_age_mix(df_enrol)
        with work_tab:
            corr = engine.get_correlation()
            if not corr.empty:
                vals = [corr["Enrolments"].sum(), corr["Bio_Updates"].sum(), corr["Demo_Updates"].sum()]
                fig = px.pie(
                    values=vals,
                    names=["Enrolments", "Bio updates", "Demo updates"],
                    hole=0.55,
                    title="<b>Workload mix</b>",
                    color_discrete_sequence=["#10b981", "#f59e0b", "#8b5cf6"],
                )
                apply_white_theme(fig, height=300, margin=dict(l=20, r=20, t=48, b=20))
                show_plot(fig, height=300)
    with ai_col:
        has_ai = bool(st.session_state.get("dash_ai_text"))
        theme.ai_panel_header(has_content=has_ai)
        brief_key = f"{anom_count}:{int(_safe_sum(df_enrol, 'total_enrolments'))}"
        if st.session_state.get("dash_ai_key") != brief_key:
            st.session_state.pop("dash_ai_text", None)
            st.session_state.dash_ai_key = brief_key
        if st.button("Generate" if not has_ai else "Regenerate", type="primary", key="dash_ai_btn"):
            with st.spinner("Analyzing current data…"):
                st.session_state.dash_ai_text = engine.generate_dashboard_insight(anom_count, use_llm=True)
            st.rerun()
        if st.session_state.get("dash_ai_text"):
            st.markdown(st.session_state.dash_ai_text)
        else:
            st.caption("Summarize KPIs, risk cells, and forecast trajectory.")

    render_anomaly_section(engine, contamination, min_volume)

    theme.section_title(f"30-day outlook · {model_label}")
    if fc_df is not None and not fc_df.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=list(fc_df["date"]) + list(fc_df["date"][::-1]),
                y=list(fc_df["upper"]) + list(fc_df["lower"][::-1]),
                fill="toself",
                fillcolor="rgba(37, 99, 235, 0.15)",
                line=dict(color="rgba(0,0,0,0)"),
                name="P10–P90",
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=fc_df["date"],
                y=fc_df["predicted"],
                line=dict(color="#2563eb", width=2.5),
                name="Point forecast",
                mode="lines",
            )
        )
        apply_white_theme(
            fig,
            height=300,
            margin=dict(l=40, r=16, t=16, b=40),
            rangemode="tozero",
            legend=dict(orientation="h", y=1.12, x=0),
        )
        show_plot(fig, height=300)
        outlook_kpis = [
            {"label": "Peak", "value": int(fc_df["predicted"].max()), "accent": "blue", "compact": True},
            {"label": "Floor", "value": int(fc_df["predicted"].min()), "accent": "slate", "compact": True},
        ]
        if smape is not None:
            outlook_kpis.append(
                {"label": "Holdout sMAPE", "value": f"{smape}%", "accent": "amber", "compact": True, "format": False}
            )
        theme.kpi_row(outlook_kpis, compact=True)
        cmp = (engine._last_forecast_meta or {}).get("model_comparison") or []
        if cmp:
            st.caption("Bake-off: " + ", ".join(f"{r['model']}={r.get('smape_pct')}%" for r in cmp))

    render_recent_activity(logs)
