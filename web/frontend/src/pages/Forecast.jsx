import { useEffect, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, filterParams, fmt, triggerDownload } from "../api";
import KpiCard from "../components/KpiCard";
import MarkdownBlock from "../components/MarkdownBlock";

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
      const ins = await api.insightForecast(params());
      setInsight(ins.markdown);
      setErr("");
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
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
    <>
      <div className="page-header">
        <div>
          <h2>Forecast</h2>
          <p>
            Top-4 bake-off · MASE primary · beat SeasonalNaive & MovingAverage · split conformal intervals
          </p>
        </div>
        <span className="badge">{data.model}</span>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <label>
            Horizon (days)
            <input type="number" min={7} max={90} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
          </label>
          <label>
            Model
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="Auto">Auto (beat baselines)</option>
              {(data.candidates || []).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label>
            Scenario shock %
            <input type="number" min={-50} max={50} value={shock} onChange={(e) => setShock(Number(e.target.value))} />
          </label>
          <label>
            Series scope
            <select value={seriesState} onChange={(e) => setSeriesState(e.target.value)}>
              <option value="">(National)</option>
              {(data.state_options || []).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-ghost" onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <h3>Model comparison (rolling-origin CV)</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Model</th>
                <th>MASE ★</th>
                <th>sMAPE %</th>
                <th>RMSE</th>
                <th>nRMSE</th>
                <th>Band</th>
                <th>Folds</th>
              </tr>
            </thead>
            <tbody>
              {(data.comparison || []).map((r, i) => (
                <tr key={i} style={r.model === data.model ? { background: "#eff6ff" } : undefined}>
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
        {data.comparison?.[0] && (
          <p className="muted" style={{ marginTop: 8 }}>
            Best by {data.comparison[0].primary_metric || "mase"}: <strong>{data.comparison[0].model}</strong>
          </p>
        )}
      </div>

      <div className="grid grid-kpi" style={{ marginBottom: "1rem" }}>
        <KpiCard label="Model" value={data.model} format={false} />
        <KpiCard label="Selection" value={String(meta.selection || "—").slice(0, 18)} format={false} />
        <KpiCard label="MASE" value={roll.rolling_mase ?? "—"} format={false} />
        <KpiCard label="sMAPE" value={roll.rolling_smape_pct != null ? `${roll.rolling_smape_pct}%` : "—"} format={false} />
        <KpiCard label="Band" value={meta.decision_band || "—"} format={false} />
        <KpiCard label="Conformal q" value={meta.conformal_q ?? "—"} format={false} />
      </div>
      <p className="muted" style={{ marginBottom: "1rem" }}>
        Primary: <strong>{meta.primary_metric || "mase"}</strong> · Intervals: {meta.interval_method || "n/a"}{" "}
        (α={meta.conformal_alpha ?? "n/a"}) · Scope: {seriesState || "National"}
      </p>

      <div className="grid grid-2" style={{ marginBottom: "1rem" }}>
        <div className="card">
          <h3>Enrolment volume forecast</h3>
          <div style={{ height: 360 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={28} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => fmt(v)} />
                <Tooltip formatter={(v) => fmt(v)} />
                <Legend />
                <Area type="monotone" dataKey="upper" stroke="none" fill="#dbeafe" fillOpacity={0.5} name="Upper" />
                <Area type="monotone" dataKey="lower" stroke="none" fill="#fff" fillOpacity={1} name="Lower" />
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
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <div className="card-head">
            <h3>AI analysis</h3>
            <button className="btn btn-primary btn-sm" onClick={load}>
              Refresh
            </button>
          </div>
          <MarkdownBlock text={insight} />
        </div>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <h3>Resource planning (illustrative)</h3>
        <div className="grid grid-3">
          <KpiCard label={`Operators (${rp.per_operator || 40}/day)`} value={rp.operators_at_40} format={false} />
          <KpiCard label="Peak daily" value={rp.peak_daily} />
          <KpiCard label="Avg daily" value={rp.avg_daily} />
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          Constants are configurable assumptions, not certified capacity standards.
        </p>
      </div>

      <div className="card">
        <h3>Methods & download</h3>
        <ul className="muted">
          <li>
            <strong>MovingAverage</strong> — 7-day level × DOW shape
          </li>
          <li>
            <strong>Drift</strong> — damped first→last trend
          </li>
          <li>
            <strong>Ensemble</strong> — median of MA + Drift + SeasonalNaive
          </li>
          <li>
            <strong>SeasonalNaive</strong> — lag-7 recursive (MASE scale)
          </li>
          <li>
            <strong>Auto</strong> — best MASE only if it beats SeasonalNaive and MA
          </li>
          <li>
            <strong>Intervals</strong> — split conformal absolute residual quantile
          </li>
        </ul>
        <button
          className="btn btn-primary"
          onClick={() => triggerDownload(api.exportForecast(params()), "forecast_data.csv")}
        >
          Download forecast CSV
        </button>
      </div>
    </>
  );
}
