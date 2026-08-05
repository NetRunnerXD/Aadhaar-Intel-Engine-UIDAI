"""Data governance console — durable patches, audit, AI triage."""
from __future__ import annotations

import datetime
import difflib
import math
import uuid

import pandas as pd
import streamlit as st

from src.ai.ollama_client import get_ollama_client
from src.geo.normalize import load_official_states
from src.services import governance_store as gstore

OFFICIAL_STATES = load_official_states() or [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal", "Andaman & Nicobar Islands", "Chandigarh",
    "Dadra & Nagar Haveli And Daman & Diu", "Delhi", "Jammu & Kashmir", "Ladakh",
    "Lakshadweep", "Puducherry",
]


def init_session_state():
    if st.session_state.get("_governance_loaded"):
        return

    store = gstore.load_store()
    st.session_state.state_patches = dict(store.get("state_patches") or {})
    st.session_state.district_patches = dict(store.get("district_patches") or {})
    st.session_state.state_deletions = list(store.get("state_deletions") or [])
    st.session_state.district_deletions = list(store.get("district_deletions") or [])
    st.session_state.governance_log = gstore.load_audit_log()
    st.session_state.scan_results_state = pd.DataFrame()
    st.session_state.scan_results_dist = pd.DataFrame()
    st.session_state._governance_loaded = True
    if _has_active_governance():
        st.session_state.data_dirty = True


def persist_governance():
    gstore.save_store(
        st.session_state.get("state_patches", {}),
        st.session_state.get("district_patches", {}),
        st.session_state.get("state_deletions", []),
        st.session_state.get("district_deletions", []),
    )
    log = st.session_state.get("governance_log")
    if log is not None and not log.empty:
        gstore.save_audit_log(log)


def batch_log_changes(entries):
    if not entries:
        return
    new_logs = pd.DataFrame(entries)
    st.session_state.governance_log = pd.concat(
        [st.session_state.governance_log, new_logs],
        ignore_index=True,
    )
    persist_governance()


def revert_changes(log_ids_to_revert):
    logs = st.session_state.governance_log
    to_process = logs[logs["ID"].isin(log_ids_to_revert)]

    for _, row in to_process.iterrows():
        scope, action, orig = row["Scope"], row["Action"], row["Original"]
        if scope == "State":
            if action == "Merge" and orig in st.session_state.state_patches:
                del st.session_state.state_patches[orig]
            elif action == "Delete" and orig in st.session_state.state_deletions:
                if orig in st.session_state.state_deletions:
                    st.session_state.state_deletions.remove(orig)
        elif scope == "District":
            if action == "Merge" and orig in st.session_state.district_patches:
                del st.session_state.district_patches[orig]
            elif action == "Delete" and orig in st.session_state.district_deletions:
                if orig in st.session_state.district_deletions:
                    st.session_state.district_deletions.remove(orig)

    st.session_state.governance_log = logs[~logs["ID"].isin(log_ids_to_revert)]
    st.session_state.data_dirty = True
    persist_governance()
    st.toast(f"Reverted {len(to_process)} actions.", icon="↩️")


def find_state_discrepancies(df):
    if df is None or df.empty or "state" not in df.columns:
        return pd.DataFrame()
    present = df["state"].astype(str).unique()
    issues = []
    official = set(OFFICIAL_STATES)
    for s in present:
        if s not in official:
            matches = difflib.get_close_matches(s, OFFICIAL_STATES, n=1, cutoff=0.4)
            tgt = matches[0] if matches else "Unknown"
            conf = difflib.SequenceMatcher(None, s.lower(), tgt.lower()).ratio() if matches else 0.0
            vol = int((df["state"].astype(str) == s).sum())
            issues.append({"Suspect": s, "Fix": tgt, "Conf": conf, "Suspect_Vol": vol})
    return pd.DataFrame(issues).sort_values("Conf", ascending=False) if issues else pd.DataFrame()


