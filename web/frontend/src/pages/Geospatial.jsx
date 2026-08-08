import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { ColumnLayer, GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import Map from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  Compass,
  Crosshair,
  Download,
  Eye,
  EyeOff,
  Flame,
  Layers,
  LocateFixed,
  Map as MapIcon,
  Maximize2,
  Minimize2,
  Search,
  X,
} from "lucide-react";
import { api, filterParams, fmt, triggerDownload } from "../api";
import KpiCard from "../components/KpiCard";

const MAP_STYLES = {
  positron: {
    label: "Positron (light)",
    url: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  },
  voyager: {
    label: "Voyager",
    url: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
  },
  dark: {
    label: "Dark Matter",
    url: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  },
};

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
const INTENSITY_ORDER = ["low", "medium", "high"];

function resolveStateCentroid(state) {
  const s = String(state || "");
  if (STATE_CENTROIDS[s]) return STATE_CENTROIDS[s];
  const alt = s.replace(" And ", " & ");
  if (STATE_CENTROIDS[alt]) return STATE_CENTROIDS[alt];
  const alt2 = s.replace(" & ", " And ");
  if (STATE_CENTROIDS[alt2]) return STATE_CENTROIDS[alt2];
  return [22.0, 79.0];
}

function pointColor(d, selectedKey) {
  const key = `${d.state}||${d.district}`;
  if (selectedKey && key === selectedKey) return [37, 99, 235, 240];
  if (Array.isArray(d.color) && d.color.length >= 3) return d.color;
  return FALLBACK_COLORS[d.intensity] || FALLBACK_COLORS.medium;
}

function buildView({ states, mode }) {
  const pitch = mode === "3d" ? 55 : 0;
  if (states?.length === 1) {
    const [lat, lon] = resolveStateCentroid(states[0]);
    return { longitude: lon, latitude: lat, zoom: 6, pitch, bearing: 0 };
  }
  return { longitude: 79, latitude: 22.5, zoom: 4.1, pitch, bearing: 0 };
}

function boundsToView(bounds, mode) {
  if (!bounds) return null;
  const { min_lat, max_lat, min_lon, max_lon } = bounds;
  const latitude = (min_lat + max_lat) / 2;
  const longitude = (min_lon + max_lon) / 2;
  const latSpan = Math.max(0.4, max_lat - min_lat);
  const lonSpan = Math.max(0.4, max_lon - min_lon);
  const span = Math.max(latSpan, lonSpan);
  let zoom = 4.2;
  if (span < 2) zoom = 7;
  else if (span < 5) zoom = 6;
  else if (span < 10) zoom = 5;
  else if (span < 18) zoom = 4.4;
  return { longitude, latitude, zoom, pitch: mode === "3d" ? 55 : 0, bearing: 0 };
}

