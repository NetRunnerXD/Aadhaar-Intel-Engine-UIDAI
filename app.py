import json
import os

import pandas as pd
import streamlit as st

import src.utils.theme as theme
from src.ai_core import AnalyticsEngine
from src.components import navigation
from src.ai.ollama_client import get_ollama_client
from src.config import DATA_DIR, GEOJSON_PATH, MARTS_ONLY, PROCESSED_DIR
from src.data_manager import DataLoader
from src.modules import analytics, command, dashboard, data_admin, predict
from src.services.filters import apply_filters


def load_geojson():
    path = str(GEOJSON_PATH)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _is_empty(*dfs) -> bool:
    return all(df is None or df.empty for df in dfs)


def main():
    theme.setup_page()

    @st.cache_resource
    def load_raw_data():
        loader = DataLoader(str(DATA_DIR), processed_path=PROCESSED_DIR, prefer_cache=True)
        enrol, demo, bio, logs = loader.get_data()
        return (
            enrol,
            demo,
            bio,
            logs,
            loader.load_report,
            loader.dim_geo,
            loader.agg_district,
            loader.source,
        )

    (
        raw_enrol,
        raw_demo,
        raw_bio,
        logs,
        load_report,
        dim_geo,
        agg_district,
        source,
    ) = load_raw_data()

    if _is_empty(raw_enrol, raw_demo, raw_bio):
        st.error("### No data loaded")
        st.markdown(
            f"Place Aadhaar CSV shards in `{DATA_DIR}` and restart. "
            "See `data/README.md` for expected schemas.\n\n"
            f"Optional: build cache with `python -m src.etl.build_cache`"
        )
        with st.expander("Load logs", expanded=True):
            for line in logs:
                st.text(line)
            st.json(load_report)
        return

    # Load durable governance patches once, then apply
    data_admin.init_session_state()

    if "df_enrol_clean" not in st.session_state or st.session_state.get("data_dirty", False):
        st.session_state.df_enrol_clean = data_admin.apply_governance_changes(raw_enrol)
        st.session_state.df_demo_clean = data_admin.apply_governance_changes(raw_demo)
        st.session_state.df_bio_clean = data_admin.apply_governance_changes(raw_bio)
        st.session_state.data_dirty = False

    df_enrol = st.session_state.df_enrol_clean
    df_demo = st.session_state.df_demo_clean
    df_bio = st.session_state.df_bio_clean

    # Keep dim_geo available for governance PIN heuristics
    if "dim_geo" not in st.session_state:
        st.session_state.dim_geo = dim_geo

    view = navigation.render_sidebar(df_enrol)

    f_enrol = apply_filters(df_enrol)
    f_demo = apply_filters(df_demo)
    f_bio = apply_filters(df_bio)

    engine = AnalyticsEngine(f_enrol, f_demo, f_bio)
    anomalies = engine.get_anomalies()
    geojson_data = load_geojson()

    # Research chrome: freshness + LLM health
    max_date = None
    if df_enrol is not None and not df_enrol.empty and "date" in df_enrol.columns:
        max_date = pd.to_datetime(df_enrol["date"], errors="coerce").max()
    ollama = get_ollama_client().status()

    with st.sidebar:
        st.markdown("### Research status")
        st.caption(f"Data as of: **{max_date.date() if max_date is not None and pd.notna(max_date) else 'n/a'}**")
        st.caption(f"Source: **{source}** · MARTS_ONLY={MARTS_ONLY}")
        if ollama.available:
            st.success(f"LLM: online · {ollama.model}")
        else:
            st.warning("LLM: offline (engine drafts)")
        with st.expander("Data quality", expanded=False):
            st.caption(f"Enrol {len(df_enrol):,} · Bio {len(df_bio):,} · Demo {len(df_demo):,}")
            if load_report.get("warnings"):
                for w in load_report["warnings"][:6]:
                    st.warning(w)
            st.json(
                {
                    "source": load_report.get("source"),
                    "cache_valid": load_report.get("cache_valid"),
                    "rows_raw": load_report.get("rows_raw"),
                    "quarantined": load_report.get("rows_quarantined"),
                    "dedup_collapsed": load_report.get("duplicate_keys_collapsed"),
                    "district_as_state_repairs": load_report.get("district_as_state_repairs", {}),
                    "geo_repair_stats": load_report.get("geo_repair_stats", {}),
                    "unknown_states": load_report.get("unknown_states", [])[:15],
                    "dim_geo_rows": len(dim_geo) if dim_geo is not None else 0,
                    "agg_district_rows": len(agg_district) if agg_district is not None else 0,
                    "llm": {"available": ollama.available, "model": ollama.model, "error": ollama.error},
                }
            )

    if view == "Dashboard":
        dashboard.render_dashboard(engine, f_enrol, f_bio, f_demo, logs, len(anomalies))
    elif view == "Analytics":
        analytics.render_tab(engine)
    elif view == "Forecast":
        predict.render_tab(engine, f_enrol)
    elif view == "Geospatial Intel":
        command.render_tab(f_enrol, geojson=geojson_data)
    elif view == "Data Governance":
        # Prefer dim_geo for PIN-aware scans when daily grain lacks pincode
        gov_df = df_enrol
        if (dim_geo is not None) and (not dim_geo.empty) and ("pincode" not in df_enrol.columns):
            # Lightweight frame for name scans: unique districts with sample pins
            gov_df = dim_geo.copy()
            if "total_enrolments" not in gov_df.columns:
                gov_df["total_enrolments"] = 1
        data_admin.render_tab(gov_df if not gov_df.empty else df_enrol)


if __name__ == "__main__":
    main()
