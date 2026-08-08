import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowUpRight,
  Brain,
  ChevronDown,
  ChevronUp,
  Download,
  Fingerprint,
  IdCard,
  RefreshCw,
  ShieldAlert,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  Area,
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, exportChartAsPNG, filterParams, fmt } from "../api";
import AiPanel from "../components/AiPanel";
import KpiCard from "../components/KpiCard";

const PIE_COLORS = ["#10b981", "#f59e0b", "#8b5cf6"];
const AGE_COLORS = ["#0ea5e9", "#6366f1", "#2563eb"];

const chartTooltip = {
  contentStyle: {
    background: "rgba(255,255,255,0.96)",
    border: "1px solid rgba(203,213,225,0.8)",
    borderRadius: 12,
    boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
    fontSize: 12,
    fontWeight: 500,
  },
  itemStyle: { color: "#334155" },
  labelStyle: { color: "#0f172a", fontWeight: 700, marginBottom: 4 },
};

function ChartDownload({ chartId, filename }) {
  return (
    <button
      type="button"
      className="btn btn-ghost btn-sm chart-dl-btn"
      onClick={() => exportChartAsPNG(chartId, filename)}
      title="Download chart"
    >
      <Download size={14} />
      <span>PNG</span>
    </button>
  );
}

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
      setInsight("");
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  const generateInsight = async () => {
    setInsight("Analyzing…");
    try {
      const p = { ...filterParams(filters), contamination, min_volume: minVolume };
      const ins = await api.insightDashboard(p);
      setInsight(ins.markdown);
    } catch (e) {
      setInsight(String(e.message || e));
    }
  };

  useEffect(() => {
    load();
  }, [filters.states?.join(","), filters.start, filters.end, contamination, minVolume]);

  if (loading && !data) {
    return (
      <div className="dash-loading">
        <div className="dash-loading__pulse" />
        <p>Loading dashboard…</p>
      </div>
    );
  }
  if (err) return <div className="error-box">{err}</div>;
  if (!data) return null;

  const k = data.kpis;
  const pie = [
    { name: "Enrolments", value: data.workload.enrolments },
    { name: "Bio updates", value: data.workload.bio },
    { name: "Demo updates", value: data.workload.demo },
  ];
  const age = Object.entries(data.age_mix || {}).map(([name, value]) => ({ name, value }));
  const growthPositive = (k.forecast_growth_pct ?? 0) >= 0;
  const hasRisk = k.anomaly_count > 0;

  return (
    <div className="dash">
      {/* ── Hero ── */}
      <header className="dash-hero">
        <div className="dash-hero__main">
          <h1 className="dash-hero__title">Dashboard</h1>
        </div>

        <div className="dash-hero__aside">
          <div className="dash-status-row">
            <span className={`dash-status ${meta?.llm?.available ? "is-ok" : "is-warn"}`}>
              <Brain size={14} />
              {meta?.llm?.available
                ? `LLM · ${meta.llm.model || "online"}`
                : "LLM offline · engine-only insights"}
            </span>
            <span className="dash-status is-info">
              <TrendingUp size={14} />
              {k.forecast_model ? `Forecast · ${k.forecast_model}` : "Ready"}
            </span>
          </div>

          <div className="dash-controls">
            <label className="dash-field">
              <span>Contamination</span>
              <input
                type="number"
                step="0.01"
                min="0.01"
                max="0.15"
                value={contamination}
                onChange={(e) => setContamination(Number(e.target.value))}
              />
            </label>
            <label className="dash-field">
              <span>Min volume</span>
              <input
                type="number"
                min="0"
                value={minVolume}
                onChange={(e) => setMinVolume(Number(e.target.value))}
              />
            </label>
            <button type="button" className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
              <RefreshCw size={14} className={loading ? "spin" : ""} />
              Refresh
            </button>
          </div>
        </div>
      </header>

      {/* ── KPI strip ── */}
      <section className="dash-kpi-strip" aria-label="Key metrics">
        <KpiCard
          label="Total enrolments"
          value={k.total_enrolments}
          delta={`18+: ${fmt(k.adult_enrolments)}`}
          icon={<Users size={18} />}
          accent="blue"
        />
        <KpiCard
          label="Biometric updates"
          value={k.biometric_updates}
          icon={<Fingerprint size={18} />}
          accent="green"
        />
        <KpiCard
          label="Demographic updates"
          value={k.demographic_updates}
          icon={<IdCard size={18} />}
          accent="violet"
        />
        <KpiCard
          label="Risk cells"
          value={k.anomaly_count}
          delta="IsolationForest"
          icon={<ShieldAlert size={18} />}
          accent={hasRisk ? "rose" : "slate"}
        />
        <KpiCard
          label="Forecast Δ"
          value={`${growthPositive ? "+" : ""}${k.forecast_growth_pct}%`}
          format={false}
          delta={
            k.holdout_smape != null
              ? `sMAPE ${k.holdout_smape}%`
              : k.holdout_mape != null
                ? `MAPE ${k.holdout_mape}%`
                : "30-day horizon"
          }
          icon={<TrendingUp size={18} />}
          accent={growthPositive ? "amber" : "rose"}
        />
      </section>

      {/* ── Mix charts ── */}
      <section className="dash-bento dash-bento--mix">
        <article className="dash-panel">
          <div className="dash-panel__head">
            <h2>Enrolment age mix</h2>
            <ChartDownload chartId="chart-age-mix" filename="age_mix.png" />
          </div>
          <div id="chart-age-mix" className="dash-chart dash-chart--pie">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={age}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={62}
                  outerRadius={98}
                  paddingAngle={3}
                  stroke="none"
                >
                  {age.map((_, i) => (
                    <Cell key={i} fill={AGE_COLORS[i % AGE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip {...chartTooltip} formatter={(v) => fmt(v)} />
                <Legend verticalAlign="bottom" height={36} iconType="circle" />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="dash-panel">
          <div className="dash-panel__head">
            <h2>Workload mix</h2>
            <ChartDownload chartId="chart-workload-mix" filename="workload_mix.png" />
          </div>
          <div id="chart-workload-mix" className="dash-chart dash-chart--pie">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pie}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={62}
                  outerRadius={98}
                  paddingAngle={3}
                  stroke="none"
                >
                  {pie.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip {...chartTooltip} formatter={(v) => fmt(v)} />
                <Legend verticalAlign="bottom" height={36} iconType="circle" />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      {/* ── Anomaly investigation ── */}
      <section className="dash-panel dash-panel--risk">
        <div className="dash-panel__head">
          <div className="dash-panel__title-row">
            <div className={`dash-risk-icon ${hasRisk ? "is-hot" : "is-calm"}`}>
              <AlertTriangle size={18} />
            </div>
            <h2>Anomaly investigation</h2>
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => navigate("/governance")}>
            Open Governance
            <ArrowUpRight size={14} />
          </button>
        </div>

        {!hasRisk ? (
          <div className="dash-empty-ok">
            <ShieldAlert size={22} />
            <div>
              <strong>No multi-feature outliers</strong>
              <p>Nothing flagged under current contamination and volume thresholds.</p>
            </div>
          </div>
        ) : (
          <>
            <div className="dash-alert">
              <strong>{k.anomaly_count} cells flagged</strong>
              <span>
                contamination={contamination} · min_volume={minVolume}. Statistical outliers only — not verified
                fraud. Unit of analysis is composite (state, district).
              </span>
            </div>

            <div className="dash-bento dash-bento--risk">
              <div id="chart-anomaly" className="dash-chart dash-chart--bar">
                <div className="dash-chart__float-actions">
                  <ChartDownload chartId="chart-anomaly" filename="anomaly.png" />
                </div>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.risk_bars || []} layout="vertical" margin={{ left: 8, right: 12, top: 8, bottom: 8 }}>
                    <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
                    <YAxis
                      type="category"
                      dataKey="label"
                      width={118}
                      tick={{ fontSize: 10, fill: "#475569" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip {...chartTooltip} />
                    <Bar dataKey="risk_score" fill="#ef4444" radius={[0, 8, 8, 0]} name="Risk score" maxBarSize={22} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="dash-risk-side">
                <div className="table-wrap dash-table-wrap">
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
                          <td className="dash-reason">{r.reason}</td>
                          <td className="mono">{r.bio_ratio != null ? Number(r.bio_ratio).toFixed(2) : "—"}</td>
                          <td className="mono">{r.demo_ratio != null ? Number(r.demo_ratio).toFixed(2) : "—"}</td>
                          <td className="mono">{r.cv != null ? Number(r.cv).toFixed(2) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <button
                  type="button"
                  className="btn btn-ghost btn-sm dash-toggle"
                  onClick={() => setShowNote((s) => !s)}
                >
                  {showNote ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  {showNote ? "Hide" : "Show"} investigation note
                </button>
                {showNote && data.investigation_note && (
                  <p className="dash-note">{data.investigation_note}</p>
                )}
              </div>
            </div>
          </>
        )}
      </section>

      {/* ── Forecast + AI ── */}
      <section className="dash-bento dash-bento--bottom">
        <article className="dash-panel dash-panel--forecast">
          <div className="dash-panel__head">
            <h2>30-day outlook · {k.forecast_model || "n/a"}</h2>
            <ChartDownload chartId="chart-outlook" filename="outlook.png" />
          </div>

          <div id="chart-outlook" className="dash-chart dash-chart--forecast">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data.forecast || []} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="forecastBand" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} minTickGap={28} axisLine={false} tickLine={false} />
                <YAxis
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  tickFormatter={(v) => fmt(v)}
                  axisLine={false}
                  tickLine={false}
                  width={56}
                />
                <Tooltip {...chartTooltip} formatter={(v) => fmt(v)} />
                <Area type="monotone" dataKey="upper" stroke="none" fill="url(#forecastBand)" name="Upper" />
                <Area type="monotone" dataKey="lower" stroke="none" fill="#f8fafc" fillOpacity={1} name="Lower" />
                <Line type="monotone" dataKey="predicted" stroke="#2563eb" strokeWidth={2.5} dot={false} name="Point forecast" />
                <Brush dataKey="date" height={28} stroke="#93c5fd" travellerWidth={8} />
                <Legend verticalAlign="top" height={28} iconType="plainline" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="dash-forecast-meta">
            <KpiCard label="Peak" value={data.forecast_peak} compact accent="blue" />
            <KpiCard label="Floor" value={data.forecast_floor} compact accent="slate" />
            {k.holdout_smape != null && (
              <KpiCard label="Holdout sMAPE" value={`${k.holdout_smape}%`} format={false} compact accent="amber" />
            )}
          </div>
          {data.bakeoff_caption && <p className="dash-bakeoff">Bake-off: {data.bakeoff_caption}</p>}
        </article>

        <AiPanel
          text={insight}
          onGenerate={generateInsight}
          emptyText="Summarize KPIs, risk cells, and forecast trajectory."
        />
      </section>

      {/* ── System logs ── */}
      <section className="dash-panel dash-panel--logs">
        <button
          type="button"
          className="dash-logs-toggle"
          onClick={() => setShowLogs((s) => !s)}
          aria-expanded={showLogs}
        >
          <h2>System logs</h2>
          {showLogs ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>

        {showLogs && (
          <div className="table-wrap dash-logs-table">
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
      </section>
    </div>
  );
}
