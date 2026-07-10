import streamlit as st
import pandas as pd
import difflib
import datetime
import uuid
import math

# --- CONFIGURATION & INIT ---
OFFICIAL_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", 
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", 
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", 
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", 
    "Uttarakhand", "West Bengal", "Andaman & Nicobar", "Chandigarh", "Dadra & Nagar Haveli", 
    "Daman & Diu", "Delhi", "Jammu & Kashmir", "Ladakh", "Lakshadweep", "Puducherry"
]

def init_session_state():
    if 'state_patches' not in st.session_state: st.session_state.state_patches = {}
    if 'state_deletions' not in st.session_state: st.session_state.state_deletions = []
    if 'district_patches' not in st.session_state: st.session_state.district_patches = {}
    if 'district_deletions' not in st.session_state: st.session_state.district_deletions = []
    if 'governance_log' not in st.session_state: 
        st.session_state.governance_log = pd.DataFrame(columns=["ID", "Timestamp", "Scope", "Action", "Original", "Target", "User"])
    
    # Caching scan results
    if 'scan_results_state' not in st.session_state: st.session_state.scan_results_state = pd.DataFrame()
    if 'scan_results_dist' not in st.session_state: st.session_state.scan_results_dist = pd.DataFrame()

# --- OPTIMIZED LOGGING (The Fix) ---
def batch_log_changes(entries):
    """
    Writes multiple logs at once to avoid O(N^2) dataframe rebuilding.
    """
    if not entries: return
    new_logs = pd.DataFrame(entries)
    st.session_state.governance_log = pd.concat(
        [st.session_state.governance_log, new_logs], 
        ignore_index=True
    )

def revert_changes(log_ids_to_revert):
    logs = st.session_state.governance_log
    to_process = logs[logs['ID'].isin(log_ids_to_revert)]
    
    # Remove from patches/deletions
    for _, row in to_process.iterrows():
        scope, action, orig = row['Scope'], row['Action'], row['Original']
        
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
    
    # Update Log
    st.session_state.governance_log = logs[~logs['ID'].isin(log_ids_to_revert)]
    st.session_state.data_dirty = True
    st.toast(f"✅ Reverted {len(to_process)} actions.", icon="↩️")

# --- OPTIMIZED FINDERS ---
def find_state_discrepancies(df):
    if df.empty or 'state' not in df.columns: return pd.DataFrame()
    present = df['state'].unique().astype(str)
    issues = []
    for s in present:
        if s not in OFFICIAL_STATES:
            matches = difflib.get_close_matches(s, OFFICIAL_STATES, n=1, cutoff=0.4)
            tgt = matches[0] if matches else "Unknown"
            conf = difflib.SequenceMatcher(None, s.lower(), tgt.lower()).ratio() if matches else 0.0
            issues.append({"Suspect": s, "Fix": tgt, "Conf": conf, "Suspect_Vol": len(df[df['state']==s])})
    return pd.DataFrame(issues).sort_values('Conf', ascending=False) if issues else pd.DataFrame()

def find_district_discrepancies(df):
    if df.empty or 'district' not in df.columns: return pd.DataFrame()
    dists = sorted(df['district'].unique().astype(str))
    issues = []
    processed = set()
    
    has_pins = 'pincode' in df.columns
    pin_map = {}
    if has_pins:
        valid_pins = df[df['pincode'] > 0][['district', 'pincode']]
        if not valid_pins.empty:
            pin_map = valid_pins.groupby('district')['pincode'].apply(set).to_dict()

    for d in dists:
        if d in processed: continue
        matches = difflib.get_close_matches(d, dists, n=5, cutoff=0.85)
        matches = [m for m in matches if m != d]
        
        if matches:
            curr_count = len(df[df['district'] == d])
            best, max_c = None, -1
            
            for m in matches:
                mc = len(df[df['district'] == m])
                if has_pins and d in pin_map and m in pin_map:
                    suspect_pins, target_pins = pin_map[d], pin_map[m]
                    if suspect_pins and target_pins and not suspect_pins.intersection(target_pins):
                        continue 
                if mc > curr_count:
                    best, max_c = m, mc
            
            if best:
                conf = difflib.SequenceMatcher(None, d.lower(), best.lower()).ratio()
                s_pins = list(pin_map.get(d, []))
                t_pins = list(pin_map.get(best, []))
                overlap = bool(set(s_pins) & set(t_pins)) if s_pins and t_pins else False
                
                issues.append({
                    "Suspect": d, "Fix": best, "Conf": conf, "Suspect_Vol": curr_count,
                    "Target_Vol": max_c, "PIN_Overlap": overlap,
                    "Suspect_PINs": ", ".join(map(str, s_pins[:3])) + ("..." if len(s_pins)>3 else ""),
                    "Fix_PINs": ", ".join(map(str, t_pins[:3])) + ("..." if len(t_pins)>3 else "")
                })
                processed.add(d)
                
    return pd.DataFrame(issues).sort_values('Conf', ascending=False) if issues else pd.DataFrame()

