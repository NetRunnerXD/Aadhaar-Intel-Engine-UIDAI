"""
Repair rows where a district/locality was written into the `state` column.

Typical dirty demo rows:
  state=Jaipur, district='Near meera hospital', pincode=302016
→ state=Rajasthan, district=Jaipur
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.config import (
    DISTRICT_ALIASES_PATH,
    DISTRICT_AS_STATE_PATH,
    TELANGANA_DISTRICTS_PATH,
)
from src.geo.normalize import _normalize_key, load_official_states


@lru_cache(maxsize=1)
def load_district_as_state_map(path: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    p = Path(path) if path else DISTRICT_AS_STATE_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    return {_normalize_key(k): v for k, v in raw.items()}


@lru_cache(maxsize=1)
def load_district_aliases(path: Optional[str] = None) -> Dict[str, str]:
    p = Path(path) if path else DISTRICT_ALIASES_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    return {_normalize_key(k): v for k, v in raw.items()}


@lru_cache(maxsize=1)
def load_telangana_districts(path: Optional[str] = None) -> set:
    p = Path(path) if path else TELANGANA_DISTRICTS_PATH
    if not p.exists():
        return set()
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    return {_normalize_key(x) for x in raw}


def _title_district(name: str) -> str:
    s = " ".join(str(name).strip().split())
    return s.title() if s else s


def build_corpus_district_to_state(df: pd.DataFrame, official: List[str]) -> Dict[str, str]:
    """
    From rows that already have an official state, map district name → majority state.
    Used to repair misfiled states when the label appears as a real district elsewhere.
    """
    if df is None or df.empty or "state" not in df.columns or "district" not in df.columns:
        return {}
    official_set = set(official)
    work = df.copy()
    work["_state"] = work["state"].astype(str)
    work["_district"] = work["district"].astype(str).str.strip().str.title()
    valid = work[work["_state"].isin(official_set)]
    if valid.empty:
        return {}
    # majority state per district
    mapping: Dict[str, str] = {}
    for dist, grp in valid.groupby("_district", observed=True):
        if not dist or dist.lower() in {"nan", "none", "unknown"}:
            continue
        top = grp["_state"].value_counts()
        if len(top) == 0:
            continue
        mapping[_normalize_key(str(dist))] = str(top.index[0])
    return mapping


def repair_misfiled_states(
    df: pd.DataFrame,
    seed_map: Optional[Dict[str, Dict[str, str]]] = None,
    corpus_map: Optional[Dict[str, str]] = None,
) -> Tuple[pd.DataFrame, List[dict]]:
    """
    For non-official `state` values that look like districts:
      - set state to the parent state
      - set district to the canonical district (from seed or the misfiled label)

    Returns (repaired_df, list of repair audit records).
    """
    if df is None or df.empty or "state" not in df.columns:
        return df, []

    official = load_official_states()
    official_set = set(official)
    seed_map = seed_map if seed_map is not None else load_district_as_state_map()
    if corpus_map is None:
        corpus_map = build_corpus_district_to_state(df, official)

    out = df.copy()
    # Work in object dtype for safe assignment
    out["state"] = out["state"].astype(object)
    if "district" in out.columns:
        out["district"] = out["district"].astype(object)

    repairs: List[dict] = []
    states = out["state"].astype(str)
    bad_mask = ~states.isin(official_set) & (states != "Unknown")

    if not bad_mask.any():
        return out, repairs

    for idx in out.index[bad_mask]:
        raw_state = str(out.at[idx, "state"])
        key = _normalize_key(raw_state)
        old_district = str(out.at[idx, "district"]) if "district" in out.columns else ""

        new_state = None
        new_district = None
        source = None

        if key in seed_map:
            entry = seed_map[key]
            new_state = entry.get("state")
            new_district = entry.get("district") or _title_district(raw_state)
            source = "seed"
        elif key in corpus_map:
            new_state = corpus_map[key]
            new_district = _title_district(raw_state)
            source = "corpus"
        else:
            continue

        if new_state not in official_set:
            continue

        out.at[idx, "state"] = new_state
        if "district" in out.columns and new_district:
            out.at[idx, "district"] = new_district

        repairs.append(
            {
                "old_state": raw_state,
                "old_district": old_district,
                "new_state": new_state,
                "new_district": new_district,
                "source": source,
            }
        )

    return out, repairs


def summarize_repairs(repairs: List[dict]) -> Dict[str, int]:
    """Count repairs by old_state label."""
    counts: Dict[str, int] = {}
    for r in repairs:
        k = r.get("old_state", "?")
        counts[k] = counts.get(k, 0) + 1
    return counts


def apply_district_aliases(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Normalize known district spelling variants."""
    if df is None or df.empty or "district" not in df.columns:
        return df, 0
    aliases = load_district_aliases()
    if not aliases:
        return df, 0
    out = df.copy()
    keys = out["district"].astype(str).map(_normalize_key)
    mapped = keys.map(aliases)
    mask = mapped.notna() & (mapped != out["district"].astype(str))
    n = int(mask.sum())
    if n:
        out.loc[mask, "district"] = mapped[mask].values
    return out, n


def apply_telangana_boundary_fix(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Reassign known Telangana districts currently tagged as Andhra Pradesh.
    Policy: automatic reassignment with count returned for audit.
    """
    if df is None or df.empty or "state" not in df.columns or "district" not in df.columns:
        return df, 0
    ts_set = load_telangana_districts()
    if not ts_set:
        return df, 0
    out = df.copy()
    st = out["state"].astype(str)
    dist_key = out["district"].astype(str).map(_normalize_key)
    mask = st.eq("Andhra Pradesh") & dist_key.isin(ts_set)
    n = int(mask.sum())
    if n:
        out.loc[mask, "state"] = "Telangana"
    return out, n


def full_geo_repair(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Run all geo repairs: district-as-state, district aliases, AP→Telangana.
    Returns (df, stats).
    """
    stats: Dict[str, int] = {
        "district_as_state": 0,
        "district_aliases": 0,
        "ap_to_telangana": 0,
    }
    if df is None or df.empty:
        return df, stats

    repaired, audit = repair_misfiled_states(df)
    stats["district_as_state"] = len(audit)
    repaired, n_alias = apply_district_aliases(repaired)
    stats["district_aliases"] = n_alias
    repaired, n_ts = apply_telangana_boundary_fix(repaired)
    stats["ap_to_telangana"] = n_ts
    return repaired, stats
