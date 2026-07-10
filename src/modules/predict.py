import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

def render_forecast_chart(historical_df, forecast_df):
    fig = go.Figure()

    recent_history = historical_df.sort_values('date').tail(60)
    
    fig.add_trace(go.Scatter(
        x=recent_history['date'],
        y=recent_history['adult_enrolments'],
        mode='lines',
        name='Historical Data',
        line=dict(color='#00f2ff', width=3)
    ))

    fig.add_trace(go.Scatter(
        x=pd.concat([forecast_df['date'], forecast_df['date'][::-1]]),
        y=pd.concat([forecast_df['upper'], forecast_df['lower'][::-1]]),
        fill='toself',
        fillcolor='rgba(0, 242, 255, 0.1)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip",
        name='Confidence Interval'
    ))

    fig.add_trace(go.Scatter(
        x=forecast_df['date'],
        y=forecast_df['predicted'],
        mode='lines',
        name='AI Projection',
        line=dict(color='#ff9f43', width=3, dash='dash')
    ))

    fig.update_layout(
        title="<b>Enrolment Volume Forecast</b>",
        xaxis_title="Timeline",
        yaxis_title="Daily Enrolments",
        template="plotly_dark",
        height=450,
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(orientation="h", y=1.1),
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)

def render_resource_planning(forecast_df):
    st.markdown("### 🛠️ Resource Planning")
    
    AVG_ENROL_PER_OP = 40
    AVG_PACKET_SIZE = 5
    
    peak_vol = forecast_df['predicted'].max()
    avg_vol = forecast_df['predicted'].mean()
    
    ops_needed = int(np.ceil(peak_vol / AVG_ENROL_PER_OP))
    storage_needed = (peak_vol * AVG_PACKET_SIZE) / 1024
    
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.metric("Operators Required", f"{ops_needed} Staff")
        
    with c2:
        st.metric("Peak Bandwidth", f"{storage_needed:.2f} GB/day")
        
    with c3:
        st.metric("Avg Daily Volume", f"{int(avg_vol):,}")
        
    if ops_needed > 100:
        st.warning(f"⚠️ **High Load Alert:** Peak volume ({int(peak_vol)}) requires significant staffing ({ops_needed} operators).")
    else:
        st.success(f"✅ **Stable Load:** Projected peak of {int(peak_vol)}/day is within current capacity.")

def render_tab(engine, df_enrol):
    st.markdown("### 🔮 Predictive Intelligence Engine")
    
    with st.expander("⚙️ Simulation Controls", expanded=True):
        c1, c2, c3 = st.columns(3)
        horizon = c1.slider("Forecast Horizon (Days)", 7, 90, 30)
        model_type = c2.selectbox("Algorithm", ["Linear (Conservative)", "Polynomial (Growth)"])
        algo = "Linear" if "Linear" in model_type else "Polynomial"
        sim_factor = c3.slider("Simulate Growth Spike (%)", -50, 50, 0)
        growth_factor = sim_factor / 100.0

    if 'date' not in df_enrol.columns:
        st.error("Date column missing. Forecasting unavailable.")
        return

    forecast_df, trend_label = engine.forecast_trends(
        horizon=horizon, 
        growth_factor=growth_factor, 
        model_type=algo
    )

    if forecast_df is None:
        st.warning("Insufficient data to generate forecast.")
        return

    col_chart, col_text = st.columns([2, 1])
    
    with col_chart:
        render_forecast_chart(df_enrol, forecast_df)
        
    with col_text:
        st.subheader("🤖 AI Insight")
        st.info(engine.generate_forecast_insight(forecast_df, algo))
        st.caption(f"**Simulation:** {sim_factor}% Growth\n\n**Algorithm:** {model_type}")

    st.markdown("---")
    render_resource_planning(forecast_df)
    
    with st.expander("📄 View Forecast Data"):
        display_df = forecast_df.copy()
        for col in ['predicted', 'upper', 'lower']:
            display_df[col] = display_df[col].astype(int)
        display_df.columns = ["Date", "Predicted (N)", "Upper Bound", "Lower Bound"]
        
        st.dataframe(display_df, use_container_width=True)
        csv = display_df.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Download CSV", csv, "forecast_data.csv", "text/csv")