def find_district_discrepancies(df):
    if df is None or df.empty or "district" not in df.columns:
        return pd.DataFrame()
    dists = sorted(df["district"].astype(str).unique())
    issues = []
    processed = set()

    has_pins = "pincode" in df.columns
    pin_map = {}
    if has_pins:
        valid_pins = df[pd.to_numeric(df["pincode"], errors="coerce").fillna(0) > 0][["district", "pincode"]]
        if not valid_pins.empty:
            pin_map = (
                valid_pins.assign(district=valid_pins["district"].astype(str))
                .groupby("district")["pincode"]
                .apply(set)
                .to_dict()
            )

    vol_col = "total_enrolments" if "total_enrolments" in df.columns else None

    for d in dists:
        if d in processed:
            continue
        matches = difflib.get_close_matches(d, dists, n=5, cutoff=0.85)
        matches = [m for m in matches if m != d]
        if not matches:
            continue

        if vol_col:
            curr_count = float(df.loc[df["district"].astype(str) == d, vol_col].sum())
        else:
            curr_count = float((df["district"].astype(str) == d).sum())

        best, max_c = None, -1
        for m in matches:
            if vol_col:
                mc = float(df.loc[df["district"].astype(str) == m, vol_col].sum())
            else:
                mc = float((df["district"].astype(str) == m).sum())
            if has_pins and d in pin_map and m in pin_map:
                if pin_map[d] and pin_map[m] and not pin_map[d].intersection(pin_map[m]):
                    continue
            if mc > curr_count:
                best, max_c = m, mc

        if best:
            conf = difflib.SequenceMatcher(None, d.lower(), best.lower()).ratio()
            s_pins = list(pin_map.get(d, []))
            t_pins = list(pin_map.get(best, []))
            overlap = bool(set(s_pins) & set(t_pins)) if s_pins and t_pins else False
            issues.append(
                {
                    "Suspect": d,
                    "Fix": best,
                    "Conf": conf,
                    "Suspect_Vol": int(curr_count),
                    "Target_Vol": int(max_c),
                    "PIN_Overlap": overlap,
                    "Suspect_PINs": ", ".join(map(str, s_pins[:3])) + ("..." if len(s_pins) > 3 else ""),
                    "Fix_PINs": ", ".join(map(str, t_pins[:3])) + ("..." if len(t_pins) > 3 else ""),
                }
            )
            processed.add(d)

    return pd.DataFrame(issues).sort_values("Conf", ascending=False) if issues else pd.DataFrame()


def paginator(label, items, items_per_page=10, on_sidebar=False):
    n_items = len(items) if not isinstance(items, int) else items
    if n_items <= items_per_page:
        return 0, n_items
    n_pages = math.ceil(n_items / items_per_page)
    container = st.sidebar if on_sidebar else st
    c1, c2, c3 = container.columns([2, 1, 2])
    with c2:
        current_page = st.number_input(
            f"{label} Page", min_value=1, max_value=n_pages, value=1, key=f"pg_{label}"
        )
    start_idx = (current_page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, n_items)
    container.caption(f"Showing {start_idx + 1}-{end_idx} of {n_items}")
    return start_idx, end_idx


