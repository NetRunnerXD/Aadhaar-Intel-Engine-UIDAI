import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, exportChartAsPNG, filterParams, fmt, triggerDownload } from "../api";
import AiPanel from "../components/AiPanel";
import KpiCard from "../components/KpiCard";

const tip = {
  contentStyle: {
    background: "rgba(255,255,255,0.96)",
    border: "1px solid rgba(203,213,225,0.8)",
    borderRadius: 12,
    boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
    fontSize: 12,
  },
};

export default function Forecast({ filters }) {
  const [horizon, setHorizon] = useState(30);
  const [model, setModel] = useState("Auto");
  const [shock, setShock] = useState(0);
  const [seriesState, setSeriesState] = useState("");
  const [data, setData] = useState(null);
  const [insight, setInsight] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const params = () => ({
    ...filterParams(filters),
    horizon,
    model,
    growth_factor: shock / 100,
    series_state: seriesState || undefined,
  });

  const load = async () => {
    setLoading(true);
    try {
      const d = await api.forecast(params());
      setData(d);
      setInsight("");
      setErr("");
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  const generateInsight = async () => {
    setInsight("Analyzing…");
    try {
      const ins = await api.insightForecast(params());
      setInsight(ins.markdown);
    } catch (e) {
      setInsight(String(e.message || e));
    }
  };

  useEffect(() => {
    load();
  }, [filters.states?.join(","), filters.start, filters.end, horizon, model, shock, seriesState]);

  if (loading && !data) return <div className="loading">Running forecast bake-off…</div>;
  if (err) return <div className="error-box">{err}</div>;
  if (!data) return null;

  const chartData = [
    ...(data.history || []).map((h) => ({ date: h.date, historical: h.volume })),
    ...(data.forecast || []).map((f) => ({
      date: f.date,
      predicted: f.predicted,
      lower: f.lower,
      upper: f.upper,
    })),
  ];
  const meta = data.meta || {};
  const roll = meta.rolling || {};
  const rp = data.resource_planning || {};

  return (
    <div className="page">
      <header className="page-header">
        <div className="page-header__title">
          <h2>Forecast</h2>
          <span className="badge">{data.model}</span>
        </div>
        <div className="page-controls">
          <label className="ctrl">
            Horizon
            <input type="number" min={7} max={90} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
          </label>
          <label className="ctrl">
            Model
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="Auto">Auto</option>
              {(data.candidates || []).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="ctrl">
            Shock %
            <input type="number" min={-50} max={50} value={shock} onChange={(e) => setShock(Number(e.target.value))} />
          </label>
          <label className="ctrl">
            Scope
            <select value={seriesState} onChange={(e) => setSeriesState(e.target.value)}>
              <option value="">National</option>
              {(data.state_options || []).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <section className="kpi-row kpi-row--6">
        <KpiCard label="Model" value={data.model} format={false} accent="blue" />
        <KpiCard label="Selection" value={String(meta.selection || "—").slice(0, 18)} format={false} accent="slate" />
        <KpiCard label="MASE" value={roll.rolling_mase ?? "—"} format={false} accent="violet" />
        <KpiCard label="sMAPE" value={roll.rolling_smape_pct != null ? `${roll.rolling_smape_pct}%` : "—"} format={false} accent="amber" />
        <KpiCard label="Band" value={meta.decision_band || "—"} format={false} accent="green" />
        <KpiCard label="Conformal q" value={meta.conformal_q ?? "—"} format={false} accent="slate" />
      </section>

      <section className="bento bento--forecast">
        <article className="panel">
          <div className="panel-head">
            <h3>Enrolment volume</h3>
            <button
              type="button"
              className="btn btn-ghost btn-sm chart-dl-btn"
              onClick={() => exportChartAsPNG("chart-forecast", "forecast.png")}
            >
              <Download size={14} />
            </button>
          </div>
          <div id="chart-forecast" className="chart chart--lg">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="fcBand" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} minTickGap={28} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "#64748b" }} tickFormatter={(v) => fmt(v)} axisLine={false} tickLine={false} width={56} />
                <Tooltip {...tip} formatter={(v) => fmt(v)} />
                <Legend verticalAlign="top" height={28} />
                <Area type="monotone" dataKey="upper" stroke="none" fill="url(#fcBand)" name="Upper" />
                <Area type="monotone" dataKey="lower" stroke="none" fill="#f8fafc" fillOpacity={1} name="Lower" />
                <Line type="monotone" dataKey="historical" stroke="#2563eb" strokeWidth={2} dot={false} name="Historical" />
                <Line
                  type="monotone"
                  dataKey="predicted"
                  stroke="#d97706"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  dot={false}
                  name="Forecast"
                />
                <Brush dataKey="date" height={28} stroke="#93c5fd" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </article>

        <AiPanel text={insight} onGenerate={generateInsight} emptyText="Summarize model choice, intervals, and outlook." />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h3>Model comparison</h3>
          {data.comparison?.[0] && (
            <span className="badge success">Best · {data.comparison[0].model}</span>
          )}
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Model</th>
                <th>MASE</th>
                <th>sMAPE %</th>
                <th>RMSE</th>
                <th>nRMSE</th>
                <th>Band</th>
                <th>Folds</th>
              </tr>
            </thead>
            <tbody>
              {(data.comparison || []).map((r, i) => (
                <tr key={i} className={r.model === data.model ? "row-active" : undefined}>
                  <td>{i + 1}</td>
                  <td>
                    <strong>{r.model}</strong>
                  </td>
                  <td className="mono">{r.mase}</td>
                  <td className="mono">{r.smape_pct}</td>
                  <td className="mono">{fmt(r.rmse)}</td>
                  <td className="mono">{r.nrmse}</td>
                  <td>
                    <span className="badge">{r.decision_band}</span>
                  </td>
                  <td>{r.n_folds}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="bento bento--2">
        <article className="panel">
          <div className="panel-head">
            <h3>Resource planning</h3>
          </div>
          <div className="kpi-row kpi-row--3">
            <KpiCard label={`Operators (${rp.per_operator || 40}/day)`} value={rp.operators_at_40} format={false} compact accent="blue" />
            <KpiCard label="Peak daily" value={rp.peak_daily} compact accent="amber" />
            <KpiCard label="Avg daily" value={rp.avg_daily} compact accent="green" />
          </div>
        </article>

        <article className="panel panel--export">
          <div className="panel-head">
            <h3>Export</h3>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => triggerDownload(api.exportForecast(params()), "forecast_data.csv")}
          >
            Forecast CSV
          </button>
        </article>
      </section>
    </div>
  );
}