export default function Geospatial({ filters }) {
  const [depth, setDepth] = useState("top5");
  const [scale, setScale] = useState("log");
  const [mode, setMode] = useState("2d");
  const [basemap, setBasemap] = useState("positron");
  const [showBorders, setShowBorders] = useState(true);
  const [sizeBoost, setSizeBoost] = useState(1);
  const [heatRadius, setHeatRadius] = useState(60);
  const [minVolume, setMinVolume] = useState(0);
  const [bands, setBands] = useState({ low: true, medium: true, high: true });
  const [query, setQuery] = useState("");
  const [rankTab, setRankTab] = useState("districts");
  const [selected, setSelected] = useState(null);
  const [fullscreen, setFullscreen] = useState(false);

  const [data, setData] = useState(null);
  const [geojson, setGeojson] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [viewState, setViewState] = useState(() => buildView({ states: filters.states, mode: "2d" }));

  const mapShellRef = useRef(null);

  const intensityParam = useMemo(() => {
    const on = INTENSITY_ORDER.filter((b) => bands[b]);
    if (on.length === 3) return undefined;
    if (!on.length) return "none";
    return on.join(",");
  }, [bands]);

  const q = () => ({
    ...filterParams(filters),
    depth,
    scale,
    mode,
    min_volume: minVolume > 0 ? minVolume : undefined,
    intensity: intensityParam,
  });

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
        setSelected(null);
        const fitted = boundsToView(d.bounds, mode) || buildView({ states: filters.states, mode });
        setViewState({ ...fitted, bearing: 0 });
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
  }, [filters.states?.join(","), filters.start, filters.end, depth, scale, mode, minVolume, intensityParam]);

  // Fullscreen change sync
  useEffect(() => {
    const onFs = () => {
      const el = mapShellRef.current;
      setFullscreen(Boolean(el && document.fullscreenElement === el));
    };
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  const toggleFullscreen = async () => {
    const el = mapShellRef.current;
    if (!el) return;
    try {
      if (!document.fullscreenElement) {
        await el.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch {
      // Fallback: CSS-only expand if Fullscreen API blocked
      setFullscreen((f) => !f);
    }
  };

  const selectedKey = selected ? `${selected.state}||${selected.district}` : null;

  const filteredPoints = useMemo(() => {
    const pts = data?.points || [];
    if (!query.trim()) return pts;
    const qn = query.trim().toLowerCase();
    return pts.filter(
      (p) =>
        String(p.district || "")
          .toLowerCase()
          .includes(qn) ||
        String(p.state || "")
          .toLowerCase()
          .includes(qn)
    );
  }, [data, query]);

  const layers = useMemo(() => {
    const pts = filteredPoints;
    const list = [];

    if (showBorders && geojson) {
      list.push(
        new GeoJsonLayer({
          id: "india-state-borders",
          data: geojson,
          stroked: true,
          filled: false,
          opacity: 0.5,
          getLineColor: basemap === "dark" ? [148, 163, 184, 180] : [71, 85, 105, 200],
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
          radius: 5000 * sizeBoost,
          extruded: true,
          pickable: true,
          elevationScale: 1,
          autoHighlight: true,
          getPosition: (d) => [d.lon, d.lat],
          getFillColor: (d) => pointColor(d, selectedKey),
          getElevation: (d) => (Number(d.elevation) || 0) * sizeBoost,
          onClick: ({ object }) => object && setSelected(object),
        })
      );
    } else if (mode === "heatmap") {
      list.push(
        new HeatmapLayer({
          id: "density-heatmap",
          data: pts,
          getPosition: (d) => [d.lon, d.lat],
          getWeight: (d) => Number(d.volume) || 0,
          radiusPixels: heatRadius,
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
          opacity: 0.85,
          stroked: true,
          filled: true,
          radiusUnits: "meters",
          radiusMinPixels: 3,
          radiusMaxPixels: 90,
          lineWidthMinPixels: 1,
          getPosition: (d) => [d.lon, d.lat],
          getRadius: (d) => (Number(d.radius) || 4000) * sizeBoost,
          getFillColor: (d) => pointColor(d, selectedKey),
          getLineColor: (d) => {
            const key = `${d.state}||${d.district}`;
            return selectedKey && key === selectedKey ? [37, 99, 235, 255] : [255, 255, 255, 120];
          },
          onClick: ({ object }) => object && setSelected(object),
        })
      );
    }

    return list;
  }, [filteredPoints, geojson, mode, showBorders, sizeBoost, heatRadius, selectedKey, basemap]);

  const getTooltip = ({ object }) => {
    if (!object || object.type === "Feature") return null;
    const vol = object.volume ?? object.adult_enrolments;
    return {
      html: `<div style="font-weight:700;margin-bottom:2px">${object.district || "—"}</div>
        <div style="opacity:.85">${object.state || "—"}</div>
        <div style="margin-top:6px">Volume: <b>${fmt(vol)}</b></div>
        <div>Intensity: <b>${object.intensity || "—"}</b></div>
        <div>Centroid: ${object.centroid_source || "—"}</div>`,
      style: {
        color: "#0f172a",
        backgroundColor: "rgba(255,255,255,0.97)",
        fontSize: "12px",
        padding: "10px 12px",
        borderRadius: "10px",
        boxShadow: "0 8px 28px rgba(15,23,42,0.14)",
        border: "1px solid rgba(226,232,240,0.9)",
        maxWidth: "240px",
      },
    };
  };

  const flyTo = useCallback((lat, lon, zoom = 7) => {
    setViewState((v) => ({
      ...v,
      latitude: Number(lat),
      longitude: Number(lon),
      zoom,
      transitionDuration: 600,
    }));
  }, []);

  const resetView = () => {
    const fitted = boundsToView(data?.bounds, mode) || buildView({ states: filters.states, mode });
    setViewState({ ...fitted, bearing: 0, transitionDuration: 500 });
  };

  const flyHotspot = () => {
    const hp = data?.hotspot_point;
    if (!hp) return;
    setSelected(hp);
    flyTo(hp.lat, hp.lon, 7.2);
  };

  const toggleBand = (band) => {
    setBands((prev) => {
      const next = { ...prev, [band]: !prev[band] };
      // keep at least one band on
      if (!INTENSITY_ORDER.some((b) => next[b])) return prev;
      return next;
    });
  };

  if (loading && !data) return <div className="loading">Preparing map…</div>;
  if (err) return <div className="error-box">{err}</div>;
  if (!data) return null;

  const legend = data.legend || {};
  const k = data.kpis || {};
  const src = data.centroid_sources || {};
  const scaleLabel = scale === "linear" ? "Linear" : "Log";
  const empty = !(data.points || []).length;
  const ic = data.intensity_counts || {};
  const iv = data.intensity_volume || {};
  const topDistricts = data.top_districts || [];
  const topStates = data.top_states || [];

  const mapShellClass = `geo-map-shell ${fullscreen ? "is-fullscreen" : ""}`;

  return (
    <div className="page geo-page">
      <header className="page-header">
        <div className="page-header__title">
          <h2>Geospatial Intel</h2>
          <span className="badge">{data.count ?? 0} points</span>
          {loading && <span className="badge warn">Updating…</span>}
        </div>
        <div className="page-controls geo-toolbar">
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
              <option value="top5">Top 5 / state</option>
              <option value="all">All districts</option>
            </select>
          </label>
          <label className="ctrl">
            Scaling
            <select value={scale} onChange={(e) => setScale(e.target.value)}>
              <option value="log">Log (balanced)</option>
              <option value="linear">Linear</option>
            </select>
          </label>
          <label className="ctrl">
            Basemap
            <select value={basemap} onChange={(e) => setBasemap(e.target.value)}>
              {Object.entries(MAP_STYLES).map(([id, s]) => (
                <option key={id} value={id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="ctrl">
            Min vol
            <input
              type="number"
              min={0}
              step={100}
              value={minVolume}
              onChange={(e) => setMinVolume(Number(e.target.value) || 0)}
            />
          </label>
        </div>
      </header>

      <section className="kpi-row kpi-row--4 geo-kpis">
        <KpiCard label="Mapped volume" value={k.visible_volume} accent="blue" />
        <KpiCard label="Hotspot" value={k.hotspot || "—"} format={false} accent="rose" />
        <KpiCard label="Districts" value={k.districts} format={false} accent="slate" />
        <KpiCard
          label="High intensity"
          value={k.high_share_pct != null ? `${k.high_share_pct}%` : "—"}
          format={false}
          delta={`${ic.high || 0} cells`}
          accent="amber"
        />
      </section>

      <section className="geo-layout">
        <div ref={mapShellRef} className={mapShellClass}>
          <div className="geo-map-canvas">
            {empty ? (
              <div className="map-empty">Nothing to map under current filters.</div>
            ) : (
              <DeckGL
                viewState={viewState}
                onViewStateChange={({ viewState: vs }) => setViewState(vs)}
                controller={{ dragRotate: mode === "3d" }}
                layers={layers}
                getTooltip={getTooltip}
                style={{ width: "100%", height: "100%" }}
                onClick={(info) => {
                  if (!info?.object || info.object.type === "Feature") return;
                  setSelected(info.object);
                }}
              >
                <Map key={basemap} mapStyle={MAP_STYLES[basemap].url} attributionControl={false} />
              </DeckGL>
            )}
          </div>

          {/* Floating map tools */}
          <div className="geo-map-tools" aria-label="Map tools">
            <button type="button" className="geo-tool-btn" title="Fullscreen" onClick={toggleFullscreen}>
              {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button type="button" className="geo-tool-btn" title="Reset view" onClick={resetView}>
              <Compass size={16} />
            </button>
            <button type="button" className="geo-tool-btn" title="Fly to hotspot" onClick={flyHotspot} disabled={!data.hotspot_point}>
              <LocateFixed size={16} />
            </button>
            <button
              type="button"
              className={`geo-tool-btn ${showBorders ? "is-on" : ""}`}
              title={showBorders ? "Hide state borders" : "Show state borders"}
              onClick={() => setShowBorders((v) => !v)}
            >
              {showBorders ? <Eye size={16} /> : <EyeOff size={16} />}
            </button>
            <button
              type="button"
              className="geo-tool-btn"
              title="North up"
              onClick={() => setViewState((v) => ({ ...v, bearing: 0, pitch: mode === "3d" ? 55 : 0, transitionDuration: 400 }))}
            >
              <Crosshair size={16} />
            </button>
          </div>

          {/* Search + intensity chips */}
          <div className="geo-map-overlay-top">
            <div className="geo-search">
              <Search size={15} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search district or state…"
              />
              {query && (
                <button type="button" className="geo-search-clear" onClick={() => setQuery("")} aria-label="Clear search">
                  <X size={14} />
                </button>
              )}
            </div>
            <div className="geo-band-chips">
              {INTENSITY_ORDER.map((b) => (
                <button
                  key={b}
                  type="button"
                  className={`geo-band-chip ${bands[b] ? "on" : ""}`}
                  style={{ "--band": HEX_COLORS[b] }}
                  onClick={() => toggleBand(b)}
                >
                  <i />
                  {b}
                  <span>{ic[b] ?? 0}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Layer size / heat controls */}
          <div className="geo-map-overlay-bottom">
            <div className="geo-slider-card">
              <div className="geo-slider-row">
                <Layers size={14} />
                <label>
                  Marker size
                  <input
                    type="range"
                    min={0.5}
                    max={2.5}
                    step={0.1}
                    value={sizeBoost}
                    onChange={(e) => setSizeBoost(Number(e.target.value))}
                    disabled={mode === "heatmap"}
                  />
                </label>
                <span className="mono">{sizeBoost.toFixed(1)}×</span>
              </div>
              {mode === "heatmap" && (
                <div className="geo-slider-row">
                  <Flame size={14} />
                  <label>
                    Heat radius
                    <input
                      type="range"
                      min={20}
                      max={120}
                      step={5}
                      value={heatRadius}
                      onChange={(e) => setHeatRadius(Number(e.target.value))}
                    />
                  </label>
                  <span className="mono">{heatRadius}px</span>
                </div>
              )}
              <div className="geo-overlay-meta">
                {fmt(data.min)} – {fmt(data.max)} · {scaleLabel} · {Object.entries(src).map(([k, v]) => `${k}:${v}`).join(" · ") || "—"}
              </div>
            </div>

            <div className="geo-legend-compact">
              <span className="geo-legend-title">Intensity</span>
              {["low", "medium", "high"].map((b) => (
                <span key={b} className="geo-legend-item">
                  <i style={{ background: HEX_COLORS[b] }} />
                  {b}
                  <em>
                    {b === "low" && `< ${fmt(legend.low_max)}`}
                    {b === "medium" && `${fmt(legend.low_max)}–${fmt(legend.medium_max)}`}
                    {b === "high" && `≥ ${fmt(legend.medium_max)}`}
                  </em>
                </span>
              ))}
            </div>
          </div>

          {/* Selection card */}
          {selected && (
            <div className="geo-selection-card">
              <div className="geo-selection-head">
                <div>
                  <strong>{selected.district}</strong>
                  <div className="muted">{selected.state}</div>
                </div>
                <button type="button" className="icon-btn" onClick={() => setSelected(null)} aria-label="Close">
                  <X size={14} />
                </button>
              </div>
              <div className="geo-selection-grid">
                <div>
                  <span className="muted">Volume</span>
                  <strong className="mono">{fmt(selected.volume ?? selected.adult_enrolments)}</strong>
                </div>
                <div>
                  <span className="muted">Intensity</span>
                  <strong style={{ color: HEX_COLORS[selected.intensity] || "#334155" }}>{selected.intensity || "—"}</strong>
                </div>
                <div>
                  <span className="muted">Centroid</span>
                  <strong>{selected.centroid_source || "—"}</strong>
                </div>
                <div>
                  <span className="muted">Coords</span>
                  <strong className="mono">
                    {Number(selected.lat).toFixed(3)}, {Number(selected.lon).toFixed(3)}
                  </strong>
                </div>
              </div>
              <div className="geo-selection-actions">
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => flyTo(selected.lat, selected.lon, 7.5)}>
                  <MapIcon size={14} /> Focus
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    const text = `${selected.district}, ${selected.state} · ${fmt(selected.volume)} · ${selected.lat},${selected.lon}`;
                    navigator.clipboard?.writeText(text);
                  }}
                >
                  Copy
                </button>
              </div>
            </div>
          )}
        </div>

        <aside className="geo-side">
          <div className="panel geo-side-panel">
            <div className="panel-head">
              <div className="mix-tabs" role="tablist">
                <button
                  type="button"
                  className={`mix-tab ${rankTab === "districts" ? "active" : ""}`}
                  onClick={() => setRankTab("districts")}
                >
                  Top districts
                </button>
                <button
                  type="button"
                  className={`mix-tab ${rankTab === "states" ? "active" : ""}`}
                  onClick={() => setRankTab("states")}
                >
                  Top states
                </button>
              </div>
            </div>

            <div className="geo-rank-list">
              {rankTab === "districts" &&
                topDistricts.map((r) => (
                  <button
                    key={`${r.state}-${r.district}`}
                    type="button"
                    className={`geo-rank-item ${selected?.district === r.district && selected?.state === r.state ? "active" : ""}`}
                    onClick={() => {
                      setSelected(r);
                      flyTo(r.lat, r.lon, 7.2);
                    }}
                  >
                    <span className="geo-rank-num">{r.rank}</span>
                    <span className="geo-rank-main">
                      <strong>{r.district}</strong>
                      <span className="muted">{r.state}</span>
                    </span>
                    <span className="geo-rank-meta">
                      <span className="mono">{fmt(r.volume)}</span>
                      <span className="geo-intensity-pill" style={{ "--c": HEX_COLORS[r.intensity] }}>
                        {r.intensity}
                      </span>
                    </span>
                  </button>
                ))}
              {rankTab === "states" &&
                topStates.map((r) => (
                  <div key={r.state} className="geo-rank-item is-static">
                    <span className="geo-rank-num">{r.rank}</span>
                    <span className="geo-rank-main">
                      <strong>{r.state}</strong>
                      <span className="muted">{r.districts} districts · {r.share_pct}%</span>
                    </span>
                    <span className="geo-rank-meta">
                      <span className="mono">{fmt(r.volume)}</span>
                    </span>
                  </div>
                ))}
              {rankTab === "districts" && !topDistricts.length && <p className="muted">No districts in view.</p>}
              {rankTab === "states" && !topStates.length && <p className="muted">No states in view.</p>}
            </div>
          </div>

          <div className="panel geo-side-panel">
            <div className="panel-head">
              <h3>Intensity split</h3>
            </div>
            <div className="geo-split">
              {INTENSITY_ORDER.map((b) => {
                const share = data.total_volume ? (100 * (iv[b] || 0)) / data.total_volume : 0;
                return (
                  <div key={b} className="geo-split-row">
                    <div className="geo-split-label">
                      <i style={{ background: HEX_COLORS[b] }} />
                      {b}
                      <span className="muted">{ic[b] || 0}</span>
                    </div>
                    <div className="geo-split-bar">
                      <span style={{ width: `${Math.max(share, share > 0 ? 2 : 0)}%`, background: HEX_COLORS[b] }} />
                    </div>
                    <span className="mono geo-split-val">{share.toFixed(1)}%</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="panel geo-side-panel">
            <div className="panel-head">
              <h3>Export</h3>
            </div>
            <div className="export-row">
              <button type="button" className="btn btn-primary btn-sm" onClick={() => triggerDownload(api.exportMap("full", q()), "map_data.csv")}>
                <Download size={14} /> Full CSV
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => triggerDownload(api.exportMap("top20", q()), "top_districts.csv")}>
                Top 20
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => triggerDownload(api.exportMap("top10", q()), "top_states.csv")}>
                Top states
              </button>
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
}
