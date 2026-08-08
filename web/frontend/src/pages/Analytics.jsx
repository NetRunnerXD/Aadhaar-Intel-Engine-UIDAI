import { useEffect, useState } from "react";
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

function Dl({ id, name }) {
  return (
    <button type="button" className="btn btn-ghost btn-sm chart-dl-btn" onClick={() => exportChartAsPNG(id, name)}>
      <Download size={14} />
    </button>
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

  if (loading && !data) return <div className="loading">Loading analytics…</div>;
  if (err) return <div className="error-box">{err}</div>;
  if (!data) return null;

  const pie = [
    { name: "New enrolments", value: data.workload.enrolments },
    { name: "Bio updates", value: data.workload.bio },
    { name: "Demo updates", value: data.workload.demo },
  ];
  const radar = (data.state_radar || []).map((r) => ({
    state: `${String(r.state).slice(0, 12)}\nvol ${fmt(r.flagged_volume)}`,
    max_risk: Number(r.max_risk) || 0,
    mean_risk: Number(r.mean_risk) || 0,
    full: r.state,
  }));
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
        <div className="bento bento--2">
          <div id="chart-radar" className="chart chart--lg">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radar}>
                <PolarGrid stroke="#e2e8f0" />
                <PolarAngleAxis dataKey="state" tick={{ fontSize: 10, fill: "#64748b" }} />
                <PolarRadiusAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
                <Radar name="Max risk" dataKey="max_risk" stroke="#dc2626" fill="#dc2626" fillOpacity={0.25} />
                <Radar name="Mean risk" dataKey="mean_risk" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.12} />
                <Legend />
                <Tooltip {...tip} />
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
                  <th>Vol</th>
                </tr>
              </thead>
              <tbody>
                {(data.state_radar || []).map((r, i) => (
                  <tr key={i}>
                    <td>{r.state}</td>
                    <td>{r.max_risk}</td>
                    <td>{Number(r.mean_risk).toFixed?.(1) ?? r.mean_risk}</td>
                    <td>{r.flags}</td>
                    <td className="mono">{fmt(r.flagged_volume)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h3>High-risk cells</h3>
          <Dl id="chart-scatter" name="scatter.png" />
        </div>
        <div id="chart-scatter" className="chart chart--md" style={{ marginBottom: 12 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
              <XAxis type="number" dataKey="risk_score" name="Risk" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} />
              <YAxis type="number" dataKey="volume" name="Volume" tickFormatter={(v) => fmt(v)} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} />
              <ZAxis type="number" dataKey="risk_score" range={[40, 200]} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} {...tip} formatter={(v, n) => (n === "volume" ? fmt(v) : v)} />
              <Scatter data={data.scatter || []} fill="#dc2626" fillOpacity={0.65} name="Risk cells" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>State</th>
                <th>District</th>
                <th>Risk</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {(data.risk_cells || []).slice(0, 15).map((r, i) => (
                <tr key={i}>
                  <td>{r.state}</td>
                  <td>{r.district}</td>
                  <td>
                    <span className="badge danger">{r.risk_score}</span>
                  </td>
                  <td style={{ whiteSpace: "normal", maxWidth: 360 }}>{r.reason}</td>
                </tr>
              ))}
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
                    <td>{r.risk_score}</td>
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
