"""Geospatial command center — pydeck maps over enrolment volume."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

from src.config import GEOJSON_PATH
from src.geo.centroids import resolve_centroid

GEOJSON_URL = "https://raw.githubusercontent.com/Subhash9325/GeoJson-Data-of-Indian-States/master/Indian_States"

# Basemap that does not require a Mapbox token
MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"

STATE_CENTROIDS = {
    "Andhra Pradesh": [15.91, 79.74],
    "Arunachal Pradesh": [28.21, 94.72],
    "Assam": [26.20, 92.93],
    "Bihar": [25.09, 85.31],
    "Chhattisgarh": [21.27, 81.86],
    "Goa": [15.29, 74.12],
    "Gujarat": [22.25, 71.19],
    "Haryana": [29.05, 76.08],
    "Himachal Pradesh": [31.10, 77.17],
    "Jharkhand": [23.61, 85.27],
    "Karnataka": [15.31, 75.71],
    "Kerala": [10.85, 76.27],
    "Madhya Pradesh": [22.97, 78.65],
    "Maharashtra": [19.75, 75.71],
    "Manipur": [24.66, 93.90],
    "Meghalaya": [25.46, 91.36],
    "Mizoram": [23.16, 92.93],
    "Nagaland": [26.15, 94.56],
    "Odisha": [20.95, 85.09],
    "Punjab": [31.14, 75.34],
    "Rajasthan": [27.02, 74.21],
    "Sikkim": [27.53, 88.51],
    "Tamil Nadu": [11.12, 78.65],
    "Telangana": [18.11, 79.01],
    "Tripura": [23.94, 91.98],
    "Uttar Pradesh": [26.84, 80.94],
    "Uttarakhand": [30.06, 79.01],
    "West Bengal": [22.98, 87.85],
    "Delhi": [28.70, 77.10],
    "Chandigarh": [30.73, 76.77],
    "Ladakh": [34.15, 77.57],
    "Jammu & Kashmir": [33.77, 76.57],
    "Puducherry": [11.94, 79.80],
    "Lakshadweep": [10.57, 72.64],
    "Andaman & Nicobar Islands": [11.74, 92.65],
    "Dadra & Nagar Haveli": [20.18, 73.02],
    "Dadra & Nagar Haveli And Daman & Diu": [20.18, 73.02],
    "Daman & Diu": [20.42, 72.83],
}


@st.cache_data(show_spinner=False)
def fetch_geojson():
    # Prefer local asset
    try:
        if GEOJSON_PATH.exists():
            import json

            with open(GEOJSON_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    try:
        r = requests.get(GEOJSON_URL, timeout=20)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def get_color_scale(val, min_v, max_v):
    span = float(max_v - min_v) + 1.0
    ratio = (float(val) - float(min_v)) / span
    if ratio < 0.1:
        return [0, 255, 255, 140]
    if ratio < 0.3:
        return [255, 191, 0, 160]
    return [255, 0, 50, 200]


def _vol_col(df: pd.DataFrame):
    if "total_enrolments" in df.columns:
        return "total_enrolments"
    if "adult_enrolments" in df.columns:
        return "adult_enrolments"
    return None


def _centroid(state) -> list:
    s = str(state)
    if s in STATE_CENTROIDS:
        return STATE_CENTROIDS[s]
    alt = s.replace(" And ", " & ")
    if alt in STATE_CENTROIDS:
        return STATE_CENTROIDS[alt]
    alt2 = s.replace(" & ", " And ")
    if alt2 in STATE_CENTROIDS:
        return STATE_CENTROIDS[alt2]
    return [22.0, 79.0]


def _prepare_map_frame(df: pd.DataFrame, vol: str, view_depth: str) -> pd.DataFrame:
    """
    Aggregate to district grain and attach map geometry.
    Converts categoricals to plain types so lat/lon math never hits category dtypes.
    """
    work = df.copy()
    # Critical: category + float arithmetic raises TypeError in pandas 2.x
    for col in ("state", "district"):
        if col in work.columns:
            work[col] = work[col].astype(str)

    full_agg = (
        work.groupby(["state", "district"], as_index=False, observed=True)[vol]
        .sum()
        .rename(columns={vol: "adult_enrolments"})
    )
    # Ensure numeric volume
    full_agg["adult_enrolments"] = pd.to_numeric(full_agg["adult_enrolments"], errors="coerce").fillna(0)

    if view_depth == "Top 5 Priority":
        agg_df = (
            full_agg.sort_values(["state", "adult_enrolments"], ascending=[True, False])
            .groupby("state", as_index=False, sort=False)
            .head(5)
            .reset_index(drop=True)
        )
    else:
        agg_df = full_agg.reset_index(drop=True)

    agg_df = agg_df.copy()

    def _resolve_row(row):
        lat, lon, source = resolve_centroid(row["state"], row["district"])
        return pd.Series({"lat": lat, "lon": lon, "centroid_source": source})

    geo = agg_df.apply(_resolve_row, axis=1)
    agg_df["lat"] = geo["lat"].astype("float64")
    agg_df["lon"] = geo["lon"].astype("float64")
    agg_df["centroid_source"] = geo["centroid_source"].astype(str)

    # Jitter only when we lack a district centroid (state/default)
    def _jitter(name: str, axis: int) -> float:
        seed = abs(hash((str(name), axis))) % 10_000
        return (seed / 10_000.0) * 0.3 - 0.15

    need_jitter = agg_df["centroid_source"].isin(["state", "default"])
    if need_jitter.any():
        jlat = agg_df.loc[need_jitter, "district"].map(lambda d: _jitter(d, 0))
        jlon = agg_df.loc[need_jitter, "district"].map(lambda d: _jitter(d, 1))
        agg_df.loc[need_jitter, "lat"] = agg_df.loc[need_jitter, "lat"] + jlat
        agg_df.loc[need_jitter, "lon"] = agg_df.loc[need_jitter, "lon"] + jlon

    agg_df["lat"] = agg_df["lat"].astype("float64")
    agg_df["lon"] = agg_df["lon"].astype("float64")
    return agg_df


def _apply_scale(agg_df: pd.DataFrame, scale_mode: str) -> pd.DataFrame:
    out = agg_df.copy()
    min_v = float(out["adult_enrolments"].min())
    max_v = float(out["adult_enrolments"].max())

    out["color"] = out["adult_enrolments"].map(lambda x: get_color_scale(x, min_v, max_v))

    if scale_mode == "Linear (True Scale)":
        out["norm"] = (out["adult_enrolments"] - min_v) / (max_v - min_v + 1.0)
        out["elevation"] = out["adult_enrolments"].astype("float64") * 50.0
    else:
        log_v = np.log1p(out["adult_enrolments"].astype("float64"))
        ln_min, ln_max = float(log_v.min()), float(log_v.max())
        out["norm"] = (log_v - ln_min) / (ln_max - ln_min + 0.1)
        out["elevation"] = out["norm"] * 200_000.0

    out["norm"] = out["norm"].astype("float64")
    out["radius"] = (4000.0 + out["norm"] * 20_000.0).astype("float64")
    out["elevation"] = out["elevation"].astype("float64")
    return out


def render_export_hub(agg_df: pd.DataFrame, deck: pdk.Deck):
    st.markdown("---")
    st.subheader("Data Export")

    export_df = agg_df.drop(columns=["color"], errors="ignore").copy()
    # color is a list column — bad for CSV
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button("Full Data", export_df.to_csv(index=False), "map_data.csv", "text/csv")

    top_d = export_df.sort_values("adult_enrolments", ascending=False).head(20)
    c2.download_button("Top 20 Districts", top_d.to_csv(index=False), "top_districts.csv", "text/csv")

    top_s = (
        export_df.groupby("state", as_index=False, observed=True)["adult_enrolments"]
        .sum()
        .nlargest(10, "adult_enrolments")
    )
    c3.download_button("Top 10 States", top_s.to_csv(index=False), "top_states.csv", "text/csv")

    try:
        c4.download_button("Map HTML", deck.to_html(as_string=True), "map.html", "text/html")
    except Exception:
        c4.button("HTML N/A", disabled=True)


def render_tab(df_enrol, geojson=None):
    st.markdown("### Geospatial Command Center")
    st.caption(
        "Research map: prefers district centroids when available; otherwise state centroid + jitter. "
        "Centroid source is approximate (not a full LGD extract)."
    )

    if df_enrol is None or df_enrol.empty:
        st.warning("No data found for selected filters.")
        return

    active_states = st.session_state.get("active_filters", {}).get("state", []) or []
    df = df_enrol.copy()
    # Compare as strings so categorical filters never fail
    if active_states and "state" in df.columns:
        df = df[df["state"].astype(str).isin([str(s) for s in active_states])]

    if df.empty:
        st.warning("No data found for selected filters.")
        return

    vol = _vol_col(df)
    if vol is None:
        st.error("No enrolment volume column available.")
        return

    m1, m2, m3 = st.columns(3)
    vol_by_district = df.assign(_state=df["state"].astype(str), _district=df["district"].astype(str)).groupby(
        "_district", observed=True
    )[vol].sum()
    m1.metric("Visible Volume", f"{float(df[vol].sum()):,.0f}")
    m2.metric("Hotspot", str(vol_by_district.idxmax()) if not vol_by_district.empty else "—")
    m3.metric("Districts", int(df["district"].nunique()))

    c1, c2, c3 = st.columns(3)
    viz_mode = c1.selectbox("Mode", ["Intensity (2D)", "Density (Heatmap)", "Volumetric (3D)"])
    view_depth = c2.selectbox("Depth", ["Top 5 Priority", "Show All Districts"])
    scale_mode = c3.selectbox("Scaling", ["Logarithmic (Balanced)", "Linear (True Scale)"])

    st.markdown("---")

    try:
        agg_df = _prepare_map_frame(df, vol, view_depth)
        if agg_df.empty:
            st.warning("Nothing to map after aggregation.")
            return
        agg_df = _apply_scale(agg_df, scale_mode)
    except Exception as e:
        st.error(f"Failed to prepare map data: {e}")
        st.exception(e)
        return

    if not geojson:
        geojson = fetch_geojson()

    layers = []
    if geojson:
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                geojson,
                opacity=0.3,
                stroked=True,
                filled=False,
                get_line_color=[255, 255, 255],
                get_line_width=2000,
            )
        )

    # Legend for centroid quality
    if "centroid_source" in agg_df.columns:
        src_counts = agg_df["centroid_source"].value_counts().to_dict()
        st.caption(f"Centroid sources: {src_counts}")

    pitch = 0
    tooltip = {
        "html": "<b>{district}</b> ({state})<br/>Volume: {adult_enrolments}<br/>Centroid: {centroid_source}",
        "style": {"color": "white"},
    }

    # pydeck is happier with plain Python lists for get_fill_color
    map_data = agg_df.copy()
    map_data["color"] = map_data["color"].tolist()

    if "3D" in viz_mode:
        pitch = 60
        layers.append(
            pdk.Layer(
                "ColumnLayer",
                data=map_data,
                get_position="[lon, lat]",
                get_elevation="elevation",
                elevation_scale=1,
                radius=5000,
                get_fill_color="color",
                pickable=True,
                extruded=True,
                auto_highlight=True,
            )
        )
    elif "Heatmap" in viz_mode:
        layers.append(
            pdk.Layer(
                "HeatmapLayer",
                data=map_data,
                get_position="[lon, lat]",
                get_weight="adult_enrolments",
                radius_pixels=60,
            )
        )
    else:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=map_data,
                get_position="[lon, lat]",
                get_fill_color="color",
                get_radius="radius",
                pickable=True,
                opacity=0.8,
            )
        )

    if active_states:
        lat0, lon0 = _centroid(active_states[0])
        zoom = 6
    else:
        lat0, lon0, zoom = 22.0, 79.0, 4

    view_state = pdk.ViewState(latitude=float(lat0), longitude=float(lon0), zoom=zoom, pitch=pitch)

    try:
        deck = pdk.Deck(
            map_style=MAP_STYLE,
            initial_view_state=view_state,
            layers=layers,
            tooltip=tooltip,
        )
        st.pydeck_chart(deck, use_container_width=True)
        render_export_hub(agg_df, deck)
    except Exception as e:
        st.error(f"Map render failed: {e}")
        st.exception(e)
        st.dataframe(
            agg_df[["state", "district", "adult_enrolments", "lat", "lon"]].head(50),
            use_container_width=True,
        )
