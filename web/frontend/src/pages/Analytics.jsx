import { useEffect, useMemo, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { api, exportChartAsPNG, filterParams, fmt, triggerDownload } from "../api";
import KpiCard from "../components/KpiCard";

const PIE_COLORS = ["#10b981", "#f59e0b", "#8b5cf6"];

const tip = {
  contentStyle: {
    background: "rgba(255,255,255,0.96)",
    border: "1px solid rgba(203,213,225,0.8)",
    borderRadius: 12,
    boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
    fontSize: 12,
  },
};

/** Risk score → warm red scale (matches dashboard risk bars). */
function riskFill(score, minS = 50, maxS = 100) {
  const s = Number(score) || 0;
  const t = Math.max(0, Math.min(1, (s - minS) / Math.max(1e-6, maxS - minS)));
  const h = 12 + (1 - t) * 28; // red → amber
  const l = 42 - t * 10;
  return `hsl(${h} 78% ${l}%)`;
}

function shortState(s, n = 14) {
  const t = String(s || "");
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
}

function Dl({ id, name }) {
  return (
    <button type="button" className="btn btn-ghost btn-sm chart-dl-btn" onClick={() => exportChartAsPNG(id, name)}>
      <Download size={14} />
    </button>
  );
}

function ScatterTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0]?.payload || {};
  return (
    <div style={tip.contentStyle}>
      <div style={{ fontWeight: 700, color: "#0f172a", marginBottom: 4 }}>
        {p.district}
        <span style={{ fontWeight: 500, color: "#64748b" }}> · {p.state}</span>
      </div>
      <div style={{ color: "#334155" }}>
        Risk: <strong style={{ color: riskFill(p.risk_score) }}>{p.risk_score}</strong>
      </div>
      <div style={{ color: "#334155" }}>Volume: <strong>{fmt(p.volume)}</strong></div>
      {p.cv != null && <div style={{ color: "#64748b", fontSize: 11 }}>CV: {Number(p.cv).toFixed(2)}</div>}
      {p.reason && (
        <div style={{ color: "#64748b", fontSize: 11, marginTop: 4, maxWidth: 220 }}>{p.reason}</div>
      )}
    </div>
  );
}

function RadarTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0]?.payload || {};
  return (
    <div style={tip.contentStyle}>
      <div style={{ fontWeight: 700, color: "#0f172a", marginBottom: 4 }}>{p.full || p.state}</div>
      <div>Max risk: <strong>{p.max_risk}</strong></div>
      <div>Mean risk: <strong>{Number(p.mean_risk).toFixed(1)}</strong></div>
      <div>Flags: <strong>{p.flags}</strong></div>
      <div>Flagged volume: <strong>{fmt(p.flagged_volume)}</strong></div>
      {p.top_district && (
        <div style={{ marginTop: 4, color: "#64748b", fontSize: 11 }}>
          Top cell: {p.top_district} ({p.top_district_risk})
        </div>
      )}
    </div>
  );
}

