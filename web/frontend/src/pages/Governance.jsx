import { useEffect, useMemo, useState } from "react";
import { api, fmt, triggerDownload } from "../api";
import AiPanel from "../components/AiPanel";
import KpiCard from "../components/KpiCard";

export default function Governance({ onChanged }) {
  const [tab, setTab] = useState("fix");
  const [scope, setScope] = useState("states");
  const [issues, setIssues] = useState([]);
  const [actions, setActions] = useState({});
  const [status, setStatus] = useState(null);
  const [insight, setInsight] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [confirmAll, setConfirmAll] = useState(false);
  const [selIds, setSelIds] = useState([]);
  const [auditStart, setAuditStart] = useState("");
  const [auditEnd, setAuditEnd] = useState("");
  const [auditScopes, setAuditScopes] = useState(["State", "District"]);
  const [page, setPage] = useState(0);
  const pageSize = 10;

  const refreshStatus = () => api.governance().then(setStatus).catch(() => {});

  useEffect(() => {
    refreshStatus();
  }, []);

  const scan = async () => {
    setLoading(true);
    setMsg("");
    setPage(0);
    try {
      const r = await api.scan(scope);
      const list = r.issues || [];
      setIssues(list);
      const init = {};
      list.forEach((row, i) => {
        init[i] = {
          act: Number(row.Conf) > 0.85 ? "Merge" : "Ignore",
          target: row.Fix,
        };
      });
      setActions(init);
      setMsg(`Found ${list.length} pending issues`);
      setInsight("");
    } catch (e) {
      setMsg(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  const applyItems = async (items, label) => {
    setLoading(true);
    try {
      const r = await api.applyGovernance(items);
      setMsg(`${label}: applied ${r.applied}`);
      setConfirmAll(false);
      await scan();
      await refreshStatus();
      onChanged?.();
    } catch (e) {
      setMsg(String(e.message || e));
    } finally {
      setLoading(false);
    }
  };

  const high = issues.filter((r) => Number(r.Conf) > 0.9);
  const pageIssues = issues.slice(page * pageSize, page * pageSize + pageSize);

  const official = status?.official_states || [];
  const districtOptions = useMemo(() => {
    const s = new Set(issues.map((i) => i.Fix).filter(Boolean));
    return [...s].sort();
  }, [issues]);

  const mergeAll = () =>
    applyItems(
      issues.map((row) => ({
        scope: scope === "states" ? "State" : "District",
        original: row.Suspect,
        target: row.Fix,
        action: "Merge",
      })),
      "Merge all"
    );

  const autoFixHigh = () =>
    applyItems(
      high.map((row) => ({
        scope: scope === "states" ? "State" : "District",
        original: row.Suspect,
        target: row.Fix,
        action: "Merge",
      })),
      "Auto-Fix high conf"
    );

  const commitPage = () => {
    const items = [];
    pageIssues.forEach((row, localIdx) => {
      const idx = page * pageSize + localIdx;
      const a = actions[idx] || { act: "Ignore", target: row.Fix };
      if (a.act === "Ignore") return;
      items.push({
        scope: scope === "states" ? "State" : "District",
        original: row.Suspect,
        target: a.target,
        action: a.act,
      });
    });
    if (!items.length) {
      setMsg("No changes on this page");
      return;
    }
    return applyItems(items, "Commit page");
  };

  const filteredAudit = useMemo(() => {
    let rows = status?.audit || [];
    if (auditStart) {
      rows = rows.filter((r) => String(r.Timestamp).slice(0, 10) >= auditStart);
    }
    if (auditEnd) {
      rows = rows.filter((r) => String(r.Timestamp).slice(0, 10) <= auditEnd);
    }
    if (auditScopes.length) {
      rows = rows.filter((r) => auditScopes.includes(r.Scope));
    }
    return [...rows].reverse();
  }, [status, auditStart, auditEnd, auditScopes]);

  const toggleSel = (id) => {
    setSelIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const importFile = async (file) => {
    if (!file) return;
    try {
      const text = await file.text();
      const pack = JSON.parse(text);
      await api.importPack(pack);
      setMsg("Pack imported");
      await refreshStatus();
      onChanged?.();
    } catch (e) {
      setMsg(`Import failed: ${e.message}`);
    }
  };

  const generateInsight = async () => {
    setInsight("Analyzing…");
    try {
      const r = await api.insightGovernance(scope);
      setInsight(r.markdown);
    } catch (e) {
      setInsight(String(e.message || e));
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <h2>Data Governance</h2>
      </header>

      <section className="kpi-row kpi-row--4">
        <KpiCard label="State merges" value={status ? Object.keys(status.state_patches || {}).length : "—"} format={false} accent="blue" />
        <KpiCard label="District merges" value={status ? Object.keys(status.district_patches || {}).length : "—"} format={false} accent="violet" />
        <KpiCard label="State deletions" value={status?.state_deletions?.length ?? "—"} format={false} accent="rose" />
        <KpiCard label="District deletions" value={status?.district_deletions?.length ?? "—"} format={false} accent="amber" />
      </section>

      <div className="tabs">
        <button type="button" className={tab === "fix" ? "active" : ""} onClick={() => setTab("fix")}>
          Fix anomalies
        </button>
        <button type="button" className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>
          Audit & revert
        </button>
        <button type="button" className={tab === "io" ? "active" : ""} onClick={() => setTab("io")}>
          Import / export
        </button>
      </div>

      {tab === "fix" && (
        <div className="page-stack">
          <AiPanel text={insight} onGenerate={generateInsight} emptyText="Generate governance insights for residual name issues." />

          <section className="panel">
            <div className="panel-head panel-head--wrap">
              <div className="page-controls" style={{ margin: 0 }}>
                <label className="ctrl">
                  Scope
                  <select value={scope} onChange={(e) => setScope(e.target.value)}>
                    <option value="states">States</option>
                    <option value="districts">Districts</option>
                  </select>
                </label>
                <button type="button" className="btn btn-primary btn-sm" onClick={scan} disabled={loading}>
                  {loading ? "Working…" : "Start scan"}
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={autoFixHigh} disabled={!high.length || loading}>
                  Auto-fix high ({high.length})
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmAll(true)} disabled={!issues.length || loading}>
                  Merge all ({issues.length})
                </button>
                <button type="button" className="btn btn-primary btn-sm" onClick={commitPage} disabled={!pageIssues.length || loading}>
                  Commit page
                </button>
              </div>
            </div>

            {confirmAll && (
              <div className="banner warn">
                Merge all applies the suggested target for all {issues.length} pending {scope}.
                <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                  <button type="button" className="btn btn-primary btn-sm" onClick={mergeAll}>
                    Confirm
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmAll(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {msg && <p className="panel-meta">{msg}</p>}

            <div className="issue-list">
              {pageIssues.map((row, localIdx) => {
                const idx = page * pageSize + localIdx;
                const a = actions[idx] || { act: "Ignore", target: row.Fix };
                const options = scope === "states" ? official : districtOptions.length ? districtOptions : [row.Fix];
                return (
                  <div className="issue-card" key={idx}>
                    <div className="issue-card__main">
                      <strong>{row.Suspect}</strong>
                      <div className="muted">
                        conf {(Number(row.Conf) * 100).toFixed(0)}% · vol {fmt(row.Suspect_Vol)}
                        {row.PIN_Overlap != null && <> · PIN {row.PIN_Overlap ? "match" : "no overlap"}</>}
                        {row.Suspect_PINs && <> · PINs {row.Suspect_PINs}</>}
                      </div>
                      <div className="muted">→ {row.Fix}</div>
                    </div>
                    <div className="issue-card__actions">
                      <select
                        value={a.act}
                        onChange={(e) => setActions((prev) => ({ ...prev, [idx]: { ...a, act: e.target.value } }))}
                      >
                        <option>Merge</option>
                        <option>Delete</option>
                        <option>Ignore</option>
                      </select>
                      {a.act === "Merge" && (
                        <select
                          value={a.target || row.Fix}
                          onChange={(e) => setActions((prev) => ({ ...prev, [idx]: { ...a, target: e.target.value } }))}
                        >
                          {options.map((o) => (
                            <option key={o} value={o}>
                              {o}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {issues.length > pageSize && (
              <div className="pager">
                <button type="button" className="btn btn-ghost btn-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                  Prev
                </button>
                <span className="muted">
                  {page + 1} / {Math.ceil(issues.length / pageSize)}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={(page + 1) * pageSize >= issues.length}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </button>
              </div>
            )}

            {!issues.length && !loading && <p className="muted">Scan to list residual name issues.</p>}
          </section>
        </div>
      )}

      {tab === "audit" && (
        <section className="panel">
          <div className="panel-head panel-head--wrap">
            <h3>Audit log</h3>
            <div className="page-controls" style={{ margin: 0 }}>
              <label className="ctrl">
                Start
                <input type="date" value={auditStart} onChange={(e) => setAuditStart(e.target.value)} />
              </label>
              <label className="ctrl">
                End
                <input type="date" value={auditEnd} onChange={(e) => setAuditEnd(e.target.value)} />
              </label>
              <label className="ctrl ctrl--check">
                <input
                  type="checkbox"
                  checked={auditScopes.includes("State")}
                  onChange={(e) =>
                    setAuditScopes((s) => (e.target.checked ? [...new Set([...s, "State"])] : s.filter((x) => x !== "State")))
                  }
                />
                State
              </label>
              <label className="ctrl ctrl--check">
                <input
                  type="checkbox"
                  checked={auditScopes.includes("District")}
                  onChange={(e) =>
                    setAuditScopes((s) =>
                      e.target.checked ? [...new Set([...s, "District"])] : s.filter((x) => x !== "District")
                    )
                  }
                />
                District
              </label>
            </div>
          </div>

          <div className="export-row" style={{ marginBottom: "1rem" }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!selIds.length}
              onClick={async () => {
                await api.revertGovernance(selIds);
                setSelIds([]);
                await refreshStatus();
                onChanged?.();
                setMsg(`Reverted ${selIds.length}`);
              }}
            >
              Revert selected ({selIds.length})
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              disabled={!filteredAudit.length}
              onClick={async () => {
                const ids = filteredAudit.map((r) => r.ID);
                await api.revertGovernance(ids);
                setSelIds([]);
                await refreshStatus();
                onChanged?.();
                setMsg("Reverted all filtered");
              }}
            >
              Revert filtered
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => triggerDownload(api.exportAudit(), "governance_audit.csv")}>
              Export CSV
            </button>
          </div>

          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Sel</th>
                  <th>Time</th>
                  <th>Scope</th>
                  <th>Action</th>
                  <th>Original</th>
                  <th>Target</th>
                  <th>User</th>
                </tr>
              </thead>
              <tbody>
                {filteredAudit.slice(0, 100).map((r) => (
                  <tr key={r.ID}>
                    <td>
                      <input type="checkbox" checked={selIds.includes(r.ID)} onChange={() => toggleSel(r.ID)} />
                    </td>
                    <td className="mono">{String(r.Timestamp).slice(0, 19)}</td>
                    <td>{r.Scope}</td>
                    <td>
                      <span className={`badge ${r.Action === "Merge" ? "success" : "danger"}`}>{r.Action}</span>
                    </td>
                    <td>{r.Original}</td>
                    <td>{r.Target}</td>
                    <td>{r.User}</td>
                  </tr>
                ))}
                {!filteredAudit.length && (
                  <tr>
                    <td colSpan={7} className="muted">
                      No actions recorded
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {msg && <p className="panel-meta">{msg}</p>}
        </section>
      )}

      {tab === "io" && (
        <section className="panel">
          <div className="panel-head">
            <h3>Import / export</h3>
          </div>
          <div className="export-row" style={{ marginBottom: "1.25rem" }}>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => triggerDownload(api.exportGovPack(), "governance_pack.json")}>
              Download pack
            </button>
            <label className="btn btn-ghost btn-sm">
              Import pack
              <input
                type="file"
                accept="application/json,.json"
                style={{ display: "none" }}
                onChange={(e) => importFile(e.target.files?.[0])}
              />
            </label>
          </div>
          <div className="kpi-row kpi-row--4">
            <KpiCard label="State merges" value={Object.keys(status?.state_patches || {}).length} format={false} compact accent="blue" />
            <KpiCard label="District merges" value={Object.keys(status?.district_patches || {}).length} format={false} compact accent="violet" />
            <KpiCard label="State deletions" value={status?.state_deletions?.length || 0} format={false} compact accent="rose" />
            <KpiCard label="District deletions" value={status?.district_deletions?.length || 0} format={false} compact accent="amber" />
          </div>
          {msg && <p className="panel-meta">{msg}</p>}
        </section>
      )}
    </div>
  );
}
