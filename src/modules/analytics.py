import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np

def render_kpi_row(df):
    total = df['adult_enrolments'].sum()
    states = df['state'].nunique()
    districts = df['district'].nunique()
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Total Enrolments", f"{total:,.0f}", delta="1.2% ↗")
    with c2: st.metric("Active States", states)
    with c3: st.metric("Active Districts", districts, delta="New: 3")
    with c4: st.metric("System Health", "98.5%", delta="Optimal")
    st.markdown("---")

def render_growth_analysis(df):
    st.subheader("📈 Growth Trajectory")
    if 'date' in df.columns:
        trend = df.groupby('date')['adult_enrolments'].sum().reset_index()
        fig_trend = px.area(trend, x='date', y='adult_enrolments',
            title="<b>National Daily Enrolment Volume</b>",
            color_discrete_sequence=['#3b82f6'])
        fig_trend.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0), xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig_trend, use_container_width=True)

    st.markdown("#### 📍 Top Regional Drivers")
    top_states = df.groupby('state')['adult_enrolments'].sum().nlargest(10).reset_index()
    fig_bar = px.bar(top_states, x='adult_enrolments', y='state',
        orientation='h', text_auto='.2s', color='adult_enrolments', color_continuous_scale='Blues')
    fig_bar.update_layout(height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_title="Volume", 
                          yaxis_title=None, yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False)
    st.plotly_chart(fig_bar, use_container_width=True)

def render_operational_analysis(engine, df):
    st.subheader("⚡ Operational efficiency")
    corr = engine.get_correlation()
    if not corr.empty:
        new, updates = corr['Enrolments'].sum(), corr['Bio_Updates'].sum()
        fig_donut = px.pie(values=[new, updates], names=['New Enrolments', 'Bio Updates'],
            hole=0.6, color_discrete_sequence=['#10b981', '#f59e0b'], title="<b>Workload Split</b>")
        fig_donut.update_layout(height=250, margin=dict(l=0,r=0,t=40,b=0), showlegend=True)
        st.plotly_chart(fig_donut, use_container_width=True)
        st.caption(f"ℹ️ **Insight:** Ratio: {updates / (new + 1):.1f} biometric updates per enrolment.")
    
    st.markdown("---")
    st.markdown("#### ⚠️ Watchlist (Low Volume)")
    bottom = df[df['adult_enrolments'] > 0].groupby(['state','district'])['adult_enrolments'].sum().nsmallest(10).reset_index()
    st.dataframe(bottom, hide_index=True, use_container_width=True,
        column_config={"adult_enrolments": st.column_config.ProgressColumn("Volume", format="%d", 
        min_value=0, max_value=int(bottom['adult_enrolments'].max()*2))})

def render_anomalies_inline(engine):
    st.subheader("🚨 Risk Radar")
    anom = engine.get_anomalies()
    if anom.empty:
        st.success("✅ No statistical anomalies detected.")
        return
    c1, c2 = st.columns([3, 1])
    with c1:
        fig = px.scatter(anom, x='district', y='adult_enrolments', color='risk_score', size='risk_score',
            color_continuous_scale='Reds', title="<b>High-Risk Outliers</b>", hover_data=['state'])
        fig.update_layout(height=300, xaxis={'visible': False})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.warning(f"**{len(anom)} Flags**")
        st.dataframe(anom[['district', 'risk_score']].head(5), hide_index=True, use_container_width=True)

def render_export_section(engine, df_view):
    st.markdown("---")
    st.subheader("📥 Export Intelligence Pack")
    reg_csv = df_view.groupby(['state', 'district'])['adult_enrolments'].sum().reset_index().to_csv(index=False).encode('utf-8')
    trend_csv = df_view.groupby('date')['adult_enrolments'].sum().reset_index().to_csv(index=False).encode('utf-8') if 'date' in df_view.columns else None
    anom_csv = engine.get_anomalies().to_csv(index=False).encode('utf-8')
    ops_csv = engine.get_correlation().to_csv(index=False).encode('utf-8')
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.download_button("📄 Regional", data=reg_csv, file_name="regional.csv", mime="text/csv")
    with c2: 
        if trend_csv: st.download_button("📈 Trends", data=trend_csv, file_name="trends.csv", mime="text/csv")
    with c3: st.download_button("🚨 Risk", data=anom_csv, file_name="risk.csv", mime="text/csv")
    with c4: st.download_button("⚡ Ops", data=ops_csv, file_name="ops.csv", mime="text/csv")

def render_tab(engine):
    st.markdown("### 📊 Enterprise Analytics")
    df = engine.df_enrol
    df_view = df
    if 'date' in df.columns:
        min_d, max_d = df['date'].min(), df['date'].max()
        if not (pd.isna(min_d) or pd.isna(max_d)):
            d_range = st.sidebar.date_input("Range", [min_d, max_d], min_value=min_d, max_value=max_d)
            if len(d_range) == 2:
                df_view = df.loc[(df['date'].dt.date >= d_range[0]) & (df['date'].dt.date <= d_range[1])]

    if df_view.empty:
        st.error("No data found for range.")
        return

    render_kpi_row(df_view)
    l, r = st.columns([2, 1])
    with l: render_growth_analysis(df_view)
    with r: render_operational_analysis(engine, df_view)
    st.markdown("---")
    render_anomalies_inline(engine)
    render_export_section(engine, df_view)