def render_fix_tab(df_enrol):
    c1, c2 = st.columns([3, 1])
    c1.markdown("### Anomaly Resolution")
    c1.caption("Review inconsistent names. Changes persist to disk and apply across the session.")
    target_type = c2.radio("Scope:", ["States", "Districts"], horizontal=True, label_visibility="collapsed")

    if target_type == "States":
        if st.session_state.scan_results_state.empty:
            if st.button("Start State Scan", key="scan_state"):
                with st.spinner("Scanning state names..."):
                    st.session_state.scan_results_state = find_state_discrepancies(df_enrol)
                    st.rerun()
        issues = st.session_state.scan_results_state
        active_patches = st.session_state.state_patches
        active_dels = st.session_state.state_deletions
        options = OFFICIAL_STATES
    else:
        if st.session_state.scan_results_dist.empty:
            st.info("District scan uses fuzzy matching + optional PIN overlap.")
            if st.button("Start District Scan", key="scan_dist"):
                with st.spinner("Scanning district names..."):
                    st.session_state.scan_results_dist = find_district_discrepancies(df_enrol)
                    st.rerun()
        issues = st.session_state.scan_results_dist
        active_patches = st.session_state.district_patches
        active_dels = st.session_state.district_deletions
        options = sorted(df_enrol["district"].astype(str).unique()) if not df_enrol.empty else []

    if issues is None or issues.empty:
        st.write("Ready to scan — or no residual issues after ETL repairs.")
        return

    pending = issues[
        (~issues["Suspect"].isin(active_patches.keys())) & (~issues["Suspect"].isin(active_dels))
    ]
    if pending.empty:
        st.success(f"All {target_type.lower()} data is clean under active patches.")
        return

    with st.expander("AI governance triage", expanded=True):
        st.caption("Recommendations for merges · evidence from the issue table only")
        if st.button("Generate triage advice", key="gov_ai", type="primary"):
            from src.ai_core import AnalyticsEngine

            eng = AnalyticsEngine(df_enrol, pd.DataFrame(), pd.DataFrame())
            with st.spinner("Writing stewardship guidance..."):
                st.session_state.gov_ai_text = eng.generate_governance_insight(pending, use_llm=True)
        if st.session_state.get("gov_ai_text"):
            st.markdown(st.session_state.gov_ai_text)

    a1, a2, a3 = st.columns([1, 2, 1])
    a1.metric("Issues Found", len(pending))
    high_conf = pending[pending["Conf"] > 0.9]
    if not high_conf.empty:
        if a3.button(f"Auto-Fix ({len(high_conf)})", type="primary", use_container_width=True):
            log_entries = []
            for _, row in high_conf.iterrows():
                if target_type == "States":
                    st.session_state.state_patches[row["Suspect"]] = row["Fix"]
                else:
                    st.session_state.district_patches[row["Suspect"]] = row["Fix"]
                log_entries.append(
                    {
                        "ID": str(uuid.uuid4()),
                        "Timestamp": datetime.datetime.now(),
                        "Scope": target_type[:-1],
                        "Action": "Merge",
                        "Original": row["Suspect"],
                        "Target": row["Fix"],
                        "User": "Admin_01",
                    }
                )
            batch_log_changes(log_entries)
            st.session_state.data_dirty = True
            persist_governance()
            st.rerun()

    st.markdown("---")
    start, end = paginator("Discrepancies", len(pending), items_per_page=10)
    current_page_data = pending.iloc[start:end]

    with st.form(f"fix_form_{target_type}_page"):
        user_actions = {}
        for idx, row in current_page_data.iterrows():
            suspect = row["Suspect"]
            with st.container(border=True):
                col_main, col_act = st.columns([3, 1])
                with col_main:
                    st.markdown(f"**{suspect}** `{row['Suspect_Vol']} records`")
                    if target_type == "Districts":
                        pc1, pc2 = st.columns(2)
                        pc1.caption(f"PINs: {row.get('Suspect_PINs', 'N/A')}")
                        color = "green" if row.get("PIN_Overlap") else "orange"
                        match_text = "PIN Match" if row.get("PIN_Overlap") else "No Overlap"
                        pc2.markdown(f":{color}[{match_text}] → **{row['Fix']}**")
                    else:
                        st.caption(f"Similarity: {int(row['Conf'] * 100)}% → **{row['Fix']}**")
                with col_act:
                    act = st.selectbox(
                        "Action",
                        ["Merge", "Delete", "Ignore"],
                        key=f"act_{idx}",
                        label_visibility="collapsed",
                        index=0 if row["Conf"] > 0.85 else 2,
                    )
                    if act == "Merge":
                        try:
                            def_idx = options.index(row["Fix"])
                        except Exception:
                            def_idx = 0
                        tgt = st.selectbox(
                            "Target", options, index=def_idx, key=f"tgt_{idx}", label_visibility="collapsed"
                        )
                        user_actions[idx] = {"act": act, "tgt": tgt, "suspect": suspect}
                    else:
                        user_actions[idx] = {"act": act, "tgt": None, "suspect": suspect}

        if st.form_submit_button("Commit Changes (Current Page)", type="primary", use_container_width=True):
            log_entries = []
            changes = 0
            for idx, data in user_actions.items():
                action = st.session_state.get(f"act_{idx}")
                if not action or action == "Ignore":
                    continue
                suspect, target = data["suspect"], st.session_state.get(f"tgt_{idx}", None)
                if target_type == "States":
                    if action == "Merge":
                        st.session_state.state_patches[suspect] = target
                    elif action == "Delete":
                        st.session_state.state_deletions.append(suspect)
                else:
                    if action == "Merge":
                        st.session_state.district_patches[suspect] = target
                    elif action == "Delete":
                        st.session_state.district_deletions.append(suspect)
                log_entries.append(
                    {
                        "ID": str(uuid.uuid4()),
                        "Timestamp": datetime.datetime.now(),
                        "Scope": target_type[:-1],
                        "Action": action,
                        "Original": suspect,
                        "Target": target if target else "N/A",
                        "User": "Admin_01",
                    }
                )
                changes += 1
            if changes > 0:
                batch_log_changes(log_entries)
                st.session_state.data_dirty = True
                persist_governance()
                st.toast(f"Processed {changes} items!", icon="✅")
                st.rerun()


