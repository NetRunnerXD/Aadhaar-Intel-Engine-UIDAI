import { useEffect, useMemo, useState } from "react";
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import { api, filterParams, fmt, triggerDownload } from "../api";
import KpiCard from "../components/KpiCard";

const COLORS = { low: "#0ea5e9", medium: "#f59e0b", high: "#dc2626" };

function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (!points?.length) return;
    const lats = points.map((p) => p.lat);
    const lons = points.map((p) => p.lon);
    map.fitBounds(
      [
        [Math.min(...lats), Math.min(...lons)],
        [Math.max(...lats), Math.max(...lons)],
      ],
      { padding: [30, 30], maxZoom: 7 }
    );
  }, [points, map]);
  return null;
}

export default function Geospatial({ filters }) {
  const [depth, setDepth] = useState("all");
  const [scale, setScale] = useState("log");
  const [mode, setMode] = useState("2d");
  const [data, setData] = useState(null);
  const [borders, setBorders] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const q = () => ({ ...filterParams(filters), depth, scale, mode });

  useEffect(() => {
    api.geojson().then(setBorders).catch(() => setBorders(null));
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .map(q())
      .then((d) => {
        setData(d);
        setErr("");
      })
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [filters.states?.join(","), filters.start, filters.end, depth, scale, mode]);

  const borderStyle = useMemo(
    () => ({
      color: "#475569",
      weight: 1,
      fillOpacity: 0,
      opacity: 0.55,
    }),
    []
  );

  if (loading && !data) return <div className="loading">Preparing map…</div>;
  if (err) return <div className="error-box">{err}</div>;
  if (!data) return null;

  const legend = data.legend || {};
  const k = data.kpis || {};

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Geospatial Intel</h2>
          <p>District centroids · light basemap · intensity scale · state borders</p>
        </div>
        <span className="badge">{data.count} points</span>
      </div>

      <div className="grid grid-3" style={{ marginBottom: "1rem" }}>
        <KpiCard label="Visible volume" value={k.visible_volume} />
        <KpiCard label="Hotspot" value={k.hotspot || "—"} format={false} />
        <KpiCard label="Districts" value={k.districts} format={false} />
      </div>

      <div className="toolbar">
        <label>
          Mode
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="2d">Intensity (2D)</option>
            <option value="heatmap">Density (Heatmap)</option>
            <option value="3d">Volumetric (elevated)</option>
          </select>
        </label>
        <label>
          Depth
          <select value={depth} onChange={(e) => setDepth(e.target.value)}>
            <option value="all">Show all districts</option>
            <option value="top5">Top 5 priority</option>
          </select>
        </label>
        <label>
          Scaling
          <select value={scale} onChange={(e) => setScale(e.target.value)}>
            <option value="log">Logarithmic (balanced)</option>
            <option value="linear">Linear (true scale)</option>
          </select>
        </label>
      </div>

      {data.centroid_sources && (
        <p className="muted">Centroid sources: {JSON.stringify(data.centroid_sources)}</p>
      )}

      <div className="card">
        <div className="map-box">
          <MapContainer center={[22.5, 79]} zoom={5} style={{ height: "100%", width: "100%" }} scrollWheelZoom>
            <TileLayer
              attribution='&copy; <a href="https://carto.com/">CARTO</a>'
              url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            />
            {borders && <GeoJSON data={borders} style={borderStyle} />}
            <FitBounds points={data.points} />
            {(data.points || []).map((p, i) => {
              const baseR = p.radius || 8;
              const r =
                mode === "heatmap"
                  ? baseR * 1.35
                  : mode === "3d"
                    ? 4 + (p.elevation || 0) * 0.15
                    : baseR;
              const opacity = mode === "heatmap" ? 0.35 : 0.72;
              return (
                <CircleMarker
                  key={i}
                  center={[p.lat, p.lon]}
                  radius={r}
                  pathOptions={{
                    color: COLORS[p.intensity] || COLORS.medium,
                    fillColor: COLORS[p.intensity] || COLORS.medium,
                    fillOpacity: opacity,
                    weight: mode === "3d" ? 2 : 1,
                  }}
                >
                  <Tooltip>
                    <strong>{p.district}</strong>
                    <br />
                    {p.state}
                    <br />
                    Volume: {fmt(p.volume)}
                    <br />
                    Intensity: {p.intensity}
                    <br />
                    Centroid: {p.centroid_source}
                  </Tooltip>
                </CircleMarker>
              );
            })}
          </MapContainer>
        </div>
        {mode === "3d" && (
          <p className="muted" style={{ marginTop: 8 }}>
            Volumetric mode uses elevated marker size (web equivalent of Streamlit ColumnLayer).
          </p>
        )}

        <div className="legend-row">
          <div className="legend-item">
            <div>
              <span className="dot" style={{ background: COLORS.low }} />
              <strong>Low</strong>
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              &lt; {fmt(legend.low_max)}
            </div>
            <div className="muted">bottom 10% of range</div>
          </div>
          <div className="legend-item">
            <div>
              <span className="dot" style={{ background: COLORS.medium }} />
              <strong>Medium</strong>
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              {fmt(legend.low_max)} – {fmt(legend.medium_max)}
            </div>
            <div className="muted">10–30% of range</div>
          </div>
          <div className="legend-item">
            <div>
              <span className="dot" style={{ background: COLORS.high }} />
              <strong>High</strong>
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              ≥ {fmt(legend.medium_max)}
            </div>
            <div className="muted">
              volume {fmt(data.min)} – {fmt(data.max)} · scaling {scale}
            </div>
          </div>
        </div>
      </div>

      <div className="card section-gap">
        <h3>Data export</h3>
        <div className="toolbar">
          <button className="btn btn-primary btn-sm" onClick={() => triggerDownload(api.exportMap("full", q()), "map_data.csv")}>
            Full data CSV
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => triggerDownload(api.exportMap("top20", q()), "top_districts.csv")}>
            Top 20 districts
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => triggerDownload(api.exportMap("top10", q()), "top_states.csv")}>
            Top 10 states
          </button>
        </div>
      </div>
    </>
  );
}
