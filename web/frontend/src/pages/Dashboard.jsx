import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ComposedChart,
} from "recharts";
import { api, filterParams, fmt } from "../api";
import KpiCard from "../components/KpiCard";
import MarkdownBlock from "../components/MarkdownBlock";

const PIE_COLORS = ["#10b981", "#f59e0b", "#8b5cf6"];
const AGE_COLORS = ["#0ea5e9", "#6366f1", "#2563eb"];

export default function Dashboard({ filters, meta }) {
  const [contamination, setContamination] = useState(0.05);
  const [minVolume, setMinVolume] = useState(50);
  const [data, setData] = useState(null);
  const [insight, setInsight] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [showNote, setShowNote] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    setErr("");
    try {
      const p = { ...filterParams(filters), contamination, min_volume: minVolume };
      const d = await api.dashboard(p);
      setData(d);
      const ins = await api.insightDashboard(p);
      setInsight(ins.markdown);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [filters.states?.join(","), filters.start, filters.end, contamination, minVolume]);

  if (loading && !data) return <div className="loading">Loading dashboard…</div>;
  if (err) return <div className="error-box">{err}</div>;
  if (!data) return null;

  const k = data.kpis;
  const pie = [
    { name: "Enrolments", value: data.workload.enrolments },
    { name: "Bio updates", value: data.workload.bio },
    { name: "Demo updates", value: data.workload.demo },
  ];
  const age = Object.entries(data.age_mix || {}).map(([name, value]) => ({ name, value }));

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Dashboard</h2>
          <p>Operational overview · same analytics engine as Streamlit</p>
        </div>
        <span className="badge">{k.forecast_model ? `Forecast · ${k.forecast_model}` : "Ready"}</span>
      </div>

      {meta?.llm && (
        <div className={`banner ${meta.llm.available ? "ok" : "warn"}`}>
          {meta.llm.available
            ? `LLM online · ${meta.llm.model}`
            : `LLM offline — AI analysis uses engine-only insights (${meta.llm.error || "n/a"})`}
        </div>
      )}

      <div className="card" style={{ marginBottom: "1rem" }}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <label>
            Contamination
            <input type="number" step="0.01" min="0.01" max="0.15" value={contamination} onChange={(e) => setContamination(Number(e.target.value))} />
          </label>
          <label>
            Min volume (cell)
            <input type="number" min="0" value={minVolume} onChange={(e) => setMinVolume(Number(e.target.value))} />
          </label>
          <button className="btn btn-ghost btn-sm" onClick={load}>
            Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-kpi" style={{ marginBottom: "1rem" }}>
        <KpiCard label="Total enrolments" value={k.total_enrolments} delta={`18+: ${fmt(k.adult_enrolments)}`} />
        <KpiCard label="Biometric updates" value={k.biometric_updates} />
        <KpiCard label="Demographic updates" value={k.demographic_updates} />
        <KpiCard label="Risk cells" value={k.anomaly_count} delta="IsolationForest" />
        <KpiCard
          label="Forecast Δ"
          value={`${k.forecast_growth_pct >= 0 ? "+" : ""}${k.forecast_growth_pct}%`}
          format={false}
          delta={k.holdout_smape != null ? `sMAPE ${k.holdout_smape}%` : k.holdout_mape != null ? `MAPE ${k.holdout_mape}%` : "30d"}
        />
      </div>

      <div className="card section-gap" style={{ marginBottom: "1rem" }}>
        <div className="card-head">
          <h3>AI analysis</h3>
          <button className="btn btn-primary btn-sm" onClick={load}>
            Refresh analysis
          </button>
        </div>
        <p className="muted">Insights & actions · numbers from the analytics engine</p>
        <MarkdownBlock text={insight} />
      </div>

      <div className="grid grid-2" style={{ marginBottom: "1rem" }}>
        <div className="card">
          <h3>Enrolment age mix</h3>
          <div style={{ height: 280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={age} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                  {age.map((_, i) => (
                    <Cell key={i} fill={AGE_COLORS[i % AGE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => fmt(v)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3>Workload mix</h3>
          <div style={{ height: 280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pie} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                  {pie.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => fmt(v)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <div className="card-head">
          <h3>Anomaly investigation (state × district)</h3>
          <button className="btn btn-primary btn-sm" onClick={() => navigate("/governance")}>
            Open Governance
          </button>
        </div>
        {k.anomaly_count === 0 ? (
          <div className="banner ok">No multi-feature outliers under current thresholds.</div>
        ) : (
          <>
            <div className="banner warn">
              {k.anomaly_count} cells flagged · contamination={contamination} · min_volume={minVolume}. Flags are
              statistical outliers, not verified fraud. Unit of analysis is composite (state, district).
            </div>
            <div className="grid grid-2">
              <div style={{ height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.risk_bars || []} layout="vertical" margin={{ left: 20 }}>
                    <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Bar dataKey="risk_score" fill="#dc2626" radius={[0, 6, 6, 0]} name="Risk" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div>
                <div className="table-wrap" style={{ maxHeight: 280 }}>
                  <table className="data">
                    <thead>
                      <tr>
                        <th>State</th>
                        <th>District</th>
                        <th>Vol</th>
                        <th>Risk</th>
                        <th>Reason</th>
                        <th>bio</th>
                        <th>demo</th>
                        <th>cv</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.top_risk || []).map((r, i) => (
                        <tr key={i}>
                          <td>{r.state}</td>
                          <td>{r.district}</td>
                          <td className="mono">{fmt(r.volume)}</td>
                          <td>
                            <span className="badge danger">{r.risk_score}</span>
                          </td>
                          <td>{r.reason}</td>
                          <td className="mono">{r.bio_ratio != null ? Number(r.bio_ratio).toFixed(2) : "—"}</td>
                          <td className="mono">{r.demo_ratio != null ? Number(r.demo_ratio).toFixed(2) : "—"}</td>
                          <td className="mono">{r.cv != null ? Number(r.cv).toFixed(2) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => setShowNote((s) => !s)}>
                  {showNote ? "Hide" : "Show"} top investigation note
                </button>
                {showNote && data.investigation_note && (
                  <p className="muted" style={{ marginTop: 8 }}>
                    {data.investigation_note}
                  </p>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <h3>30-day outlook · model {k.forecast_model}</h3>
        <div className="grid grid-2">
          <div style={{ height: 280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data.forecast || []}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={24} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => fmt(v)} />
                <Tooltip formatter={(v) => fmt(v)} />
                <Area type="monotone" dataKey="upper" stroke="none" fill="#dbeafe" fillOpacity={0.55} name="Upper" />
                <Area type="monotone" dataKey="lower" stroke="none" fill="#f8fafc" fillOpacity={1} name="Lower" />
                <Line type="monotone" dataKey="predicted" stroke="#2563eb" strokeWidth={2} dot={false} name="Point forecast" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="grid" style={{ gap: "0.75rem" }}>
            <KpiCard label="Peak" value={data.forecast_peak} />
            <KpiCard label="Floor" value={data.forecast_floor} />
            {k.holdout_smape != null && <KpiCard label="Holdout sMAPE" value={`${k.holdout_smape}%`} format={false} />}
            {data.bakeoff_caption && <p className="muted">Bake-off: {data.bakeoff_caption}</p>}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3>System logs</h3>
          <button className="btn btn-ghost btn-sm" onClick={() => setShowLogs((s) => !s)}>
            {showLogs ? "Hide" : "Show"}
          </button>
        </div>
        {showLogs && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Log</th>
                </tr>
              </thead>
              <tbody>
                {(data.logs || []).map((line, i) => (
                  <tr key={i}>
                    <td className="mono">{line}</td>
                  </tr>
                ))}
                {!data.logs?.length && (
                  <tr>
                    <td className="muted">No logs</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