def render_audit_tab():
    st.caption("History, export, and revert. Patches are stored under `output/`.")
    logs = st.session_state.governance_log
    if logs is None or logs.empty:
        st.info("No actions recorded.")
        return
    with st.expander("Filters", expanded=True):
        c1, c2, c3 = st.columns(3)
        min_t = logs["Timestamp"].min()
        max_t = logs["Timestamp"].max()
        if pd.isna(min_t) or pd.isna(max_t):
            filtered = logs
        else:
            min_t, max_t = min_t.to_pydatetime(), max_t.to_pydatetime() + datetime.timedelta(seconds=1)
            start_t, end_t = c1.date_input("Start", min_t), c2.date_input("End", max_t)
            scope = c3.multiselect("Scope", ["State", "District"], default=["State", "District"])
            mask = (
                (logs["Timestamp"] >= datetime.datetime.combine(start_t, datetime.time.min))
                & (logs["Timestamp"] <= datetime.datetime.combine(end_t, datetime.time.max))
                & (logs["Scope"].isin(scope))
            )
            filtered = logs[mask].sort_values("Timestamp", ascending=False)

    st.markdown(f"### Log ({len(filtered)})")
    start, end = paginator("Logs", len(filtered), items_per_page=15)
    view_logs = filtered.iloc[start:end]
    sel_ids = []
    for _, row in view_logs.iterrows():
        c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 2])
        if c1.checkbox("Sel", key=f"l_{row['ID']}", label_visibility="collapsed"):
            sel_ids.append(row["ID"])
        ts = row["Timestamp"]
        c2.caption(ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts))
        color = "green" if row["Action"] == "Merge" else "red"
        c3.markdown(f":{color}[{row['Scope']} {row['Action']}]")
        c4.code(
            f"{row['Original']} -> {row['Target']}" if row["Action"] == "Merge" else f"Del: {row['Original']}"
        )
        c5.caption(row["User"])
        st.divider()

    b1, b2, b3 = st.columns([1, 1, 2])
    with b1:
        if st.button("Revert Sel", disabled=(len(sel_ids) == 0), type="primary"):
            revert_changes(sel_ids)
            st.rerun()
    with b2:
        if st.button("Revert All"):
            revert_changes(filtered["ID"].tolist())
            st.rerun()
    with b3:
        st.download_button(
            "Export CSV",
            logs.to_csv(index=False).encode("utf-8"),
            f"log_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv",
            use_container_width=True,
        )


