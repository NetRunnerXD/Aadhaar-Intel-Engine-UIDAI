import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
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

const MASE_COLOR = "#818cf8";
const MASE_SELECTED = "#4f46e5";
const SMAPE_COLOR = "#fbbf24";
const SMAPE_SELECTED = "#d97706";
const BASELINE_MODELS = new Set(["SeasonalNaive", "MovingAverage"]);

const PLOT_VIEWS = [
  { id: "rank", label: "MASE rank" },
  { id: "dual", label: "MASE + sMAPE" },
  { id: "scatter", label: "Error map" },
  { id: "gate", label: "Baseline gate" },
];

function buildComparisonRows(comparison, selectedModel) {
  return (comparison || []).map((r, i) => ({
    model: r.model,
    rank: i + 1,
    mase: r.mase != null ? Number(r.mase) : null,
    smape_pct: r.smape_pct != null ? Number(r.smape_pct) : null,
    rmse: r.rmse != null ? Number(r.rmse) : null,
    nrmse: r.nrmse != null ? Number(r.nrmse) : null,
    selected: r.model === selectedModel,
    baseline: BASELINE_MODELS.has(r.model),
    decision_band: r.decision_band,
    n_folds: r.n_folds,
  }));
}

function ComparePlot({ view, rows, selectedModel }) {
  if (!rows.length) {
    return <div className="muted fc-plot-empty">No bake-off results for this scope.</div>;
  }

  const byMase = [...rows].filter((r) => r.mase != null).sort((a, b) => a.mase - b.mase);
  const baselineMases = rows.filter((r) => r.baseline && r.mase != null).map((r) => r.mase);
  const bestBaselineMase = baselineMases.length ? Math.min(...baselineMases) : null;
  const sn = rows.find((r) => r.model === "SeasonalNaive");
  const ma = rows.find((r) => r.model === "MovingAverage");

  if (view === "rank") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={byMase} layout="vertical" margin={{ top: 8, right: 24, left: 4, bottom: 8 }}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
          <YAxis
            type="category"
            dataKey="model"
            width={118}
            tick={{ fontSize: 11, fill: "#475569", fontWeight: 600 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            {...tip}
            formatter={(v) => [v == null ? "—" : Number(v).toFixed(4), "MASE"]}
            labelFormatter={(label, payload) => {
              const r = payload?.[0]?.payload;
              return `${label}${r?.selected ? " · selected" : ""}${r?.baseline ? " · baseline" : ""}`;
            }}
          />
          {bestBaselineMase != null && (
            <ReferenceLine
              x={bestBaselineMase}
              stroke="#94a3b8"
              strokeDasharray="4 4"
              label={{ value: "best baseline", fill: "#94a3b8", fontSize: 10, position: "insideTopRight" }}
            />
          )}
          <Bar dataKey="mase" name="MASE" radius={[0, 8, 8, 0]} maxBarSize={26}>
            {byMase.map((entry) => (
              <Cell
                key={entry.model}
                fill={entry.selected ? MASE_SELECTED : entry.baseline ? "#94a3b8" : MASE_COLOR}
                fillOpacity={entry.selected ? 1 : 0.75}
                stroke={entry.selected ? "#312e81" : "none"}
                strokeWidth={entry.selected ? 1.5 : 0}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (view === "dual") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 12, right: 12, left: 0, bottom: 8 }} barGap={6} barCategoryGap="28%">
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="model" tick={{ fontSize: 11, fill: "#475569", fontWeight: 600 }} axisLine={false} tickLine={false} interval={0} />
          <YAxis
            yAxisId="mase"
            orientation="left"
            tick={{ fontSize: 11, fill: "#64748b" }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <YAxis
            yAxisId="smape"
            orientation="right"
            tick={{ fontSize: 11, fill: "#64748b" }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            {...tip}
            formatter={(v, name) => {
              if (v == null || Number.isNaN(v)) return ["—", name];
              if (name === "MASE") return [Number(v).toFixed(4), name];
              return [`${Number(v).toFixed(1)}%`, name];
            }}
          />
          <Legend verticalAlign="top" height={28} />
          <Bar yAxisId="mase" dataKey="mase" name="MASE" radius={[6, 6, 0, 0]} maxBarSize={34}>
            {rows.map((entry) => (
              <Cell
                key={`m-${entry.model}`}
                fill={entry.selected ? MASE_SELECTED : MASE_COLOR}
                fillOpacity={entry.selected ? 1 : 0.7}
                stroke={entry.selected ? "#312e81" : "none"}
                strokeWidth={entry.selected ? 1.5 : 0}
              />
            ))}
          </Bar>
          <Bar yAxisId="smape" dataKey="smape_pct" name="sMAPE %" radius={[6, 6, 0, 0]} maxBarSize={34}>
            {rows.map((entry) => (
              <Cell
                key={`s-${entry.model}`}
                fill={entry.selected ? SMAPE_SELECTED : SMAPE_COLOR}
                fillOpacity={entry.selected ? 1 : 0.7}
                stroke={entry.selected ? "#92400e" : "none"}
                strokeWidth={entry.selected ? 1.5 : 0}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (view === "scatter") {
    const scatterData = rows.filter((r) => r.mase != null && r.smape_pct != null);
    return (
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 16, right: 20, left: 8, bottom: 12 }}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="mase"
            name="MASE"
            tick={{ fontSize: 11, fill: "#64748b" }}
            axisLine={false}
            tickLine={false}
            label={{ value: "MASE", position: "insideBottom", offset: -4, fill: "#64748b", fontSize: 11 }}
          />
          <YAxis
            type="number"
            dataKey="smape_pct"
            name="sMAPE"
            tick={{ fontSize: 11, fill: "#64748b" }}
            axisLine={false}
            tickLine={false}
            width={48}
            label={{ value: "sMAPE %", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 11 }}
          />
          <ZAxis range={[80, 280]} />
          <Tooltip
            {...tip}
            cursor={{ strokeDasharray: "3 3" }}
            formatter={(v, name) => {
              if (name === "MASE") return [Number(v).toFixed(4), name];
              if (name === "sMAPE") return [`${Number(v).toFixed(1)}%`, name];
              return [v, name];
            }}
            labelFormatter={(_, payload) => payload?.[0]?.payload?.model || ""}
          />
          {sn?.mase != null && <ReferenceLine x={sn.mase} stroke="#94a3b8" strokeDasharray="4 4" />}
          {ma?.mase != null && <ReferenceLine x={ma.mase} stroke="#cbd5e1" strokeDasharray="4 4" />}
          <Scatter name="Models" data={scatterData} shape="circle">
            {scatterData.map((entry) => (
              <Cell
                key={entry.model}
                fill={entry.selected ? MASE_SELECTED : entry.baseline ? "#94a3b8" : "#38bdf8"}
                stroke={entry.selected ? "#1e1b4b" : "#fff"}
                strokeWidth={entry.selected ? 2 : 1}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  // gate: gap vs baselines (negative = beats baseline)
  const gateRows = rows
    .filter((r) => !r.baseline && r.mase != null && bestBaselineMase != null)
    .map((r) => ({
      ...r,
      gap_vs_baseline: Number((r.mase - bestBaselineMase).toFixed(4)),
      beats: r.mase < bestBaselineMase,
    }));
  // also show baselines as zero reference context
  const gateChart = [
    ...gateRows,
    ...rows
      .filter((r) => r.baseline && r.mase != null)
      .map((r) => ({
        ...r,
        gap_vs_baseline: Number((r.mase - bestBaselineMase).toFixed(4)),
        beats: false,
      })),
  ].sort((a, b) => a.gap_vs_baseline - b.gap_vs_baseline);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={gateChart} layout="vertical" margin={{ top: 8, right: 24, left: 4, bottom: 8 }}>
        <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} />
        <YAxis
          type="category"
          dataKey="model"
          width={118}
          tick={{ fontSize: 11, fill: "#475569", fontWeight: 600 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          {...tip}
          formatter={(v) => [v == null ? "—" : Number(v).toFixed(4), "Δ MASE vs best baseline"]}
          labelFormatter={(label, payload) => {
            const r = payload?.[0]?.payload;
            if (!r) return label;
            if (r.baseline) return `${label} · baseline`;
            return `${label}${r.selected ? " · selected" : ""}${r.beats ? " · beats gate" : " · blocked"}`;
          }}
        />
        <ReferenceLine x={0} stroke="#0f172a" strokeWidth={1.2} />
        <Bar dataKey="gap_vs_baseline" name="Δ MASE" radius={[0, 8, 8, 0]} maxBarSize={26}>
          {gateChart.map((entry) => {
            let fill = "#94a3b8";
            if (!entry.baseline) fill = entry.beats ? "#10b981" : "#f43f5e";
            if (entry.selected) fill = entry.beats ? "#059669" : "#e11d48";
            return (
              <Cell
                key={entry.model}
                fill={fill}
                stroke={entry.selected ? "#0f172a" : "none"}
                strokeWidth={entry.selected ? 1.5 : 0}
              />
            );
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function Forecast({ filters }) {
  const [horizon, setHorizon] = useState(30);
  const [model, setModel] = useState("Auto");
  const [shock, setShock] = useState(0);
  const [seriesState, setSeriesState] = useState("");
  const [data, setData] = useState(null);
  const [insight, setInsight] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [plotView, setPlotView] = useState("rank");

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
  const comparisonChart = buildComparisonRows(data.comparison, data.model);
  const pngName = `model_comparison_${plotView}.png`;

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
        <div className="panel-head panel-head--wrap">
          <h3>Model selection</h3>
          <div className="panel-head-actions">
            <div className="mix-tabs" role="tablist" aria-label="Comparison views">
              {PLOT_VIEWS.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  role="tab"
                  aria-selected={plotView === v.id}
                  className={`mix-tab ${plotView === v.id ? "active" : ""}`}
                  onClick={() => setPlotView(v.id)}
                >
                  {v.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm chart-dl-btn"
              onClick={() => exportChartAsPNG("chart-model-compare", pngName)}
              disabled={!comparisonChart.length}
            >
              <Download size={14} />
            </button>
          </div>
        </div>
        <div id="chart-model-compare" className="chart chart--lg fc-selection-chart">
          <ComparePlot view={plotView} rows={comparisonChart} selectedModel={data.model} />
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h3>Model comparison</h3>
          {data.comparison?.[0] && <span className="badge success">Best · {data.comparison[0].model}</span>}
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
