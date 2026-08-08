import { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { ColumnLayer, GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import Map from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { api, filterParams, fmt, triggerDownload } from "../api";
import KpiCard from "../components/KpiCard";

/** Carto Positron — same basemap as Streamlit command center (no Mapbox token). */
const MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

/** State centroids for view framing (mirrors Streamlit STATE_CENTROIDS). */
const STATE_CENTROIDS = {
  "Andhra Pradesh": [15.91, 79.74],
  "Arunachal Pradesh": [28.21, 94.72],
  Assam: [26.2, 92.93],
  Bihar: [25.09, 85.31],
  Chhattisgarh: [21.27, 81.86],
  Goa: [15.29, 74.12],
  Gujarat: [22.25, 71.19],
  Haryana: [29.05, 76.08],
  "Himachal Pradesh": [31.1, 77.17],
  Jharkhand: [23.61, 85.27],
  Karnataka: [15.31, 75.71],
  Kerala: [10.85, 76.27],
  "Madhya Pradesh": [22.97, 78.65],
  Maharashtra: [19.75, 75.71],
  Manipur: [24.66, 93.9],
  Meghalaya: [25.46, 91.36],
  Mizoram: [23.16, 92.93],
  Nagaland: [26.15, 94.56],
  Odisha: [20.95, 85.09],
  Punjab: [31.14, 75.34],
  Rajasthan: [27.02, 74.21],
  Sikkim: [27.53, 88.51],
  "Tamil Nadu": [11.12, 78.65],
  Telangana: [18.11, 79.01],
  Tripura: [23.94, 91.98],
  "Uttar Pradesh": [26.84, 80.94],
  Uttarakhand: [30.06, 79.01],
  "West Bengal": [22.98, 87.85],
  Delhi: [28.7, 77.1],
  Chandigarh: [30.73, 76.77],
  Ladakh: [34.15, 77.57],
  "Jammu & Kashmir": [33.77, 76.57],
  Puducherry: [11.94, 79.8],
  Lakshadweep: [10.57, 72.64],
  "Andaman & Nicobar Islands": [11.74, 92.65],
  "Dadra & Nagar Haveli": [20.18, 73.02],
  "Dadra & Nagar Haveli And Daman & Diu": [20.18, 73.02],
  "Daman & Diu": [20.42, 72.83],
};

const FALLBACK_COLORS = {
  low: [14, 165, 233, 170],
  medium: [245, 158, 11, 190],
  high: [220, 38, 38, 210],
};

const HEX_COLORS = { low: "#0ea5e9", medium: "#f59e0b", high: "#dc2626" };

function resolveStateCentroid(state) {
  const s = String(state || "");
  if (STATE_CENTROIDS[s]) return STATE_CENTROIDS[s];
  const alt = s.replace(" And ", " & ");
  if (STATE_CENTROIDS[alt]) return STATE_CENTROIDS[alt];
  const alt2 = s.replace(" & ", " And ");
  if (STATE_CENTROIDS[alt2]) return STATE_CENTROIDS[alt2];
  return [22.0, 79.0];
}

function pointColor(d) {
  if (Array.isArray(d.color) && d.color.length >= 3) return d.color;
  return FALLBACK_COLORS[d.intensity] || FALLBACK_COLORS.medium;
}

function buildView({ states, mode }) {
  const pitch = mode === "3d" ? 60 : 0;
  if (states?.length === 1) {
    const [lat, lon] = resolveStateCentroid(states[0]);
    return { longitude: lon, latitude: lat, zoom: 6, pitch, bearing: 0 };
  }
  return { longitude: 79, latitude: 22, zoom: 4, pitch, bearing: 0 };
}

export default function Geospatial({ filters }) {
  // Defaults match Streamlit: Top 5 Priority, Logarithmic (Balanced), Intensity (2D)
  const [depth, setDepth] = useState("top5");
  const [scale, setScale] = useState("log");
  const [mode, setMode] = useState("2d");
  const [data, setData] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [viewState, setViewState] = useState(() => buildView({ states: filters.states, mode: "2d" }));

  const q = () => ({ ...filterParams(filters), depth, scale, mode });

  useEffect(() => {
    api
      .geojson()
      .then(setGeojson)
      .catch(() => setGeojson(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .map(q())
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setErr("");
        setViewState({
          ...buildView({ states: filters.states, mode }),
          bearing: 0,
        });
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e.message || e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters.states?.join(","), filters.start, filters.end, depth, scale, mode]);

  const layers = useMemo(() => {
    const pts = data?.points || [];
    const list = [];

    if (geojson) {
      list.push(
        new GeoJsonLayer({
          id: "india-state-borders",
          data: geojson,
          stroked: true,
          filled: false,
          opacity: 0.45,
          getLineColor: [71, 85, 105],
          getLineWidth: 1500,
          lineWidthMinPixels: 1,
          lineWidthUnits: "meters",
          pickable: false,
        })
      );
    }

    if (!pts.length) return list;

    if (mode === "3d") {
      list.push(
        new ColumnLayer({
          id: "volumetric-columns",
          data: pts,
          diskResolution: 12,
          radius: 5000,
          extruded: true,
          pickable: true,
          elevationScale: 1,
          autoHighlight: true,
          getPosition: (d) => [d.lon, d.lat],
          getFillColor: pointColor,
          getElevation: (d) => Number(d.elevation) || 0,
        })
      );
    } else if (mode === "heatmap") {
      list.push(
        new HeatmapLayer({
          id: "density-heatmap",
          data: pts,
          getPosition: (d) => [d.lon, d.lat],
          getWeight: (d) => Number(d.volume) || 0,
          radiusPixels: 60,
          intensity: 1,
          threshold: 0.03,
        })
      );
    } else {
      list.push(
        new ScatterplotLayer({
          id: "intensity-scatter",
          data: pts,
          pickable: true,
          opacity: 0.8,
          stroked: false,
          filled: true,
          radiusUnits: "meters",
          radiusMinPixels: 3,
          radiusMaxPixels: 80,
          getPosition: (d) => [d.lon, d.lat],
          getRadius: (d) => Number(d.radius) || 4000,
          getFillColor: pointColor,
        })
      );
    }

    return list;
  }, [data, geojson, mode]);

  const getTooltip = ({ object }) => {
    if (!object || object.type === "Feature") return null;
    const vol = object.volume ?? object.adult_enrolments;
    return {
      html: `<b>${object.district || "—"}</b> (${object.state || "—"})<br/>Volume: ${fmt(vol)}<br/>Centroid: ${object.centroid_source || "—"}`,
      style: {
        color: "#0f172a",
        backgroundColor: "rgba(255,255,255,0.95)",
        fontSize: "12px",
        padding: "8px 10px",
        borderRadius: "8px",
        boxShadow: "0 4px 16px rgba(15,23,42,0.12)",
      },
    };
  };

  if (loading && !data) return <div className="loading">Preparing map…</div>;
  if (err) return <div className="error-box">{err}</div>;
  if (!data) return null;

  const legend = data.legend || {};
  const k = data.kpis || {};
  const src = data.centroid_sources || {};
  const scaleLabel = scale === "linear" ? "Linear (True Scale)" : "Logarithmic (Balanced)";
  const empty = !data.points?.length;

  return (
    <div className="page">
      <header className="page-header">
        <div className="page-header__title">
          <h2>Geospatial Intel</h2>
          <span className="badge">{data.count ?? 0} points</span>
        </div>
        <div className="page-controls">
          <label className="ctrl">
            Mode
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="2d">Intensity (2D)</option>
              <option value="heatmap">Density (Heatmap)</option>
              <option value="3d">Volumetric (3D)</option>
            </select>
          </label>
          <label className="ctrl">
            Depth
            <select value={depth} onChange={(e) => setDepth(e.target.value)}>
              <option value="top5">Top 5 Priority</option>
              <option value="all">Show All Districts</option>
            </select>
          </label>
          <label className="ctrl">
            Scaling
            <select value={scale} onChange={(e) => setScale(e.target.value)}>
              <option value="log">Logarithmic (Balanced)</option>
              <option value="linear">Linear (True Scale)</option>
            </select>
          </label>
        </div>
      </header>

      <section className="kpi-row kpi-row--3">
        <KpiCard label="Visible volume" value={k.visible_volume} accent="blue" />
        <KpiCard label="Hotspot" value={k.hotspot || "—"} format={false} accent="rose" />
        <KpiCard label="Districts" value={k.districts} format={false} accent="slate" />
      </section>

      {Object.keys(src).length > 0 && (
        <p className="panel-meta" style={{ margin: 0 }}>
          Centroid sources: {Object.entries(src).map(([k, v]) => `${k}=${v}`).join(" · ")}
        </p>
      )}

      <section className="panel panel--map">
        <div className="map-box">
          {empty ? (
            <div className="map-empty">Nothing to map after aggregation.</div>
          ) : (
            <DeckGL
              viewState={viewState}
              onViewStateChange={({ viewState: vs }) => setViewState(vs)}
              controller={true}
              layers={layers}
              getTooltip={getTooltip}
              style={{ width: "100%", height: "100%" }}
            >
              <Map mapStyle={MAP_STYLE} attributionControl={false} />
            </DeckGL>
          )}
        </div>

        <div className="map-legend-block">
          <h4 className="map-legend-title">Intensity scale</h4>
          <div className="legend-row">
            <div className="legend-item">
              <div className="legend-item__head">
                <span className="dot" style={{ background: HEX_COLORS.low }} />
                <strong>Low</strong>
              </div>
              <div className="muted">&lt; {fmt(legend.low_max)}</div>
              <div className="muted legend-item__sub">bottom 10% of range</div>
            </div>
            <div className="legend-item">
              <div className="legend-item__head">
                <span className="dot" style={{ background: HEX_COLORS.medium }} />
                <strong>Medium</strong>
              </div>
              <div className="muted">
                {fmt(legend.low_max)} – {fmt(legend.medium_max)}
              </div>
              <div className="muted legend-item__sub">10–30% of range</div>
            </div>
            <div className="legend-item">
              <div className="legend-item__head">
                <span className="dot" style={{ background: HEX_COLORS.high }} />
                <strong>High</strong>
              </div>
              <div className="muted">≥ {fmt(legend.medium_max)}</div>
              <div className="muted legend-item__sub">top of range</div>
            </div>
          </div>
          <p className="map-legend-caption">
            Volume range {fmt(data.min)} – {fmt(data.max)} · marker colours use this intensity scale · size/elevation
            scaling: <strong>{scaleLabel}</strong>
          </p>
        </div>
      </section>

      <section className="panel panel--export">
        <div className="panel-head">
          <h3>Data export</h3>
        </div>
        <div className="export-row">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => triggerDownload(api.exportMap("full", q()), "map_data.csv")}
          >
            Full data
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => triggerDownload(api.exportMap("top20", q()), "top_districts.csv")}
          >
            Top 20 districts
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => triggerDownload(api.exportMap("top10", q()), "top_states.csv")}
          >
            Top 10 states
          </button>
        </div>
      </section>
    </div>
  );
}
