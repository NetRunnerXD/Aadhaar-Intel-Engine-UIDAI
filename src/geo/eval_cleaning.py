"""Precision/recall evaluation of geo-cleaning rules against gold labels."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.config import EVAL_GEO_GOLD_PATH, RULES_MANIFEST_PATH
from src.geo.normalize import canonicalize_state, load_official_states
from src.geo.repair import full_geo_repair
from src.geo.centroids import clean_district_name


def load_rules_manifest() -> Dict[str, Any]:
    p = RULES_MANIFEST_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_gold_cases(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = Path(path) if path else EVAL_GEO_GOLD_PATH
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("cases") or [])


def _apply_pipeline_row(raw_state, raw_district, pincode) -> Dict[str, Any]:
    """Run the same logical steps as load-time cleaning for one synthetic row."""
    df = pd.DataFrame(
        [
            {
                "date": "01-06-2025",
                "state": str(raw_state),
                "district": str(raw_district),
                "pincode": int(pincode) if pincode is not None else 0,
                "adult_enrolments": 1,
                "total_enrolments": 1,
            }
        ]
    )
    # mirror data_manager standardization lightly
    df["state"] = df["state"].map(lambda s: canonicalize_state(s))
    df["district"] = df["district"].astype(str).str.strip().str.title()
    df["district"] = df["district"].map(clean_district_name)
    repaired, stats = full_geo_repair(df)

    # PIN fallback if still non-official
    official = set(load_official_states())
    st = str(repaired.iloc[0]["state"])
    if st not in official or st == "Unknown":
        from src.geo.pin_map import state_from_pincode

        pin_state = state_from_pincode(repaired.iloc[0].get("pincode"))
        if pin_state and pin_state in official:
            repaired = repaired.copy()
            repaired.loc[:, "state"] = pin_state
            stats = dict(stats)
            stats["pin_prefix_fallback"] = 1

    out_state = str(repaired.iloc[0]["state"])
    out_district = clean_district_name(str(repaired.iloc[0]["district"]))

    # quarantine numeric states
    if out_state not in official:
        out_state = "Unknown"

    return {"state": out_state, "district": out_district, "stats": stats}


def evaluate_geo_cleaning(path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Returns precision/recall-style metrics:
    - state_accuracy: fraction of cases with expected_state match
    - district_accuracy: fraction with expected_district match (case-insensitive)
    - both_accuracy: both match
    - per_rule breakdown
    """
    cases = load_gold_cases(path)
    if not cases:
        return {"n": 0, "state_accuracy": None, "district_accuracy": None, "both_accuracy": None}

    rows = []
    for c in cases:
        pred = _apply_pipeline_row(c["raw_state"], c["raw_district"], c.get("pincode"))
        exp_s = canonicalize_state(c["expected_state"]) if c["expected_state"] != "Unknown" else "Unknown"
        if c["expected_state"] == "Unknown":
            exp_s = "Unknown"
        exp_d = clean_district_name(c["expected_district"])
        pred_d = clean_district_name(pred["district"])
        state_ok = pred["state"] == exp_s
        # district match: exact or containment for alias targets
        district_ok = pred_d.lower() == exp_d.lower() or exp_d.lower() in pred_d.lower() or pred_d.lower() in exp_d.lower()
        rows.append(
            {
                "rule": c.get("rule", "?"),
                "state_ok": state_ok,
                "district_ok": district_ok,
                "both_ok": state_ok and district_ok,
                "raw_state": c["raw_state"],
                "pred_state": pred["state"],
                "exp_state": exp_s,
                "pred_district": pred_d,
                "exp_district": exp_d,
            }
        )

    df = pd.DataFrame(rows)
    n = len(df)
    summary = {
        "n": n,
        "rule_pack": load_rules_manifest().get("rule_pack_version"),
        "state_accuracy": float(df["state_ok"].mean()) if n else None,
        "district_accuracy": float(df["district_ok"].mean()) if n else None,
        "both_accuracy": float(df["both_ok"].mean()) if n else None,
        "per_rule": (
            df.groupby("rule")[["state_ok", "district_ok", "both_ok"]].mean().round(3).to_dict(orient="index")
            if n
            else {}
        ),
        "failures": df[~df["both_ok"]].to_dict(orient="records"),
    }
    return summary


def dry_run_repairs(df: pd.DataFrame) -> Dict[str, Any]:
    """Report what full_geo_repair would change without requiring write path."""
    if df is None or df.empty:
        return {"rows": 0, "stats": {}, "sample_changes": []}
    before = df[["state", "district"]].astype(str).copy() if set(["state", "district"]).issubset(df.columns) else df.copy()
    after, stats = full_geo_repair(df.copy())
    sample = []
    if "state" in after.columns and "district" in after.columns:
        changed = (before["state"].values != after["state"].astype(str).values) | (
            before["district"].values != after["district"].astype(str).values
        )
        idx = after.index[changed][:25]
        for i in idx:
            sample.append(
                {
                    "from_state": before.loc[i, "state"] if i in before.index else None,
                    "to_state": str(after.loc[i, "state"]),
                    "from_district": before.loc[i, "district"] if i in before.index else None,
                    "to_district": str(after.loc[i, "district"]),
                }
            )
    return {
        "rows": int(len(df)),
        "stats": stats,
        "n_changed": int(changed.sum()) if "state" in after.columns else 0,
        "sample_changes": sample,
        "rule_pack": load_rules_manifest().get("rule_pack_version"),
    }
