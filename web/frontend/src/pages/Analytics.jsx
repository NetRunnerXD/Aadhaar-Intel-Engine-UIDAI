import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
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
import { api, filterParams, fmt, triggerDownload } from "../api";
import KpiCard from "../components/KpiCard";

const PIE_COLORS = ["#10b981", "#f59e0b", "#8b5cf6"];

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
    <>
      <div className="page-header">
        <div>
          <h2>Analytics</h2>
          <p>Growth, ops mix, watchlist, risk radar · Isolation Forest</p>
        </div>
      </div>

      <div className="toolbar">
        <label>
          Contamination
          <input type="number" step="0.01" min="0.01" max="0.15" value={contamination} onChange={(e) => setContamination(Number(e.target.value))} />
        </label>
        <label>
          Min volume
          <input type="number" min="0" value={minVolume} onChange={(e) => setMinVolume(Number(e.target.value))} />
        </label>
        <button className="btn btn-ghost" onClick={load}>
          Refresh
        </button>
      </div>

      <div className="grid grid-kpi" style={{ marginBottom: "1rem" }}>
        <KpiCard label="Total enrolments" value={data.kpis.total} delta={`18+: ${fmt(data.kpis.adult)}`} />
        <KpiCard label="Active states" value={data.kpis.states} format={false} />
        <KpiCard label="Active districts" value={data.kpis.districts} format={false} />
        <KpiCard label="Rows in view" value={data.kpis.rows} format={false} />
      </div>

      <div className="grid grid-2" style={{ marginBottom: "1rem" }}>
        <div className="card">
          <h3>Growth trajectory</h3>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.daily}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={28} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => fmt(v)} />
                <Tooltip formatter={(v) => fmt(v)} />
                <Area type="monotone" dataKey="volume" stroke="#3b82f6" fill="#dbeafe" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3>Top regional drivers</h3>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.top_states} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={(v) => fmt(v)} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="state" width={100} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => fmt(v)} />
                <Bar dataKey="volume" fill="#2563eb" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: "1rem" }}>
        <div className="card">
          <h3>Operational efficiency</h3>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pie} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92}>
                  {pie.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => fmt(v)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <p className="muted">
            Ratio: <strong>{data.ratios?.bio_per_enrol}×</strong> bio and <strong>{data.ratios?.demo_per_enrol}×</strong>{" "}
            demo updates per enrolment unit.
          </p>
        </div>
        <div className="card">
          <h3>Watchlist (low volume)</h3>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>State</th>
                  <th>District</th>
                  <th>Volume</th>
                  <th></th>
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
        </div>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <h3>Risk radar — top 10 states by flagged volume</h3>
        <p className="muted">Radial = risk score · labels include compact volume · not a fraud verdict</p>
        <div className="grid grid-2">
          <div style={{ height: 380 }}>
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radar}>
                <PolarGrid stroke="#e2e8f0" />
                <PolarAngleAxis dataKey="state" tick={{ fontSize: 10 }} />
                <PolarRadiusAxis tick={{ fontSize: 10 }} />
                <Radar name="Max risk" dataKey="max_risk" stroke="#dc2626" fill="#dc2626" fillOpacity={0.25} />
                <Radar name="Mean risk" dataKey="mean_risk" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.12} />
                <Legend />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <div>
            <div className="banner warn" style={{ marginBottom: 8 }}>
              <strong>{data.kpis.flags} flags</strong>
            </div>
            <div className="table-wrap" style={{ maxHeight: 320 }}>
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
        </div>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <h3>District-level high-risk cells</h3>
        <div style={{ height: 320, marginBottom: 12 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart>
              <CartesianGrid stroke="#e2e8f0" />
              <XAxis type="number" dataKey="risk_score" name="Risk" tick={{ fontSize: 11 }} />
              <YAxis type="number" dataKey="volume" name="Volume" tickFormatter={(v) => fmt(v)} tick={{ fontSize: 11 }} />
              <ZAxis type="number" dataKey="risk_score" range={[40, 200]} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(v, n) => (n === "volume" ? fmt(v) : v)} />
              <Scatter data={data.scatter || []} fill="#dc2626" fillOpacity={0.65} />
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
                  <td>{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => setShowInv((s) => !s)}>
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
      </div>

      <div className="card">
        <h3>Export intelligence pack</h3>
        <div className="toolbar">
          {["regional", "trends", "risk", "ops"].map((kind) => (
            <button
              key={kind}
              className="btn btn-primary btn-sm"
              onClick={() => triggerDownload(api.exportAnalytics(kind, filterParams(filters)), `${kind}.csv`)}
            >
              {kind[0].toUpperCase() + kind.slice(1)} CSV
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
