# -*- coding: utf-8 -*-
"""Extract live API metrics for Outcomes document."""
from __future__ import annotations

import json
import urllib.request
from collections import Counter
from pathlib import Path

SNAP = Path(__file__).resolve().parent / "_live_api_snapshots"
OUT = SNAP / "summary_for_outcomes.json"


def load(name: str):
    return json.loads((SNAP / name).read_text(encoding="utf-8"))


def main():
    a = load("api_analytics.json")
    d = load("api_dashboard.json")
    f = load("api_forecast_horizon_30_model_Auto.json")
    ins_d = load("api_insights_dashboard.json")
    ins_f = load("api_insights_forecast_horizon_30_model_Auto.json")

    risk = a.get("risk_cells") or []
    reasons = Counter(r.get("reason") for r in risk)
    states_flagged = Counter(r.get("state") for r in risk)

    meta = f.get("meta") or {}
    fc = f.get("forecast") or []
    preds = [x["predicted"] for x in fc] if fc else []

    # map
    map_payload = None
    try:
        raw = urllib.request.urlopen("http://127.0.0.1:8787/api/map", timeout=180).read()
        (SNAP / "api_map.json").write_bytes(raw)
        map_payload = json.loads(raw)
    except Exception as e:
        map_payload = {"error": str(e)}

    top_districts = []
    top_states_map = []
    map_summary = {}
    if isinstance(map_payload, dict) and "error" not in map_payload:
        for key in ("top_districts", "districts", "points", "rankings", "top_states"):
            v = map_payload.get(key)
            if isinstance(v, list) and v:
                map_summary[key + "_n"] = len(v)
        # prefer ranked lists
        for key in ("top_districts", "rankings", "districts", "points"):
            v = map_payload.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                # sort by volume-like field
                vol_key = None
                for cand in ("volume", "total_enrolments", "value", "intensity"):
                    if cand in v[0]:
                        vol_key = cand
                        break
                rows = v
                if vol_key:
                    rows = sorted(v, key=lambda r: float(r.get(vol_key) or 0), reverse=True)
                top_districts = rows[:10]
                break
        for key in ("top_states", "states"):
            v = map_payload.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                top_states_map = v[:10]
                break
        for k, v in map_payload.items():
            if not isinstance(v, (list, dict)):
                map_summary[k] = v
            elif isinstance(v, dict) and k in ("kpis", "summary", "stats", "centroid_sources"):
                map_summary[k] = v

    # governance meta from earlier health/meta if present
    meta_path = SNAP / "api_meta.json"
    if not meta_path.exists():
        try:
            raw = urllib.request.urlopen("http://127.0.0.1:8787/api/meta", timeout=60).read()
            meta_path.write_bytes(raw)
        except Exception:
            pass
    api_meta = load("api_meta.json") if meta_path.exists() else {}

    summary = {
        "source": "http://127.0.0.1:8787",
        "dashboard_kpis": d.get("kpis"),
        "dashboard_workload": d.get("workload"),
        "dashboard_age_mix": d.get("age_mix"),
        "dashboard_params": d.get("params"),
        "forecast_peak": d.get("forecast_peak"),
        "forecast_floor": d.get("forecast_floor"),
        "bakeoff_caption": d.get("bakeoff_caption"),
        "top_risk": (d.get("top_risk") or [])[:15],
        "analytics_kpis": a.get("kpis"),
        "top_states": a.get("top_states"),
        "workload": a.get("workload"),
        "ratios": a.get("ratios"),
        "risk_cell_count": len(risk),
        "reason_counts": dict(reasons),
        "states_flagged": states_flagged.most_common(15),
        "risk_cells_top": risk[:15],
        "forecast_model": f.get("model"),
        "forecast_meta": {
            k: meta.get(k)
            for k in (
                "model",
                "selection",
                "selection_meta",
                "horizon",
                "growth_factor",
                "conformal_alpha",
                "conformal_q",
                "interval_method",
                "decision_band",
                "primary_metric",
                "train_days",
                "data_end",
                "calendar_filled",
                "candidates",
                "thresholds_mase",
                "thresholds_smape",
            )
        },
        "model_comparison": f.get("comparison") or meta.get("model_comparison"),
        "rolling": meta.get("rolling"),
        "backtest": meta.get("backtest"),
        "resource_planning": f.get("resource_planning"),
        "forecast_series_summary": {
            "n": len(preds),
            "first": fc[0] if fc else None,
            "last": fc[-1] if fc else None,
            "peak_predicted": max(preds) if preds else None,
            "floor_predicted": min(preds) if preds else None,
            "avg_predicted": (sum(preds) / len(preds)) if preds else None,
            "sum_predicted": sum(preds) if preds else None,
        },
        "insights_dashboard_excerpt": (ins_d.get("markdown") or "")[:1200],
        "insights_forecast_excerpt": (ins_f.get("markdown") or "")[:1200],
        "llm_model_dashboard": ins_d.get("model"),
        "llm_model_forecast": ins_f.get("model"),
        "map_summary": map_summary,
        "map_top_districts": top_districts[:8],
        "map_top_states": top_states_map[:8],
        "api_meta_brief": {
            "source": api_meta.get("source"),
            "date_min": api_meta.get("date_min"),
            "date_max": api_meta.get("date_max"),
            "rows": api_meta.get("rows"),
            "states_n": len(api_meta.get("states") or []),
            "llm": api_meta.get("llm"),
            "governance": api_meta.get("governance"),
            "geo_eval": (api_meta.get("load_report") or {}).get("geo_eval"),
            "geo_repair_stats": (api_meta.get("load_report") or {}).get("geo_repair_stats"),
            "geo_rule_pack": (api_meta.get("load_report") or {}).get("geo_rule_pack"),
            "rows_raw": (api_meta.get("load_report") or {}).get("rows_raw"),
            "rows_quarantined": (api_meta.get("load_report") or {}).get("rows_quarantined"),
            "duplicate_keys_collapsed": (api_meta.get("load_report") or {}).get(
                "duplicate_keys_collapsed"
            ),
        },
    }
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote", OUT)
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:8000])


if __name__ == "__main__":
    main()
