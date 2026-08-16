"""Sidebar: brand, module nav, global filters, load status."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.utils.theme import brand_html, status_card_html

PAGES = [
    "Dashboard",
    "Analytics",
    "Forecast",
    "Geospatial Intel",
    "Data Governance",
]


def go_to_governance():
    st.session_state.current_page = "Data Governance"


def render_sidebar(
    df,
    *,
    source=None,
    load_report=None,
    logs=None,
    ollama=None,
    max_date=None,
    dim_geo=None,
    agg_district=None,
    marts_only=False,
    enrol_n: int = 0,
    bio_n: int = 0,
    demo_n: int = 0,
):
    with st.sidebar:
        st.markdown(brand_html(), unsafe_allow_html=True)

        if "current_page" not in st.session_state:
            st.session_state.current_page = "Dashboard"

        view = st.radio(
            "Select module",
            PAGES,
            key="current_page",
            label_visibility="collapsed",
        )

        st.markdown('<p class="sidebar-kicker">Global filters</p>', unsafe_allow_html=True)

        state_options = []
        if df is not None and not df.empty and "state" in df.columns:
            state_options = sorted(df["state"].astype(str).unique())

        if "selected_states" not in st.session_state:
            st.session_state.selected_states = []

        a1, a2 = st.columns(2)
        if a1.button("All", use_container_width=True, key="states_all"):
            st.session_state.selected_states = list(state_options)
            st.rerun()
        if a2.button("Clear", use_container_width=True, key="states_clear"):
            st.session_state.selected_states = []
            st.rerun()

        selected_count = len(st.session_state.selected_states)
        selected_states = st.multiselect(
            f"States / UTs ({selected_count or 'all'})",
            options=state_options,
            key="selected_states",
            placeholder="Select State / UT…",
        )

        min_d = max_d = None
        if df is not None and not df.empty and "date" in df.columns:
            dates = pd.to_datetime(df["date"], errors="coerce").dropna()
            if not dates.empty:
                min_d, max_d = dates.min().date(), dates.max().date()

        if min_d and max_d:
            if "filter_start" not in st.session_state:
                st.session_state.filter_start = min_d
            if "filter_end" not in st.session_state:
                st.session_state.filter_end = max_d
            start = st.date_input(
                "Start date",
                min_value=min_d,
                max_value=max_d,
                key="filter_start",
            )
            end = st.date_input(
                "End date",
                min_value=min_d,
                max_value=max_d,
                key="filter_end",
            )
            date_range = (start, end)
        else:
            date_range = None

        if "active_filters" not in st.session_state:
            st.session_state.active_filters = {}
        st.session_state.active_filters["state"] = selected_states
        st.session_state.active_filters["date_range"] = date_range

        date_label = "n/a"
        if max_date is not None and pd.notna(max_date):
            date_label = str(pd.Timestamp(max_date).date())
        llm_ok = bool(ollama and ollama.available)
        llm_label = (
            f"online · {ollama.model}" if llm_ok else "offline (engine analysis)"
        )

        st.markdown(
            status_card_html(
                date_max=date_label,
                source=source or "n/a",
                marts_only=marts_only,
                enrol_n=enrol_n,
                bio_n=bio_n,
                demo_n=demo_n,
                llm_ok=llm_ok,
                llm_label=llm_label,
            ),
            unsafe_allow_html=True,
        )

        with st.expander("Data quality", expanded=False):
            st.caption(f"Enrol {enrol_n:,} · Bio {bio_n:,} · Demo {demo_n:,}")
            report = load_report or {}
            if report.get("warnings"):
                for warning in report["warnings"][:6]:
                    st.warning(warning)
            geo_eval = report.get("geo_eval") or {}
            st.json(
                {
                    "source": report.get("source"),
                    "cache_valid": report.get("cache_valid"),
                    "rows_raw": report.get("rows_raw"),
                    "quarantined": report.get("rows_quarantined"),
                    "dedup_collapsed": report.get("duplicate_keys_collapsed"),
                    "district_as_state_repairs": report.get("district_as_state_repairs", {}),
                    "geo_repair_stats": report.get("geo_repair_stats", {}),
                    "geo_rule_pack": report.get("geo_rule_pack"),
                    "geo_eval": {
                        "n": geo_eval.get("n"),
                        "state_accuracy": geo_eval.get("state_accuracy"),
                        "district_accuracy": geo_eval.get("district_accuracy"),
                        "both_accuracy": geo_eval.get("both_accuracy"),
                    },
                    "unknown_states": report.get("unknown_states", [])[:15],
                    "dim_geo_rows": len(dim_geo) if dim_geo is not None else 0,
                    "agg_district_rows": len(agg_district) if agg_district is not None else 0,
                    "llm": {
                        "available": llm_ok,
                        "model": getattr(ollama, "model", None),
                        "error": getattr(ollama, "error", None),
                    },
                    "recent_logs": (logs or [])[-12:],
                }
            )

        if st.button("Reset / reload", type="primary", use_container_width=True, key="reset_reload"):
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
