import streamlit as st
import pandas as pd


def render_sidebar(df):
    with st.sidebar:
        st.title("Aadhaar Intel")
        st.markdown("---")

        if "current_page" not in st.session_state:
            st.session_state.current_page = "Dashboard"

        view = st.radio(
            "Select Module",
            ["Dashboard", "Analytics", "Forecast", "Geospatial Intel", "Data Governance"],
            key="current_page",
            label_visibility="collapsed",
        )

        st.markdown("---")
        st.subheader("Global Filters")

        state_options = []
        if df is not None and not df.empty and "state" in df.columns:
            state_options = sorted(df["state"].astype(str).unique())

        selected_states = st.multiselect(
            "Filter by State",
            options=state_options,
            placeholder="Select State / UT...",
        )

        date_range = None
        if df is not None and not df.empty and "date" in df.columns:
            dates = pd.to_datetime(df["date"], errors="coerce").dropna()
            if not dates.empty:
                min_d, max_d = dates.min().date(), dates.max().date()
                picked = st.date_input(
                    "Date range",
                    value=(min_d, max_d),
                    min_value=min_d,
                    max_value=max_d,
                )
                if isinstance(picked, (list, tuple)) and len(picked) == 2:
                    date_range = (picked[0], picked[1])
                elif picked:
                    date_range = (picked, picked)

        if "active_filters" not in st.session_state:
            st.session_state.active_filters = {}

        st.session_state.active_filters["state"] = selected_states
        st.session_state.active_filters["date_range"] = date_range

        st.markdown("---")

        if st.button("Reset Session", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            try:
                st.cache_data.clear()
            except Exception:
                pass
            try:
                st.cache_resource.clear()
            except Exception:
                pass
            st.rerun()

    return view
