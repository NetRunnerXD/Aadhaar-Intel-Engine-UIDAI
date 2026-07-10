import streamlit as st

def render_sidebar(df):
    with st.sidebar:
        st.title("Aadhaar Intel")
        st.markdown("---")
        
        # Persistence for cross-module navigation
        if "current_page" not in st.session_state:
            st.session_state.current_page = "Dashboard"

        # Module Routing
        view = st.radio(
            "Select Module",
            ["Dashboard", "Analytics", "Forecast", "Geospatial Intel", "Data Governance"],
            key="current_page",
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        st.subheader("Global Filters")
        
        # Regional Filtering Logic
        state_options = []
        if not df.empty and 'state' in df.columns:
            state_options = sorted(df['state'].unique().astype(str))
            
        selected_states = st.multiselect(
            "Filter by State", 
            options=state_options, 
            placeholder="Select State / UT..."
        )
        
        # State Sync
        if 'active_filters' not in st.session_state:
            st.session_state.active_filters = {}
            
        st.session_state.active_filters['state'] = selected_states
        
        st.markdown("---")
        
        # System Maintenance
        if st.button("Reset Session", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
    return view