def render_io_tab():
    st.markdown("### Import / Export patch pack")
    pack = gstore.export_pack(
        st.session_state.get("state_patches", {}),
        st.session_state.get("district_patches", {}),
        st.session_state.get("state_deletions", []),
        st.session_state.get("district_deletions", []),
        st.session_state.get("governance_log"),
    )
    st.download_button("Download pack JSON", pack, "governance_pack.json", "application/json")

    uploaded = st.file_uploader("Import pack JSON", type=["json"])
    if uploaded is not None:
        try:
            raw = uploaded.read().decode("utf-8")
            data = gstore.import_pack(raw)
            st.session_state.state_patches = data["state_patches"]
            st.session_state.district_patches = data["district_patches"]
            st.session_state.state_deletions = data["state_deletions"]
            st.session_state.district_deletions = data["district_deletions"]
            if data.get("audit"):
                st.session_state.governance_log = pd.DataFrame(data["audit"])
                if "Timestamp" in st.session_state.governance_log.columns:
                    st.session_state.governance_log["Timestamp"] = pd.to_datetime(
                        st.session_state.governance_log["Timestamp"], errors="coerce"
                    )
            st.session_state.data_dirty = True
            persist_governance()
            st.success("Pack imported and saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Import failed: {e}")

    st.markdown("### Active patch summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("State merges", len(st.session_state.get("state_patches", {})))
    c2.metric("District merges", len(st.session_state.get("district_patches", {})))
    c3.metric("State deletions", len(st.session_state.get("state_deletions", [])))
    c4.metric("District deletions", len(st.session_state.get("district_deletions", [])))
    st.caption(f"On-disk store: `{gstore.GOVERNANCE_FILE}`")


def render_tab(df_enrol):
    init_session_state()
    st.subheader("Data Governance Console")

    status = get_ollama_client().status()
    if status.available:
        st.caption(f"Ollama online · model `{status.model}`")
    else:
        st.caption(f"Ollama offline ({status.error}) — AI triage uses deterministic stats until available.")

    tab1, tab2, tab3 = st.tabs(["Fix Anomalies", "Audit & Revert", "Import / Export"])
    with tab1:
        render_fix_tab(df_enrol)
    with tab2:
        render_audit_tab()
    with tab3:
        render_io_tab()


def _has_active_governance() -> bool:
    return bool(
        st.session_state.get("state_patches")
        or st.session_state.get("district_patches")
        or st.session_state.get("state_deletions")
        or st.session_state.get("district_deletions")
    )


def apply_governance_changes(df):
    if df is None or df.empty:
        return df

    if "state_patches" not in st.session_state:
        st.session_state.state_patches = {}
    if "district_patches" not in st.session_state:
        st.session_state.district_patches = {}
    if "state_deletions" not in st.session_state:
        st.session_state.state_deletions = []
    if "district_deletions" not in st.session_state:
        st.session_state.district_deletions = []

    if not _has_active_governance():
        return df

    df = df.copy()
    for col in ("state", "district"):
        if col in df.columns and str(df[col].dtype) == "category":
            df[col] = df[col].astype(object)

    if st.session_state.state_deletions and "state" in df.columns:
        df = df[~df["state"].isin(st.session_state.state_deletions)]
    if st.session_state.district_deletions and "district" in df.columns:
        df = df[~df["district"].isin(st.session_state.district_deletions)]
    if st.session_state.state_patches and "state" in df.columns:
        df["state"] = df["state"].replace(st.session_state.state_patches)
    if st.session_state.district_patches and "district" in df.columns:
        df["district"] = df["district"].replace(st.session_state.district_patches)
    return df
