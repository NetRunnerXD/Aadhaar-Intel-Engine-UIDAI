import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# 1. HELPER: NAVIGATION CALLBACK
def go_to_governance():
    """
    Callback to programmatically switch the sidebar navigation
    to the 'Data Governance' tab.
    """
    st.session_state.current_page = "Data Governance"

# 2. COMPONENT: KPI ROW
def render_kpi_row(df_enrol, df_bio, anomaly_count, forecast_growth):
    """
    Top-level executive metrics.
    """
    total_enrol = df_enrol['adult_enrolments'].sum()
    total_bio = df_bio['bio_stress'].sum() # Calculate total biometric updates
    
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.metric(
            "Total Enrolments", 
            f"{total_enrol:,.0f}", 
            delta="Live", 
            help="Cumulative enrolment volume"
        )
        
    with c2:
        st.metric(
            "Biometric Updates", 
            f"{total_bio:,.0f}", 
            delta="Active",
            help="Total biometric updates processed"
        )
        
    with c3:
        # Dynamic color logic for anomalies
        color = "normal" if anomaly_count == 0 else "inverse"
        label = "✅ Healthy" if anomaly_count == 0 else f"🚨 {anomaly_count} Issues"
        st.metric(
            "Risk Monitor", 
            label, 
            delta="Review" if anomaly_count > 0 else None,
            delta_color=color,
            help="Anomalies detected by AI"
        )
        
    with c4:
        st.metric(
            "Growth Projection", 
            f"{forecast_growth:.1f}%", 
            delta="30-Day",
            help="AI projected volume trend"
        )

# 3. COMPONENT: ANOMALY SECTION
def render_anomaly_section(engine, anomaly_count):
    st.markdown("---")
    st.subheader("🛡️ Governance & Anomaly Resolution")
    
    if anomaly_count == 0:
        st.success("✅ **Zero Anomalies Detected:** All districts are operating within statistical norms.")
        return

    anom_df = engine.get_anomalies()
    c1, c2 = st.columns([3, 1])
    
    with c1:
        st.warning(f"⚠️ **Attention Required:** {anomaly_count} districts showing irregular patterns.")
        if not anom_df.empty:
            fig = px.bar(
                anom_df.head(5), x="risk_score", y="district", orientation='h',
                title="<b>Top 5 Risk Districts</b>", color="risk_score",
                color_continuous_scale="Reds", text="adult_enrolments"
            )
            fig.update_layout(height=250, margin=dict(l=0, r=0, t=40, b=0), xaxis_title="Risk Score")
            st.plotly_chart(fig, use_container_width=True)
        
    with c2:
        st.info("💡 **AI Insight**")
        if not anom_df.empty:
            st.markdown(f"Flagged **{anom_df.iloc[0]['district']}** as highest risk due to statistical variance.")
        
        st.button("⚡ Resolve in Governance", type="primary", use_container_width=True, on_click=go_to_governance)

# 4. COMPONENT: TREND SNAPSHOT
def render_trend_snapshot(engine):
    st.markdown("---")
    st.subheader("📈 30-Day Outlook")
    
    fc_df, _ = engine.forecast_trends(horizon=30, model_type="Linear")
    
    if fc_df is not None:
        c1, c2 = st.columns([3, 1])
        with c1:
            fig = go.Figure(go.Scatter(
                x=fc_df['date'], y=fc_df['predicted'], fill='tozeroy', 
                line=dict(color='#00f2ff', width=2)
            ))
            fig.update_layout(
                height=200, margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False), yaxis=dict(showgrid=False, showticklabels=False)
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with c2:
            st.metric("Expected Peak", f"{int(fc_df['predicted'].max()):,}")
            st.metric("Expected Floor", f"{int(fc_df['predicted'].min()):,}")

# 5. COMPONENT: ACTIVITY LOGS
def render_recent_activity(logs):
    st.markdown("---")
    with st.expander("📜 System Activity Logs", expanded=False):
        if logs:
            cols = ["Timestamp", "Level", "Message"] if isinstance(logs[0], (list, tuple)) else ["Log Message"]
            st.dataframe(pd.DataFrame(logs, columns=cols).tail(10), use_container_width=True, hide_index=True)
        else:
            st.info("No recent logs.")

# 6. MAIN RENDERER
def render_dashboard(engine, df_enrol, df_bio, logs, anomaly_count):
    st.markdown("## 🚀 Executive Dashboard")
    st.caption(f"Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Calculate growth metric
    fc_df, _ = engine.forecast_trends(horizon=30)
    growth = 0.0
    if fc_df is not None and not fc_df.empty:
        start, end = fc_df.iloc[0]['predicted'], fc_df.iloc[-1]['predicted']
        if start > 0: growth = ((end - start) / start) * 100
    
    # Render sections
    render_kpi_row(df_enrol, df_bio, anomaly_count, growth)
    render_anomaly_section(engine, anomaly_count)
    render_trend_snapshot(engine)
    render_recent_activity(logs)