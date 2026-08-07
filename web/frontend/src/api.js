const BASE = "";

function qs(params = {}) {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    if (Array.isArray(v)) {
      if (v.length) u.set(k, v.join(","));
    } else {
      u.set(k, String(v));
    }
  });
  const s = u.toString();
  return s ? `?${s}` : "";
}

async function get(path, params) {
  const res = await fetch(`${BASE}${path}${qs(params)}`);
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

function downloadUrl(path, params) {
  return `${BASE}${path}${qs(params)}`;
}

export const api = {
  health: () => get("/api/health"),
  meta: () => get("/api/meta"),
  reload: () => post("/api/reload", {}),
  dashboard: (f) => get("/api/dashboard", f),
  analytics: (f) => get("/api/analytics", f),
  forecast: (f) => get("/api/forecast", f),
  map: (f) => get("/api/map", f),
  geojson: () => get("/api/geojson"),
  governance: () => get("/api/governance"),
  scan: (scope) => get("/api/governance/scan", { scope }),
  applyGovernance: (items) => post("/api/governance/apply", { items }),
  revertGovernance: (ids) => post("/api/governance/revert", { ids }),
  importPack: (pack) => post("/api/governance/import-pack", pack),
  insightDashboard: (f) => get("/api/insights/dashboard", f),
  insightForecast: (f) => get("/api/insights/forecast", f),
  insightGovernance: (scope) => get("/api/insights/governance", { scope }),
  exportAnalytics: (kind, f) => downloadUrl(`/api/analytics/export/${kind}`, f),
  exportForecast: (f) => downloadUrl("/api/forecast/export", f),
  exportMap: (kind, f) => downloadUrl(`/api/map/export/${kind}`, f),
  exportGovPack: () => downloadUrl("/api/governance/export-pack"),
  exportAudit: () => downloadUrl("/api/governance/export-audit"),
};

export function filterParams(filters) {
  return {
    states: filters.states?.length ? filters.states.join(",") : undefined,
    start: filters.start || undefined,
    end: filters.end || undefined,
  };
}

export function fmt(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return Number.isInteger(n)
    ? n.toLocaleString()
    : Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function triggerDownload(url, filename) {
  const a = document.createElement("a");
  a.href = url;
  if (filename) a.download = filename;
  a.target = "_blank";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