# --- UI COMPONENTS ---
def paginator(label, items, items_per_page=10, on_sidebar=False):
    if not isinstance(items, int): n_items = len(items)
    else: n_items = items
    if n_items <= items_per_page: return 0, n_items
    n_pages = math.ceil(n_items / items_per_page)
    container = st.sidebar if on_sidebar else st
    c1, c2, c3 = container.columns([2, 1, 2])
    with c2: current_page = st.number_input(f"{label} Page", min_value=1, max_value=n_pages, value=1, key=f"pg_{label}")
    start_idx = (current_page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, n_items)
    container.caption(f"Showing {start_idx+1}-{end_idx} of {n_items}")
    return start_idx, end_idx

def render_fix_tab(df_enrol):
    c1, c2 = st.columns([3, 1])
    c1.markdown("### ⚡ Anomaly Resolution")
    c1.caption("Review and standardize inconsistent data entries.")
    
    target_type = c2.radio("Scope:", ["States", "Districts"], horizontal=True, label_visibility="collapsed")

    # Manual Scan Trigger
    if target_type == "States":
        if st.session_state.scan_results_state.empty:
            if st.button("🔍 Start State Scan"):
                with st.spinner("Scanning State Names..."):
                    st.session_state.scan_results_state = find_state_discrepancies(df_enrol)
        issues = st.session_state.scan_results_state
        active_patches = st.session_state.state_patches
        active_dels = st.session_state.state_deletions
        options = OFFICIAL_STATES
    else:
        if st.session_state.scan_results_dist.empty:
            st.info("District scanning uses deep fuzzy matching and may take a few seconds.")
            if st.button("🔍 Start District Scan"):
                with st.spinner("Scanning District Names..."):
                    st.session_state.scan_results_dist = find_district_discrepancies(df_enrol)
        issues = st.session_state.scan_results_dist
        active_patches = st.session_state.district_patches
        active_dels = st.session_state.district_deletions
        options = sorted(df_enrol['district'].unique().astype(str))

    if issues.empty:
        st.write("Ready to scan.")
        return

    # Filter Active
    pending = issues[(~issues['Suspect'].isin(active_patches.keys())) & (~issues['Suspect'].isin(active_dels))]

    if pending.empty:
        st.success(f"✅ All {target_type.lower()} data is clean!")
        return

    # Action Bar
    a1, a2, a3 = st.columns([1, 2, 1])
    a1.metric("Issues Found", len(pending))
    
    # --- OPTIMIZED AUTO-FIX (BATCH MODE) ---
    high_conf = pending[pending['Conf'] > 0.9]
    if not high_conf.empty:
        if a3.button(f"✨ Auto-Fix ({len(high_conf)})", type="primary", use_container_width=True):
            log_entries = []
            
            for _, row in high_conf.iterrows():
                if target_type == "States": st.session_state.state_patches[row['Suspect']] = row['Fix']
                else: st.session_state.district_patches[row['Suspect']] = row['Fix']
                
                # Prepare log entry but DON'T save yet
                log_entries.append({
                    "ID": str(uuid.uuid4()), "Timestamp": datetime.datetime.now(), 
                    "Scope": target_type[:-1], "Action": "Merge", 
                    "Original": row['Suspect'], "Target": row['Fix'], "User": "Admin_01"
                })
            
            # Save ALL logs at once (Fast)
            batch_log_changes(log_entries)
            st.session_state.data_dirty = True
            st.rerun()

    st.markdown("---")
    
    # Paginated Table
    start, end = paginator("Discrepancies", len(pending), items_per_page=10)
    current_page_data = pending.iloc[start:end]

    with st.form(f"fix_form_{target_type}_page"):
        user_actions = {}
        for idx, row in current_page_data.iterrows():
            suspect = row['Suspect']
            with st.container(border=True):
                col_main, col_act = st.columns([3, 1])
                with col_main:
                    st.markdown(f"**{suspect}** `{row['Suspect_Vol']} records`")
                    if target_type == "Districts":
                        pc1, pc2 = st.columns(2)
                        pc1.caption(f"📍 PINs: {row.get('Suspect_PINs', 'N/A')}")
                        color = "green" if row.get('PIN_Overlap') else "orange"
                        match_text = "✅ PIN Match" if row.get('PIN_Overlap') else "⚠️ No Overlap"
                        pc2.markdown(f":{color}[{match_text}] → **{row['Fix']}**")
                    else:
                        st.caption(f"Similiarity: {int(row['Conf']*100)}% → Suggestion: **{row['Fix']}**")
                with col_act:
                    act = st.selectbox("Action", ["Merge", "Delete", "Ignore"], key=f"act_{idx}", label_visibility="collapsed", index=0 if row['Conf'] > 0.85 else 2)
                    if act == "Merge":
                        try: def_idx = options.index(row['Fix'])
                        except: def_idx = 0
                        tgt = st.selectbox("Target", options, index=def_idx, key=f"tgt_{idx}", label_visibility="collapsed")
                        user_actions[idx] = {"act": act, "tgt": tgt, "suspect": suspect}
                    else:
                        user_actions[idx] = {"act": act, "tgt": None, "suspect": suspect}

        st.markdown("---")
        
        # --- OPTIMIZED MANUAL COMMIT (BATCH MODE) ---
        if st.form_submit_button("🚀 Commit Changes (Current Page)", type="primary", use_container_width=True):
            log_entries = []
            changes = 0
            
            for idx, data in user_actions.items():
                action = st.session_state.get(f"act_{idx}")
                if not action or action == "Ignore": continue
                suspect, target = data['suspect'], st.session_state.get(f"tgt_{idx}", None)
                
                # Update Session State
                if target_type == "States":
                    if action == "Merge": st.session_state.state_patches[suspect] = target
                    elif action == "Delete": st.session_state.state_deletions.append(suspect)
                else:
                    if action == "Merge": st.session_state.district_patches[suspect] = target
                    elif action == "Delete": st.session_state.district_deletions.append(suspect)
                
                # Prepare log
                log_entries.append({
                    "ID": str(uuid.uuid4()), "Timestamp": datetime.datetime.now(), 
                    "Scope": target_type[:-1], "Action": action, 
                    "Original": suspect, "Target": target if target else "N/A", "User": "Admin_01"
                })
                changes += 1
            
            # Save ALL logs at once (Fast)
            if changes > 0: 
                batch_log_changes(log_entries)
                st.session_state.data_dirty = True
                st.toast(f"Processed {changes} items!", icon="✅")
                st.rerun()