export default function Analytics({ filters }) {
  const [data, setData] = useState(null);
  const [contamination, setContamination] = useState(0.05);
  const [minVolume, setMinVolume] = useState(50);
  const [showInv, setShowInv] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const fp = () => ({ ...filterParams(filters), contamination, min_volume: minVolume });

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.analytics(fp()));
      setErr("");
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [filters.states?.join(","), filters.start, filters.end, contamination, minVolume]);

  const scatter = useMemo(() => {
    const rows = (data?.scatter || []).map((r, i) => ({
      ...r,
      id: r.id || `${r.state}|${r.district}|${i}`,
      volume: Number(r.volume) || 0,
      risk_score: Number(r.risk_score) || 0,
      log_volume: Number(r.log_volume) || Math.log10(Math.max(Number(r.volume) || 1, 1)),
    }));
    return rows;
  }, [data?.scatter]);

  const riskMin = useMemo(
    () => (scatter.length ? Math.min(...scatter.map((r) => r.risk_score)) : 50),
    [scatter],
  );
  const riskMax = useMemo(
    () => (scatter.length ? Math.max(...scatter.map((r) => r.risk_score)) : 100),
    [scatter],
  );

  const radar = useMemo(
    () =>
      (data?.state_radar || []).map((r) => ({
        state: shortState(r.state, 11),
        max_risk: Number(r.max_risk) || 0,
        mean_risk: Number(r.mean_risk) || 0,
        flags: Number(r.flags) || 0,
        flagged_volume: Number(r.flagged_volume) || 0,
        top_district: r.top_district || "",
        top_district_risk: r.top_district_risk,
        full: r.state,
      })),
    [data?.state_radar],
  );

  const radarDomainMax = useMemo(
    () => Math.max(100, ...radar.map((r) => r.max_risk), 0) + 5,
    [radar],
  );

  const riskCells = useMemo(() => {
    // Prefer explicit risk_cells; fall back to scatter so table always matches plot
    const src = data?.risk_cells?.length ? data.risk_cells : scatter;
    return [...src]
      .map((r) => ({
        ...r,
        risk_score: Number(r.risk_score) || 0,
        volume: Number(r.volume) || 0,
        bio_ratio: r.bio_ratio != null ? Number(r.bio_ratio) : null,
        demo_ratio: r.demo_ratio != null ? Number(r.demo_ratio) : null,
        cv: r.cv != null ? Number(r.cv) : null,
      }))
      .sort((a, b) => b.risk_score - a.risk_score || b.volume - a.volume);
  }, [data?.risk_cells, scatter]);

  if (loading && !data) return <div className="loading">Loading analytics…</div>;
  if (err && !data) return <div className="error-box">{err}</div>;
  if (!data) return null;

  const pie = [
    { name: "New enrolments", value: data.workload.enrolments },
    { name: "Bio updates", value: data.workload.bio },
    { name: "Demo updates", value: data.workload.demo },
  ];

  const maxWatch = Math.max(...(data.watchlist || []).map((w) => w.volume), 1);

  return (
    <div className="page">
      <header className="page-header">
        <h2>Analytics</h2>
        <div className="page-controls">
          <label className="ctrl">
            Contamination
            <input
              type="number"
              step="0.01"
              min="0.01"
              max="0.15"
              value={contamination}
              onChange={(e) => setContamination(Number(e.target.value))}
            />
          </label>
          <label className="ctrl">
            Min volume
            <input type="number" min="0" value={minVolume} onChange={(e) => setMinVolume(Number(e.target.value))} />
          </label>
          <button type="button" className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <section className="kpi-row kpi-row--4">
        <KpiCard label="Total enrolments" value={data.kpis.total} delta={`18+: ${fmt(data.kpis.adult)}`} accent="blue" />
        <KpiCard label="Active states" value={data.kpis.states} format={false} accent="green" />
        <KpiCard label="Active districts" value={data.kpis.districts} format={false} accent="violet" />
        <KpiCard label="Rows in view" value={data.kpis.rows} format={false} accent="slate" />
      </section>

      <section className="bento bento--2">
        <article className="panel">
          <div className="panel-head">
            <h3>Growth trajectory</h3>
            <Dl id="chart-growth" name="growth.png" />
          </div>
          <div id="chart-growth" className="chart chart--md">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="growthFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} minTickGap={28} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "#64748b" }} tickFormatter={(v) => fmt(v)} axisLine={false} tickLine={false} width={52} />
                <Tooltip {...tip} formatter={(v) => fmt(v)} />
                <Area type="monotone" dataKey="volume" stroke="#3b82f6" fill="url(#growthFill)" strokeWidth={2} name="Volume" />
                <Brush dataKey="date" height={26} stroke="#93c5fd" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h3>Top regional drivers</h3>
            <Dl id="chart-regional" name="regional.png" />
          </div>
          <div id="chart-regional" className="chart chart--md">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.top_states} layout="vertical" margin={{ left: 8, right: 12, top: 8, bottom: 8 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={(v) => fmt(v)} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="state" width={100} tick={{ fontSize: 11, fill: "#475569" }} axisLine={false} tickLine={false} />
                <Tooltip {...tip} formatter={(v) => fmt(v)} />
                <Bar dataKey="volume" fill="#2563eb" radius={[0, 6, 6, 0]} name="Volume" maxBarSize={22} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      <section className="bento bento--2">
        <article className="panel">
          <div className="panel-head">
            <h3>Operational mix</h3>
            <Dl id="chart-ops" name="ops.png" />
          </div>
          <div id="chart-ops" className="chart chart--sm">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pie} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92} paddingAngle={3} stroke="none">
                  {pie.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip {...tip} formatter={(v) => fmt(v)} />
                <Legend iconType="circle" />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <p className="panel-meta">
            {data.ratios?.bio_per_enrol}× bio · {data.ratios?.demo_per_enrol}× demo per enrolment
          </p>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h3>Watchlist</h3>
          </div>
          <div className="table-wrap table-wrap--fill">
            <table className="data">
              <thead>
                <tr>
                  <th>State</th>
                  <th>District</th>
                  <th>Volume</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(data.watchlist || []).map((r, i) => (
                  <tr key={i}>
                    <td>{r.state}</td>
                    <td>{r.district}</td>
                    <td className="mono">{fmt(r.volume)}</td>
                    <td style={{ minWidth: 80 }}>
                      <div className="progress-bar">
                        <span style={{ width: `${Math.min(100, (r.volume / maxWatch) * 100)}%` }} />
                      </div>
                    </td>
                  </tr>
                ))}
                {!data.watchlist?.length && (
                  <tr>
                    <td colSpan={4} className="muted">
                      No low-volume districts
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h3>Risk radar</h3>
          <div className="panel-head-actions">
            <span className="badge warn">{data.kpis.flags} flags</span>
            <Dl id="chart-radar" name="radar.png" />
          </div>
        </div>
        <p className="panel-meta" style={{ marginTop: 0 }}>
          State aggregates of the same high-risk district cells below. Ranked by max risk (then mean, flags). Max risk
          equals the top district score for that state.
        </p>
        <div className="bento bento--2">
          <div id="chart-radar" className="chart chart--lg">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radar} cx="50%" cy="52%" outerRadius="72%">
                <PolarGrid stroke="#e2e8f0" />
                <PolarAngleAxis dataKey="state" tick={{ fontSize: 10, fill: "#475569" }} />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, radarDomainMax]}
                  tick={{ fontSize: 10, fill: "#94a3b8" }}
                  tickCount={5}
                />
                <Radar
                  name="Max risk"
                  dataKey="max_risk"
                  stroke="#dc2626"
                  fill="#dc2626"
                  fillOpacity={0.22}
                  strokeWidth={2}
                />
                <Radar
                  name="Mean risk"
                  dataKey="mean_risk"
                  stroke="#f59e0b"
                  fill="#f59e0b"
                  fillOpacity={0.1}
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                />
                <Legend />
                <Tooltip content={<RadarTooltip />} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <div className="table-wrap table-wrap--fill">
            <table className="data">
              <thead>
                <tr>
                  <th>State</th>
                  <th>Max</th>
                  <th>Mean</th>
                  <th>Flags</th>
                  <th>Flagged vol</th>
                  <th>Top district cell</th>
                </tr>
              </thead>
              <tbody>
                {(data.state_radar || []).map((r, i) => (
                  <tr key={r.state || i}>
                    <td>{r.state}</td>
                    <td>
                      <span
                        className="badge danger"
                        style={{
                          background: `${riskFill(r.max_risk, riskMin, riskMax)}18`,
                          color: riskFill(r.max_risk, riskMin, riskMax),
                          border: `1px solid ${riskFill(r.max_risk, riskMin, riskMax)}44`,
                        }}
                      >
                        {r.max_risk}
                      </span>
                    </td>
                    <td className="mono">{Number(r.mean_risk).toFixed(1)}</td>
                    <td className="mono">{r.flags}</td>
                    <td className="mono">{fmt(r.flagged_volume)}</td>
                    <td style={{ whiteSpace: "normal", maxWidth: 180 }}>
                      {r.top_district ? (
                        <>
                          {r.top_district}{" "}
                          <span className="muted mono">({r.top_district_risk ?? r.max_risk})</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
                {!data.state_radar?.length && (
                  <tr>
                    <td colSpan={6} className="muted">
                      No flagged states under current thresholds.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h3>High-risk cells</h3>
          <div className="panel-head-actions">
            <span className="badge danger">{riskCells.length} cells</span>
            <Dl id="chart-scatter" name="scatter.png" />
          </div>
        </div>
        <p className="panel-meta" style={{ marginTop: 0 }}>
          District-level Isolation Forest outliers (same set as radar). X = enrolment volume (log scale), Y = risk
          score, bubble size ∝ volume, colour ∝ risk.
        </p>
        <div id="chart-scatter" className="chart chart--lg" style={{ marginBottom: 12 }}>
          {scatter.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 12, right: 20, left: 8, bottom: 12 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis
                  type="number"
                  dataKey="log_volume"
                  name="Volume"
                  domain={["auto", "auto"]}
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => {
                    const n = 10 ** Number(v);
                    return fmt(n);
                  }}
                  label={{ value: "Volume (log)", position: "insideBottom", offset: -2, fill: "#94a3b8", fontSize: 11 }}
                />
                <YAxis
                  type="number"
                  dataKey="risk_score"
                  name="Risk"
                  domain={[Math.max(0, Math.floor(riskMin - 5)), Math.min(100, Math.ceil(riskMax + 5))]}
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  axisLine={false}
                  tickLine={false}
                  width={42}
                  label={{ value: "Risk", angle: -90, position: "insideLeft", fill: "#94a3b8", fontSize: 11 }}
                />
                <ZAxis type="number" dataKey="volume" range={[60, 320]} name="Volume" />
                <ReferenceLine
                  y={riskMin + (riskMax - riskMin) * 0.75}
                  stroke="#fecaca"
                  strokeDasharray="4 4"
                  ifOverflow="extendDomain"
                />
                <Tooltip cursor={{ strokeDasharray: "3 3", stroke: "#94a3b8" }} content={<ScatterTooltip />} />
                <Scatter data={scatter} name="Risk cells" fillOpacity={0.88} isAnimationActive={false}>
                  {scatter.map((entry) => (
                    <Cell
                      key={entry.id}
                      fill={riskFill(entry.risk_score, riskMin, riskMax)}
                      stroke="#fff"
                      strokeWidth={1}
                    />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          ) : (
            <div className="loading" style={{ height: "100%" }}>
              No high-risk cells under current thresholds.
            </div>
          )}
        </div>
        <div className="risk-legends" style={{ marginBottom: 10 }}>
          <div className="risk-legend-block">
            <span className="risk-legend-label">Risk score</span>
            <div className="risk-gradient-scale" aria-hidden>
              <span className="risk-gradient-bar" />
              <div className="risk-gradient-ends">
                <span>{Math.round(riskMin)}</span>
                <span>{Math.round(riskMax)}</span>
              </div>
            </div>
          </div>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>State</th>
                <th>District</th>
                <th>Risk</th>
                <th>Volume</th>
                <th>CV</th>
                <th>Bio</th>
                <th>Demo</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {riskCells.slice(0, 20).map((r, i) => (
                <tr key={`${r.state}-${r.district}-${i}`}>
                  <td className="mono muted">{i + 1}</td>
                  <td>{r.state}</td>
                  <td>{r.district}</td>
                  <td>
                    <span
                      className="badge danger"
                      style={{
                        background: `${riskFill(r.risk_score, riskMin, riskMax)}18`,
                        color: riskFill(r.risk_score, riskMin, riskMax),
                        border: `1px solid ${riskFill(r.risk_score, riskMin, riskMax)}44`,
                      }}
                    >
                      {r.risk_score}
                    </span>
                  </td>
                  <td className="mono">{fmt(r.volume)}</td>
                  <td className="mono">{r.cv != null ? r.cv.toFixed(2) : "—"}</td>
                  <td className="mono">{r.bio_ratio != null ? r.bio_ratio.toFixed(2) : "—"}</td>
                  <td className="mono">{r.demo_ratio != null ? r.demo_ratio.toFixed(2) : "—"}</td>
                  <td style={{ whiteSpace: "normal", maxWidth: 280 }}>{r.reason}</td>
                </tr>
              ))}
              {!riskCells.length && (
                <tr>
                  <td colSpan={9} className="muted">
                    No multi-feature anomalies under thresholds.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 10 }} onClick={() => setShowInv((s) => !s)}>
          {showInv ? "Hide" : "Show"} investigation notes
        </button>
        {showInv && (
          <div className="table-wrap" style={{ marginTop: 8, maxHeight: 240 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>State</th>
                  <th>District</th>
                  <th>Risk</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {(data.investigation_notes || []).map((r, i) => (
                  <tr key={i}>
                    <td>{r.state}</td>
                    <td>{r.district}</td>
                    <td>
                      <span className="badge danger">{r.risk_score}</span>
                    </td>
                    <td style={{ whiteSpace: "normal", maxWidth: 420 }}>{r.investigation_notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel panel--export">
        <div className="panel-head">
          <h3>Export</h3>
        </div>
        <div className="export-row">
          {["regional", "trends", "risk", "ops"].map((kind) => (
            <button
              key={kind}
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => triggerDownload(api.exportAnalytics(kind, filterParams(filters)), `${kind}.csv`)}
            >
              {kind[0].toUpperCase() + kind.slice(1)} CSV
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
