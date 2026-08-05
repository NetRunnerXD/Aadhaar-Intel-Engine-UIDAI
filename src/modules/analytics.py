import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


def _vol_col(df):
    if df is not None and not df.empty:
        if "total_enrolments" in df.columns:
            return "total_enrolments"
        if "adult_enrolments" in df.columns:
            return "adult_enrolments"
    return "total_enrolments"


def render_kpi_row(df):
    if df is None or df.empty:
        st.warning("No rows for current filters.")
        return
    col = _vol_col(df)
    total = df[col].sum()
    states = df["state"].nunique() if "state" in df.columns else 0
    districts = df["district"].nunique() if "district" in df.columns else 0
    adult = df["adult_enrolments"].sum() if "adult_enrolments" in df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Enrolments", f"{total:,.0f}", delta=f"18+: {adult:,.0f}")
    with c2:
        st.metric("Active States", states)
    with c3:
        st.metric("Active Districts", districts)
    with c4:
        st.metric("Rows in View", f"{len(df):,}")
    st.markdown("---")


def render_growth_analysis(df):
    st.subheader("Growth Trajectory")
    col = _vol_col(df)
    if "date" in df.columns:
        trend = df.groupby("date", observed=True)[col].sum().reset_index()
        fig_trend = px.area(
            trend,
            x="date",
            y=col,
            title="<b>National Daily Enrolment Volume</b>",
            color_discrete_sequence=["#3b82f6"],
        )
        fig_trend.update_layout(height=300, margin=dict(l=0, r=0, t=40, b=0), xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig_trend, use_container_width=True)

    st.markdown("#### Top Regional Drivers")
    if "state" not in df.columns:
        return
    top_states = df.groupby("state", observed=True)[col].sum().nlargest(10).reset_index()
    fig_bar = px.bar(
        top_states,
        x=col,
        y="state",
        orientation="h",
        text_auto=".2s",
        color=col,
        color_continuous_scale="Blues",
    )
    fig_bar.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis_title="Volume",
        yaxis_title=None,
        yaxis={"categoryorder": "total ascending"},
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True)


def render_operational_analysis(engine, df):
    st.subheader("Operational efficiency")
    corr = engine.get_correlation()
    if not corr.empty:
        new, updates, demo = (
            corr["Enrolments"].sum(),
            corr["Bio_Updates"].sum(),
            corr["Demo_Updates"].sum(),
        )
        fig_donut = px.pie(
            values=[new, updates, demo],
            names=["New Enrolments", "Bio Updates", "Demo Updates"],
            hole=0.6,
            color_discrete_sequence=["#10b981", "#f59e0b", "#8b5cf6"],
            title="<b>Workload Split</b>",
        )
        fig_donut.update_layout(height=280, margin=dict(l=0, r=0, t=40, b=0), showlegend=True)
        st.plotly_chart(fig_donut, use_container_width=True)
        st.caption(
            f"Ratio: **{updates / (new + 1):.1f}×** bio and **{demo / (new + 1):.1f}×** demo updates per enrolment unit."
        )

    st.markdown("---")
    st.markdown("#### Watchlist (Low Volume)")
    col = _vol_col(df)
    if col not in df.columns or "district" not in df.columns:
        return
    bottom = (
        df[df[col] > 0]
        .groupby(["state", "district"], observed=True)[col]
        .sum()
        .nsmallest(10)
        .reset_index()
    )
    if bottom.empty:
        st.info("No low-volume districts in view.")
        return
    st.dataframe(
        bottom,
        hide_index=True,
        use_container_width=True,
        column_config={
            col: st.column_config.ProgressColumn(
                "Volume",
                format="%d",
                min_value=0,
                max_value=int(bottom[col].max() * 2) if bottom[col].max() > 0 else 1,
            )
        },
    )


def render_anomalies_inline(engine):
    st.subheader("Risk radar (state × district)")
    from src.config import ANOMALY_CONTAMINATION, ANOMALY_MIN_VOLUME

    c_a, c_b = st.columns(2)
    contamination = c_a.slider("Contamination", 0.01, 0.15, float(ANOMALY_CONTAMINATION), 0.01, key="an_c")
    min_volume = c_b.number_input("Min volume", 0, 100000, int(ANOMALY_MIN_VOLUME), 10, key="an_mv")
    anom = engine.get_anomalies(contamination=contamination, min_volume=min_volume, force=True)
    if anom.empty:
        st.success("No multi-feature anomalies detected under thresholds.")
        return
    c1, c2 = st.columns([3, 1])
    y_vol = "volume" if "volume" in anom.columns else (
        "total_enrolments" if "total_enrolments" in anom.columns else "adult_enrolments"
    )
    with c1:
        fig = px.scatter(
            anom,
            x="district",
            y=y_vol,
            color="risk_score",
            size="risk_score",
            color_continuous_scale="Reds",
            title="<b>High-risk cells</b>",
            hover_data=[c for c in ("state", "reason", "investigation_notes") if c in anom.columns],
        )
        fig.update_layout(height=320, xaxis={"visible": False})
        st.plotly_chart(fig, use_container_width=True)
        inv_cols = [c for c in ("state", "district", "risk_score", "reason", "investigation_notes") if c in anom.columns]
        with st.expander("Investigation notes"):
            st.dataframe(anom[inv_cols].head(20), hide_index=True, use_container_width=True)
    with c2:
        st.warning(f"**{len(anom)} flags**")
        cols = [c for c in ("state", "district", "risk_score", "reason") if c in anom.columns]
        st.dataframe(anom[cols].head(10), hide_index=True, use_container_width=True)


def render_export_section(engine, df_view):
    st.markdown("---")
    st.subheader("Export Intelligence Pack")
    col = _vol_col(df_view)
    reg_csv = (
        df_view.groupby(["state", "district"], observed=True)[col]
        .sum()
        .reset_index()
        .to_csv(index=False)
        .encode("utf-8")
    )
    trend_csv = None
    if "date" in df_view.columns:
        trend_csv = (
            df_view.groupby("date", observed=True)[col]
            .sum()
            .reset_index()
            .to_csv(index=False)
            .encode("utf-8")
        )
    anom_csv = engine.get_anomalies().to_csv(index=False).encode("utf-8")
    ops_csv = engine.get_correlation().to_csv(index=False).encode("utf-8")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.download_button("Regional", data=reg_csv, file_name="regional.csv", mime="text/csv")
    with c2:
        if trend_csv:
            st.download_button("Trends", data=trend_csv, file_name="trends.csv", mime="text/csv")
    with c3:
        st.download_button("Risk", data=anom_csv, file_name="risk.csv", mime="text/csv")
    with c4:
        st.download_button("Ops", data=ops_csv, file_name="ops.csv", mime="text/csv")


def render_tab(engine):
    st.markdown("### Enterprise Analytics")
    df_view = engine.df_enrol

    if df_view is None or df_view.empty:
        st.error("No data found for current global filters.")
        return

    render_kpi_row(df_view)
    l, r = st.columns([2, 1])
    with l:
        render_growth_analysis(df_view)
    with r:
        render_operational_analysis(engine, df_view)
    st.markdown("---")
    render_anomalies_inline(engine)
    render_export_section(engine, df_view)
