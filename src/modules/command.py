import streamlit as st
import pydeck as pdk
import pandas as pd
import numpy as np
import requests

GEOJSON_URL = "https://raw.githubusercontent.com/Subhash9325/GeoJson-Data-of-Indian-States/master/Indian_States"

STATE_CENTROIDS = {
    "Andhra Pradesh": [15.91, 79.74], "Arunachal Pradesh": [28.21, 94.72], "Assam": [26.20, 92.93],
    "Bihar": [25.09, 85.31], "Chhattisgarh": [21.27, 81.86], "Goa": [15.29, 74.12],
    "Gujarat": [22.25, 71.19], "Haryana": [29.05, 76.08], "Himachal Pradesh": [31.10, 77.17],
    "Jharkhand": [23.61, 85.27], "Karnataka": [15.31, 75.71], "Kerala": [10.85, 76.27],
    "Madhya Pradesh": [22.97, 78.65], "Maharashtra": [19.75, 75.71], "Manipur": [24.66, 93.90],
    "Meghalaya": [25.46, 91.36], "Mizoram": [23.16, 92.93], "Nagaland": [26.15, 94.56],
    "Odisha": [20.95, 85.09], "Punjab": [31.14, 75.34], "Rajasthan": [27.02, 74.21],
    "Sikkim": [27.53, 88.51], "Tamil Nadu": [11.12, 78.65], "Telangana": [18.11, 79.01],
    "Tripura": [23.94, 91.98], "Uttar Pradesh": [26.84, 80.94], "Uttarakhand": [30.06, 79.01],
    "West Bengal": [22.98, 87.85], "Delhi": [28.70, 77.10], "Chandigarh": [30.73, 76.77],
    "Ladakh": [34.15, 77.57], "Jammu & Kashmir": [33.77, 76.57], "Puducherry": [11.94, 79.80]
}

@st.cache_data
def fetch_geojson():
    try:
        r = requests.get(GEOJSON_URL)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def get_color_scale(val, min_v, max_v):
    ratio = (val - min_v) / (max_v - min_v + 1)
    if ratio < 0.1: return [0, 255, 255, 140]
    if ratio < 0.3: return [255, 191, 0, 160]
    return [255, 0, 50, 200]

def render_export_hub(agg_df, deck):
    st.markdown("---")
    st.subheader("📥 Data Export")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button("📄 Full Data", agg_df.to_csv(index=False), "map_data.csv", "text/csv")
    
    top_d = agg_df.sort_values('adult_enrolments', ascending=False).head(20)
    c2.download_button("🏆 Top 20 Districts", top_d.to_csv(index=False), "top_districts.csv", "text/csv")
    
    top_s = agg_df.groupby('state')['adult_enrolments'].sum().nlargest(10).reset_index()
    c3.download_button("📍 Top 10 States", top_s.to_csv(index=False), "top_states.csv", "text/csv")
    
    try:
        c4.download_button("🗺️ Map HTML", deck.to_html(as_string=True), "map.html", "text/html")
    except:
        c4.button("HTML N/A", disabled=True)

def render_tab(df_enrol, geojson=None):
    st.markdown("### 🛰️ Geospatial Command Center")
    
    active_states = st.session_state.get('active_filters', {}).get('state', [])
    df = df_enrol[df_enrol['state'].isin(active_states)].copy() if active_states else df_enrol.copy()
    
    if df.empty:
        st.warning("No data found for selected filters.")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Visible Volume", f"{df['adult_enrolments'].sum():,.0f}")
    m2.metric("Hotspot", df.groupby('district')['adult_enrolments'].sum().idxmax())
    m3.metric("Districts", df['district'].nunique())

    c1, c2, c3 = st.columns(3)
    viz_mode = c1.selectbox("Mode", ["Intensity (2D)", "Density (Heatmap)", "Volumetric (3D)"])
    view_depth = c2.selectbox("Depth", ["Top 5 Priority", "Show All Districts"])
    scale_mode = c3.selectbox("Scaling", ["Logarithmic (Balanced)", "Linear (True Scale)"])

    st.markdown("---")

    full_agg = df.groupby(['state', 'district'])['adult_enrolments'].sum().reset_index()
    if view_depth == "Top 5 Priority":
        agg_df = full_agg.sort_values(['state', 'adult_enrolments'], ascending=[True, False]).groupby('state').head(5)
    else:
        agg_df = full_agg

    agg_df['lat'] = agg_df['state'].apply(lambda x: STATE_CENTROIDS.get(x, [20, 78])[0])
    agg_df['lon'] = agg_df['state'].apply(lambda x: STATE_CENTROIDS.get(x, [20, 78])[1])
    
    # Add Jitter
    agg_df['lat'] += agg_df['district'].apply(lambda x: (hash(x) % 1000) / 3000.0 - 0.15)
    agg_df['lon'] += agg_df['district'].apply(lambda x: (hash(x[::-1]) % 1000) / 3000.0 - 0.15)
    
    min_v, max_v = agg_df['adult_enrolments'].min(), agg_df['adult_enrolments'].max()
    agg_df['color'] = agg_df['adult_enrolments'].apply(lambda x: get_color_scale(x, min_v, max_v))

    if scale_mode == "Linear (True Scale)":
        agg_df['norm'] = (agg_df['adult_enrolments'] - min_v) / (max_v - min_v + 1)
        agg_df['elevation'] = agg_df['adult_enrolments'] * 50.0 
    else:
        agg_df['log_v'] = np.log1p(agg_df['adult_enrolments'])
        ln_min, ln_max = agg_df['log_v'].min(), agg_df['log_v'].max()
        agg_df['norm'] = (agg_df['log_v'] - ln_min) / (ln_max - ln_min + 0.1)
        agg_df['elevation'] = agg_df['norm'] * 200000

    agg_df['radius'] = 4000 + (agg_df['norm'] * 20000)

    if not geojson: geojson = fetch_geojson()
    layers = []

    if geojson:
        layers.append(pdk.Layer("GeoJsonLayer", geojson, opacity=0.3, stroked=True, filled=False, get_line_color=[255, 255, 255], get_line_width=2000))

    pitch, tooltip = 0, {"html": "<b>{district}</b><br/>Volume: {adult_enrolments}"}

    if "3D" in viz_mode:
        pitch = 60
        layers.append(pdk.Layer("ColumnLayer", agg_df, get_position=["lon", "lat"], get_elevation="elevation", radius=5000, get_fill_color="color", pickable=True, extruded=True))
    elif "Heatmap" in viz_mode:
        layers.append(pdk.Layer("HeatmapLayer", agg_df, get_position=["lon", "lat"], get_weight="adult_enrolments", radius_pixels=60))
    else:
        layers.append(pdk.Layer("ScatterplotLayer", agg_df, get_position=["lon", "lat"], get_fill_color="color", get_radius="radius", pickable=True))

    view_state = pdk.ViewState(
        latitude=STATE_CENTROIDS.get(active_states[0], [22, 79])[0] if active_states else 22,
        longitude=STATE_CENTROIDS.get(active_states[0], [22, 79])[1] if active_states else 79,
        zoom=6 if active_states else 4,
        pitch=pitch
    )

    deck = pdk.Deck(map_style="mapbox://styles/mapbox/dark-v10", initial_view_state=view_state, layers=layers, tooltip=tooltip)
    st.pydeck_chart(deck)
    render_export_hub(agg_df, deck)