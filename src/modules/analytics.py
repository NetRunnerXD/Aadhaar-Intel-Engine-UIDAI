import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.utils import theme
from src.utils.plots import apply_white_theme, show_plot


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

    theme.kpi_row(
        [
            {
                "label": "Total enrolments",
                "value": total,
                "delta": f"18+: {theme.fmt_num(adult)}",
                "accent": "blue",
                "icon": "users",
            },
            {"label": "Active states", "value": states, "accent": "green", "format": False},
            {"label": "Active districts", "value": districts, "accent": "violet", "format": False},
            {"label": "Rows in view", "value": len(df), "accent": "slate"},
        ]
    )


def render_growth_analysis(df):
    theme.section_title("Growth trajectory")
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
        apply_white_theme(
            fig_trend,
            height=320,
            margin=dict(l=40, r=16, t=48, b=40),
            rangemode="tozero",
            xaxis_title="Date",
            yaxis_title="Daily volume",
        )
        show_plot(fig_trend, height=320)

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
    apply_white_theme(
        fig_bar,
        height=420,
        margin=dict(l=8, r=24, t=16, b=40),
        rangemode="tozero",
        xaxis_title="Volume",
        yaxis_title=None,
        yaxis={"categoryorder": "total ascending"},
        coloraxis_showscale=False,
    )
    show_plot(fig_bar, height=420)


def render_operational_analysis(engine, df):
    theme.section_title("Operational efficiency")
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
        apply_white_theme(fig_donut, height=300, margin=dict(l=20, r=20, t=48, b=20), showlegend=True)
        show_plot(fig_donut, height=300)
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


def _state_risk_summary(anom: pd.DataFrame) -> pd.DataFrame:
    """Aggregate district-level anomaly flags to state-level risk metrics."""
    if anom is None or anom.empty or "state" not in anom.columns:
        return pd.DataFrame()

    vol_col = next(
        (c for c in ("volume", "total_enrolments", "adult_enrolments") if c in anom.columns),
        None,
    )
    work = anom.copy()
    work["state"] = work["state"].astype(str)
    work["risk_score"] = pd.to_numeric(work["risk_score"], errors="coerce").fillna(0)

    agg = {
        "max_risk": ("risk_score", "max"),
        "mean_risk": ("risk_score", "mean"),
        "flags": ("risk_score", "count"),
    }
    if vol_col:
        work[vol_col] = pd.to_numeric(work[vol_col], errors="coerce").fillna(0)
        agg["flagged_volume"] = (vol_col, "sum")

    summary = work.groupby("state", observed=True).agg(**agg).reset_index()
    summary["mean_risk"] = summary["mean_risk"].round(1)
    summary["max_risk"] = summary["max_risk"].astype(int)
    summary = summary.sort_values(["max_risk", "mean_risk", "flags"], ascending=False)
    return summary


