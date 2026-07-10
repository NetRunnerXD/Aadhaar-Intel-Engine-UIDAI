import streamlit as st
import pandas as pd
import json
import os

import src.utils.theme as theme
from src.data_manager import DataLoader
from src.ai_core import AnalyticsEngine
from src.components import navigation
from src.modules import dashboard, analytics, predict, command, data_admin

# Configuration
DATA_PATH = "data/"
GEOJSON_PATH = "assets/india_states.geojson"

def load_geojson():
    if os.path.exists(GEOJSON_PATH):
        with open(GEOJSON_PATH, 'r') as f: 
            return json.load(f)
    return None

def main():
    theme.setup_page()

    @st.cache_resource
    def load_raw_data():
        loader = DataLoader(DATA_PATH)
        return loader.get_data()

    # Data Ingestion
    raw_enrol, raw_demo, raw_bio, logs = load_raw_data()

    # Governance Middleware
    # Syncs admin-level data corrections across the session
    if 'df_enrol_clean' not in st.session_state or st.session_state.get('data_dirty', False):
        st.session_state.df_enrol_clean = data_admin.apply_governance_changes(raw_enrol.copy())
        st.session_state.df_demo_clean = data_admin.apply_governance_changes(raw_demo.copy())
        st.session_state.df_bio_clean = data_admin.apply_governance_changes(raw_bio.copy())
        st.session_state.data_dirty = False

    df_enrol = st.session_state.df_enrol_clean
    df_demo = st.session_state.df_demo_clean
    df_bio = st.session_state.df_bio_clean

    # Initialization
    engine = AnalyticsEngine(df_enrol, df_demo, df_bio)
    anomalies = engine.get_anomalies()
    geojson_data = load_geojson()

    # Routing
    view = navigation.render_sidebar(df_enrol)
    
    if view == "Dashboard":
        dashboard.render_dashboard(engine, df_enrol, df_bio, logs, len(anomalies))
        
    elif view == "Analytics":
        analytics.render_tab(engine)
        
    elif view == "Forecast":
        predict.render_tab(engine, df_enrol)
        
    elif view == "Geospatial Intel":
        command.render_tab(df_enrol, geojson=geojson_data)
        
    elif view == "Data Governance":
        data_admin.render_tab(df_enrol)

if __name__ == "__main__":
    main()