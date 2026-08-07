import { useEffect, useMemo, useState } from "react";
import { api, fmt, triggerDownload } from "../api";
import MarkdownBlock from "../components/MarkdownBlock";

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
      const ins = await api.insightGovernance(scope);
      setInsight(ins.markdown);
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

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Data Governance</h2>
          <p>Human-in-the-loop name repair · durable patches · AI analysis</p>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: "1rem" }}>
        <div className="card kpi">
          <div className="label">State merges</div>
          <div className="value">{status ? Object.keys(status.state_patches || {}).length : "—"}</div>
        </div>
        <div className="card kpi">
          <div className="label">District merges</div>
          <div className="value">{status ? Object.keys(status.district_patches || {}).length : "—"}</div>
        </div>
        <div className="card kpi">
          <div className="label">State deletions</div>
          <div className="value">{status?.state_deletions?.length ?? "—"}</div>
        </div>
        <div className="card kpi">
          <div className="label">District deletions</div>
          <div className="value">{status?.district_deletions?.length ?? "—"}</div>
        </div>
      </div>

      <div className="tabs">
        <button className={tab === "fix" ? "active" : ""} onClick={() => setTab("fix")}>
          Fix anomalies
        </button>
        <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>
          Audit & revert
        </button>
        <button className={tab === "io" ? "active" : ""} onClick={() => setTab("io")}>
          Import / export
        </button>
      </div>

      {tab === "fix" && (
        <>
          <div className="card" style={{ marginBottom: "1rem" }}>
            <div className="card-head">
              <h3>AI analysis</h3>
              <button
                className="btn btn-primary btn-sm"
                onClick={async () => {
                  setInsight("Analyzing…");
                  try {
                    const r = await api.insightGovernance(scope);
                    setInsight(r.markdown);
                  } catch (e) {
                    setInsight(String(e.message || e));
                  }
                }}
              >
                Run analysis
              </button>
            </div>
            <MarkdownBlock text={insight} />
          </div>

          <div className="card">
            <div className="toolbar">
              <label>
                Scope
                <select value={scope} onChange={(e) => setScope(e.target.value)}>
                  <option value="states">States</option>
                  <option value="districts">Districts</option>
                </select>
              </label>
              <button className="btn btn-primary" onClick={scan} disabled={loading}>
                {loading ? "Working…" : "Start scan"}
              </button>
              <button className="btn btn-ghost" onClick={autoFixHigh} disabled={!high.length || loading}>
                Auto-Fix high conf ({high.length})
              </button>
              <button className="btn btn-ghost" onClick={() => setConfirmAll(true)} disabled={!issues.length || loading}>
                Merge all ({issues.length})
              </button>
              <button className="btn btn-primary" onClick={commitPage} disabled={!pageIssues.length || loading}>
                Commit page
              </button>
            </div>

            {confirmAll && (
              <div className="banner warn">
                Merge all applies the <strong>suggested target</strong> for all <strong>{issues.length}</strong> pending{" "}
                {scope}.
                <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                  <button className="btn btn-primary" onClick={mergeAll}>
                    Confirm merge all
                  </button>
                  <button className="btn btn-ghost" onClick={() => setConfirmAll(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {msg && <p className="muted">{msg}</p>}

            {pageIssues.map((row, localIdx) => {
              const idx = page * pageSize + localIdx;
              const a = actions[idx] || { act: "Ignore", target: row.Fix };
              const options = scope === "states" ? official : districtOptions.length ? districtOptions : [row.Fix];
              return (
                <div className="issue-card" key={idx} style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
                  <div style={{ flex: 1, minWidth: 200 }}>
                    <strong>{row.Suspect}</strong>
                    <div className="muted">
                      conf {(Number(row.Conf) * 100).toFixed(0)}% · vol {fmt(row.Suspect_Vol)}
                      {row.PIN_Overlap != null && (
                        <> · PIN {row.PIN_Overlap ? "match" : "no overlap"}</>
                      )}
                      {row.Suspect_PINs && <> · PINs {row.Suspect_PINs}</>}
                    </div>
                    <div className="muted">Suggested → {row.Fix}</div>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
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

            {issues.length > pageSize && (
              <div className="toolbar">
                <button className="btn btn-ghost btn-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                  Prev
                </button>
                <span className="muted">
                  Page {page + 1} / {Math.ceil(issues.length / pageSize)}
                </span>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={(page + 1) * pageSize >= issues.length}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </button>
              </div>
            )}

            {!issues.length && !loading && <p className="muted">Scan to list residual name issues after ETL repairs.</p>}
          </div>
        </>
      )}

      {tab === "audit" && (
        <div className="card">
          <h3>Audit log</h3>
          <p className="muted">History, export, and revert. Patches stored under output/.</p>
          <div className="toolbar">
            <label>
              Start
              <input type="date" value={auditStart} onChange={(e) => setAuditStart(e.target.value)} />
            </label>
            <label>
              End
              <input type="date" value={auditEnd} onChange={(e) => setAuditEnd(e.target.value)} />
            </label>
            <label>
              <input
                type="checkbox"
                checked={auditScopes.includes("State")}
                onChange={(e) =>
                  setAuditScopes((s) => (e.target.checked ? [...new Set([...s, "State"])] : s.filter((x) => x !== "State")))
                }
              />{" "}
              State
            </label>
            <label>
              <input
                type="checkbox"
                checked={auditScopes.includes("District")}
                onChange={(e) =>
                  setAuditScopes((s) =>
                    e.target.checked ? [...new Set([...s, "District"])] : s.filter((x) => x !== "District")
                  )
                }
              />{" "}
              District
            </label>
          </div>
          <div className="toolbar">
            <button
              className="btn btn-primary"
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
              className="btn btn-danger"
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
              Revert all filtered
            </button>
            <button className="btn btn-ghost" onClick={() => triggerDownload(api.exportAudit(), "governance_audit.csv")}>
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
        </div>
      )}

      {tab === "io" && (
        <div className="card">
          <h3>Import / export patch pack</h3>
          <div className="toolbar">
            <button className="btn btn-primary" onClick={() => triggerDownload(api.exportGovPack(), "governance_pack.json")}>
              Download pack JSON
            </button>
            <label className="btn btn-ghost">
              Import pack JSON
              <input
                type="file"
                accept="application/json,.json"
                style={{ display: "none" }}
                onChange={(e) => importFile(e.target.files?.[0])}
              />
            </label>
          </div>
          <p className="muted">On-disk store: {status?.store_path || "output/governance_patches.json"}</p>
          <h3 style={{ marginTop: "1rem" }}>Active patch summary</h3>
          <div className="grid grid-4">
            <KpiLike label="State merges" value={Object.keys(status?.state_patches || {}).length} />
            <KpiLike label="District merges" value={Object.keys(status?.district_patches || {}).length} />
            <KpiLike label="State deletions" value={status?.state_deletions?.length || 0} />
            <KpiLike label="District deletions" value={status?.district_deletions?.length || 0} />
          </div>
          {msg && <p className="muted">{msg}</p>}
        </div>
      )}
    </>
  );
}

function KpiLike({ label, value }) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}