def _fmt_compact_volume(val) -> str:
    """Short volume label for radar axis ticks (e.g. 12.4k, 1.2M)."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "—"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}k"
    return f"{int(v)}"


def render_state_risk_radar(top_states: pd.DataFrame):
    """Polar risk radar: top states by volume, with volume printed next to each name."""
    st.markdown("#### Risk radar — top 10 states by volume")
    st.caption(
        "State-level Isolation Forest flags ranked by flagged volume. "
        "Radial value = risk score; axis labels show state name and volume. "
        "Not a fraud verdict — multi-feature outlier ranking."
    )
    if top_states is None or top_states.empty:
        st.info("No state risk aggregation available.")
        return

    top = top_states.copy()
    # Rank and order by flagged volume so labels read high-volume first around the chart
    if "flagged_volume" in top.columns:
        top = top.sort_values("flagged_volume", ascending=False).head(10).reset_index(drop=True)
        volumes = pd.to_numeric(top["flagged_volume"], errors="coerce").fillna(0)
    else:
        top = top.head(10).reset_index(drop=True)
        volumes = pd.Series([0.0] * len(top))

    # Axis labels: state name + volume metric next to it
    labels = [
        f"{row.state}<br>vol {_fmt_compact_volume(vol)}"
        for row, vol in zip(top.itertuples(index=False), volumes)
    ]
    hover_names = top["state"].astype(str).tolist()
    vol_raw = volumes.astype(int).tolist()
    flags = top["flags"].astype(int).tolist() if "flags" in top.columns else [0] * len(top)
    mean_risks = top["mean_risk"].tolist() if "mean_risk" in top.columns else [0.0] * len(top)

    r_vals = top["max_risk"].astype(float).tolist()
    r_closed = r_vals + [r_vals[0]]
    theta_closed = labels + [labels[0]]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=r_closed,
            theta=theta_closed,
            fill="toself",
            name="Max risk",
            mode="lines+markers",
            line=dict(color="#dc2626", width=2),
            marker=dict(size=9, color="#dc2626"),
            fillcolor="rgba(220, 38, 38, 0.22)",
            customdata=list(
                zip(
                    hover_names + [hover_names[0]],
                    vol_raw + [vol_raw[0]],
                    flags + [flags[0]],
                    mean_risks + [mean_risks[0]],
                )
            ),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Max risk: %{r:.0f}<br>"
                "Mean risk: %{customdata[3]:.1f}<br>"
                "Flags: %{customdata[2]}<br>"
                "Volume: %{customdata[1]:,}<extra></extra>"
            ),
        )
    )
    if "mean_risk" in top.columns:
        mean_closed = [float(x) for x in mean_risks] + [float(mean_risks[0])]
        fig.add_trace(
            go.Scatterpolar(
                r=mean_closed,
                theta=theta_closed,
                fill="toself",
                name="Mean risk",
                mode="lines",
                line=dict(color="#f59e0b", width=1.5, dash="dot"),
                fillcolor="rgba(245, 158, 11, 0.12)",
                hovertemplate="<b>%{theta}</b><br>Mean risk: %{r:.1f}<extra></extra>",
            )
        )

    max_axis = max(100, int(top["max_risk"].max()) + 8) if len(top) else 100
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#151b2b",
        plot_bgcolor="#151b2b",
        font=dict(color="#cbd5e1", family="Segoe UI, system-ui, sans-serif", size=12),
        title=dict(
            text="<b>Top 10 states by flagged volume — risk score radar</b>",
            font=dict(color="#e2e8f0", size=14),
        ),
        height=520,
        margin=dict(l=80, r=80, t=64, b=64),
        showlegend=True,
        legend=dict(bgcolor="rgba(21,27,43,0.92)", font=dict(color="#cbd5e1", size=11), orientation="h", y=1.08),
        polar=dict(
            bgcolor="#151b2b",
            radialaxis=dict(
                visible=True,
                range=[0, max_axis],
                title=dict(text="Risk score", font=dict(size=11, color="#94a3b8")),
                showline=True,
                linecolor="#64748b",
                gridcolor="#1e293b",
                tickfont=dict(color="#94a3b8", size=10),
            ),
            angularaxis=dict(
                tickfont=dict(color="#e2e8f0", size=11),
                linecolor="#64748b",
                gridcolor="#1e293b",
                rotation=90,
                direction="clockwise",
            ),
        ),
    )
    show_plot(fig, height=520, key="state_risk_radar")


def render_anomalies_inline(engine):
    theme.section_title("Risk radar")
    from src.config import ANOMALY_CONTAMINATION, ANOMALY_MIN_VOLUME

    c_a, c_b = st.columns(2)
    contamination = c_a.slider("Contamination", 0.01, 0.15, float(ANOMALY_CONTAMINATION), 0.01, key="an_c")
    min_volume = c_b.number_input("Min volume", 0, 100000, int(ANOMALY_MIN_VOLUME), 10, key="an_mv")
    anom = engine.get_anomalies(contamination=contamination, min_volume=min_volume, force=True)
    if anom.empty:
        st.success("No multi-feature anomalies detected under thresholds.")
        return

    state_summary = _state_risk_summary(anom)
    if not state_summary.empty:
        render_state_risk_radar(state_summary)
        st.markdown("---")

    st.markdown("#### District-level risk cells")
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
            title="<b>High-risk cells (state × district)</b>",
            hover_data=[c for c in ("state", "reason", "investigation_notes") if c in anom.columns],
        )
        apply_white_theme(
            fig,
            height=360,
            margin=dict(l=40, r=20, t=48, b=40),
            rangemode="tozero",
            xaxis={"visible": False, "showticklabels": False},
            yaxis_title="Volume",
        )
        show_plot(fig, height=360)
        inv_cols = [c for c in ("state", "district", "risk_score", "reason", "investigation_notes") if c in anom.columns]
        with st.expander("Investigation notes"):
            st.dataframe(anom[inv_cols].head(20), hide_index=True, use_container_width=True)
    with c2:
        st.warning(f"**{len(anom)} flags**")
        cols = [c for c in ("state", "district", "risk_score", "reason") if c in anom.columns]
        st.dataframe(anom[cols].head(10), hide_index=True, use_container_width=True)


def render_export_section(engine, df_view):
    theme.section_title("Export intelligence pack")
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
    theme.page_header("Analytics")
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