def render_audit_tab():
    st.caption("View history, export logs, or revert changes.")
    logs = st.session_state.governance_log
    if logs.empty: st.info("No actions recorded."); return
    with st.expander("⏳ Time-Travel & Filters", expanded=True):
        c1, c2, c3 = st.columns(3)
        min_t, max_t = logs['Timestamp'].min().to_pydatetime(), logs['Timestamp'].max().to_pydatetime() + datetime.timedelta(seconds=1)
        start_t, end_t = c1.date_input("Start", min_t), c2.date_input("End", max_t)
        scope = c3.multiselect("Scope", ["State", "District"], default=["State", "District"])
        mask = (logs['Timestamp'] >= datetime.datetime.combine(start_t, datetime.time.min)) & (logs['Timestamp'] <= datetime.datetime.combine(end_t, datetime.time.max)) & (logs['Scope'].isin(scope))
        filtered = logs[mask].sort_values("Timestamp", ascending=False)
    
    st.markdown(f"### 📜 Log ({len(filtered)})")
    start, end = paginator("Logs", len(filtered), items_per_page=15)
    view_logs = filtered.iloc[start:end]
    
    c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 2])
    c1.markdown("**Select**"); c2.markdown("**Time**"); c3.markdown("**Action**"); c4.markdown("**Change**"); c5.markdown("**User**")
    st.divider()
    sel_ids = []
    for idx, row in view_logs.iterrows():
        c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 2])
        if c1.checkbox("Sel", key=f"l_{row['ID']}", label_visibility="collapsed"): sel_ids.append(row['ID'])
        c2.caption(row['Timestamp'].strftime("%H:%M:%S"))
        color = "green" if row['Action']=="Merge" else "red"
        c3.markdown(f":{color}[{row['Scope']} {row['Action']}]")
        c4.code(f"{row['Original']} -> {row['Target']}" if row['Action']=="Merge" else f"Del: {row['Original']}")
        c5.caption(row['User'])
        st.divider()
    
    b1, b2, b3 = st.columns([1, 1, 2])
    with b1: 
        if st.button("↩️ Revert Sel", disabled=(len(sel_ids)==0), type="primary"): revert_changes(sel_ids); st.rerun()
    with b2:
        if st.button("♻️ Revert All"): revert_changes(filtered['ID'].tolist()); st.rerun()
    with b3:
        st.download_button("💾 Export CSV", logs.to_csv(index=False).encode('utf-8'), f"log_{datetime.datetime.now().strftime('%Y%m%d')}.csv", "text/csv", use_container_width=True)

def render_tab(df_enrol):
    init_session_state()
    st.subheader("🛠️ Data Governance Console")
    tab1, tab2 = st.tabs(["⚡ Fix Anomalies", "📜 Audit & Revert"])
    with tab1: render_fix_tab(df_enrol)
    with tab2: render_audit_tab()

def apply_governance_changes(df):
    """
    Applies active session_state patches to the dataframe.
    """
    if df.empty: return df
    
    # Init state safely
    if 'state_patches' not in st.session_state: st.session_state.state_patches = {}
    if 'district_patches' not in st.session_state: st.session_state.district_patches = {}
    if 'state_deletions' not in st.session_state: st.session_state.state_deletions = []
    if 'district_deletions' not in st.session_state: st.session_state.district_deletions = []

    # 1. Apply Deletions (Filter first to reduce rows for Replace)
    if st.session_state.state_deletions:
        df = df[~df['state'].isin(st.session_state.state_deletions)]
    if st.session_state.district_deletions:
        df = df[~df['district'].isin(st.session_state.district_deletions)]
        
    # 2. Apply Patches
    if st.session_state.state_patches:
        df['state'] = df['state'].replace(st.session_state.state_patches)
    if st.session_state.district_patches:
        df['district'] = df['district'].replace(st.session_state.district_patches)
        
    return df