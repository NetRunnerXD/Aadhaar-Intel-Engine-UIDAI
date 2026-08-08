import { useEffect, useMemo, useState } from "react";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  MapPinned,
  Menu,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import { api } from "./api";
import Dashboard from "./pages/Dashboard";
import Analytics from "./pages/Analytics";
import Forecast from "./pages/Forecast";
import Geospatial from "./pages/Geospatial";
import Governance from "./pages/Governance";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/forecast", label: "Forecast", icon: TrendingUp },
  { to: "/map", label: "Geospatial Intel", icon: MapPinned },
  { to: "/governance", label: "Data Governance", icon: ShieldCheck },
];

export default function App() {
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState("");
  const [states, setStates] = useState([]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [stateQ, setStateQ] = useState("");
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebarCollapsed") === "1");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [qualityOpen, setQualityOpen] = useState(false);
  const navigate = useNavigate();

  const loadMeta = () =>
    api
      .meta()
      .then((m) => {
        setMeta(m);
        setError("");
        if (m.date_min && !start) setStart(m.date_min);
        if (m.date_max && !end) setEnd(m.date_max);
      })
      .catch((e) => setError(String(e.message || e)));

  useEffect(() => {
    loadMeta();
  }, []);

  useEffect(() => {
    localStorage.setItem("sidebarCollapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  const filters = useMemo(() => ({ states, start, end }), [states, start, end]);

  const allStates = meta?.states || [];
  const filteredStates = allStates.filter((s) => s.toLowerCase().includes(stateQ.toLowerCase()));

  const toggleState = (s) => {
    setStates((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  };

  const resetAll = async () => {
    setStates([]);
    if (meta) {
      setStart(meta.date_min || "");
      setEnd(meta.date_max || "");
    }
    try {
      await api.reload();
      await loadMeta();
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  return (
    <div className={`app-shell ${collapsed ? "collapsed" : ""}`}>
      {mobileOpen && <div className="mobile-overlay" onClick={() => setMobileOpen(false)} />}

      <aside className={`sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        <div className="sidebar-top">
          <div className="brand">
            <div className="brand-mark">AI</div>
            <div className="brand-text">
              <h1>Aadhaar Intel</h1>
              <p>Operational intelligence</p>
            </div>
          </div>
          <button
            type="button"
            className="icon-btn"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setCollapsed((c) => !c)}
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        <nav className="nav">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={label}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              <Icon size={18} />
              <span className="nav-label">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-section sidebar-filters-full">
          <h3>Global filters</h3>
          <div className="field">
            <label>Search states</label>
            <input
              className="state-search"
              value={stateQ}
              onChange={(e) => setStateQ(e.target.value)}
              placeholder="Filter list…"
            />
          </div>
          <div className="filter-actions">
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => setStates([...allStates])}>
              All
            </button>
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => setStates([])}>
              Clear
            </button>
          </div>
          <div className="field">
            <label>States / UTs ({states.length || "all"})</label>
            <div className="multi-select">
              {filteredStates.map((s) => (
                <label key={s}>
                  <input type="checkbox" checked={states.includes(s)} onChange={() => toggleState(s)} />
                  {s}
                </label>
              ))}
            </div>
          </div>
          <div className="field">
            <label>Start date</label>
            <input
              type="date"
              value={start}
              min={meta?.date_min}
              max={meta?.date_max}
              onChange={(e) => setStart(e.target.value)}
            />
          </div>
          <div className="field">
            <label>End date</label>
            <input
              type="date"
              value={end}
              min={meta?.date_min}
              max={meta?.date_max}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>
        </div>

        <div className="sidebar-foot">
          <div className="sidebar-filters-full">
            <div className="status-card">
              {meta ? (
                <>
                  <div>
                    Data as of: <strong>{meta.date_max || "n/a"}</strong>
                  </div>
                  <div>
                    Source: <strong>{meta.source}</strong> · MARTS_ONLY={String(meta.marts_only)}
                  </div>
                  <div>
                    E {meta.rows?.enrol?.toLocaleString()} · B {meta.rows?.bio?.toLocaleString()} · D{" "}
                    {meta.rows?.demo?.toLocaleString()}
                  </div>
                  <div className={meta.llm?.available ? "ok" : "warn"}>
                    LLM: {meta.llm?.available ? `online · ${meta.llm.model}` : "offline (engine analysis)"}
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-block"
                    style={{ marginTop: 8 }}
                    onClick={() => setQualityOpen(true)}
                  >
                    Data quality
                  </button>
                </>
              ) : (
                <div>Loading status…</div>
              )}
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-block"
            style={{ background: "#1e293b", color: "#e2e8f0", borderColor: "#334155" }}
            title="Reload data"
            onClick={resetAll}
          >
            <RefreshCw size={16} />
            <span className="nav-label">Reset / reload</span>
          </button>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="chips">
            <button
              type="button"
              className="btn btn-ghost btn-sm mobile-menu-btn"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={16} /> Menu
            </button>
            <span className="chip">
              States: <strong>{states.length ? states.length : "All"}</strong>
            </span>
            <span className="chip">
              Range:{" "}
              <strong>
                {start || "—"} → {end || "—"}
              </strong>
            </span>
            {meta?.llm && (
              <span className="chip">{meta.llm.available ? `LLM · ${meta.llm.model}` : "LLM offline"}</span>
            )}
          </div>
          <div className="chips">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate("/governance")}>
              <ShieldCheck size={14} /> Governance
            </button>
          </div>
        </div>

        <div className="content">
          {error && (
            <div className="error-box" style={{ marginBottom: "1rem" }}>
              {error}{" "}
              <button type="button" className="btn btn-primary" onClick={loadMeta}>
                Retry
              </button>
            </div>
          )}
          <Routes>
            <Route path="/" element={<Dashboard filters={filters} meta={meta} />} />
            <Route path="/analytics" element={<Analytics filters={filters} />} />
            <Route path="/forecast" element={<Forecast filters={filters} />} />
            <Route path="/map" element={<Geospatial filters={filters} />} />
            <Route path="/governance" element={<Governance onChanged={loadMeta} />} />
          </Routes>
        </div>
      </main>

      {qualityOpen && (
        <div className="drawer-backdrop" onClick={() => setQualityOpen(false)}>
          <div className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="card-head">
              <h3>Data quality</h3>
              <button type="button" className="icon-btn" onClick={() => setQualityOpen(false)}>
                <X size={16} />
              </button>
            </div>
            <p className="muted">Load report from the analytics engine (same as Streamlit sidebar).</p>
            <pre>{JSON.stringify(meta?.load_report || {}, null, 2)}</pre>
            {meta?.logs?.length > 0 && (
              <>
                <h4>Recent logs</h4>
                <pre>{meta.logs.join("\n")}</pre>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
