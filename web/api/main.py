# -*- coding: utf-8 -*-
"""Aadhaar Intel Engine — FastAPI (full Streamlit feature parity for React UI)."""
from __future__ import annotations

import datetime
import io
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import FORECAST_CANDIDATES, OUTPUT_DIR
from src.geo.centroids import resolve_centroid
from src.services import governance_store as gstore
from web.api import data_service as ds

ROOT = Path(__file__).resolve().parent.parent.parent
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(title="Aadhaar Intel Engine API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_states(states: Optional[str]) -> Optional[List[str]]:
    if not states:
        return None
    parts = [s.strip() for s in states.split(",") if s.strip()]
    return parts or None


def _sum(df: pd.DataFrame, col: str) -> float:
    if df is None or df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def _vol(df: pd.DataFrame) -> str:
    if df is not None and not df.empty:
        if "total_enrolments" in df.columns:
            return "total_enrolments"
        if "adult_enrolments" in df.columns:
            return "adult_enrolments"
    return "total_enrolments"


def _csv_response(df: pd.DataFrame, filename: str) -> StreamingResponse:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _jitter(name: str, axis: int) -> float:
    seed = abs(hash((str(name), axis))) % 10_000
    return (seed / 10_000.0) * 0.3 - 0.15


@app.on_event("startup")
def _startup():
    try:
        ds.ensure_loaded()
    except Exception as e:
        print("Data load warning:", e)


@app.get("/api/health")
def health():
    data = ds.ensure_loaded()
    return {"ok": True, "ready": bool(data.get("ready")), "source": data.get("source")}


@app.get("/api/meta")
def meta():
    m = ds.meta_payload()
    data = ds.ensure_loaded()
    m["logs"] = list(data.get("logs") or [])[-40:]
    m["governance"] = {
        "state_merges": len(data.get("state_patches") or {}),
        "district_merges": len(data.get("district_patches") or {}),
        "state_deletions": len(data.get("state_deletions") or []),
        "district_deletions": len(data.get("district_deletions") or []),
        "store_path": str(gstore.GOVERNANCE_FILE),
    }
    return m


@app.post("/api/reload")
def reload_data():
    ds.reload_data()
    return meta()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/api/dashboard")
def dashboard(
    states: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    contamination: float = 0.05,
    min_volume: int = 50,
):
    st_list = _parse_states(states)
    eng = ds.engine_for(st_list, start, end)
    enrol, demo, bio = ds.filter_frames(st_list, start, end)
    vol = _vol(enrol)
    total = _sum(enrol, vol)
    adult = _sum(enrol, "adult_enrolments")
    bio_t = _sum(bio, "bio_stress")
    demo_t = _sum(demo, "update_volume")

    anom = eng.get_anomalies(contamination=contamination, min_volume=min_volume, force=True)
    fc, model = eng.forecast_trends(horizon=30, model_type="Auto")
    growth = 0.0
    if fc is not None and not fc.empty:
        a, b = float(fc.iloc[0]["predicted"]), float(fc.iloc[-1]["predicted"])
        if a > 0:
            growth = ((b - a) / a) * 100

    age = {}
    for c, label in (("age_0_5", "0–5"), ("age_5_17", "5–17"), ("age_18_greater", "18+")):
        if c in enrol.columns:
            age[label] = _sum(enrol, c)

    daily = []
    if not enrol.empty and "date" in enrol.columns and vol in enrol.columns:
        t = enrol.groupby("date", observed=True)[vol].sum().reset_index().sort_values("date").tail(90)
        daily = [{"date": str(r["date"])[:10], "volume": float(r[vol])} for _, r in t.iterrows()]

    inv_cols = [
        c
        for c in (
            "state",
            "district",
            "volume",
            "risk_score",
            "reason",
            "bio_ratio",
            "demo_ratio",
            "cv",
            "investigation_notes",
            "driver_z",
        )
        if c in anom.columns
    ]
    top_risk = ds.df_records(anom[inv_cols].head(15)) if not anom.empty and inv_cols else []
    risk_bars = []
    if not anom.empty:
        top10 = anom.head(10)
        for _, r in top10.iterrows():
            risk_bars.append(
                {
                    "label": f"{r.get('district', '')} ({str(r.get('state', ''))[:10]})",
                    "risk_score": float(r.get("risk_score", 0) or 0),
                    "state": str(r.get("state", "")),
                    "district": str(r.get("district", "")),
                    "volume": float(r.get("volume", 0) or 0),
                }
            )

    meta_f = eng._last_forecast_meta or {}
    roll = meta_f.get("rolling") or {}
    bt = meta_f.get("backtest") or {}
    cmp = meta_f.get("model_comparison") or []
    forecast_series = []
    peak = floor = None
    if fc is not None and not fc.empty:
        peak = float(fc["predicted"].max())
        floor = float(fc["predicted"].min())
        for _, r in fc.iterrows():
            forecast_series.append(
                {
                    "date": str(r["date"])[:10],
                    "predicted": float(r["predicted"]),
                    "lower": float(r["lower"]),
                    "upper": float(r["upper"]),
                }
            )

    corr = eng.get_correlation()
    workload = {"enrolments": total, "bio": bio_t, "demo": demo_t}
    if not corr.empty:
        workload = {
            "enrolments": float(corr["Enrolments"].sum()),
            "bio": float(corr["Bio_Updates"].sum()),
            "demo": float(corr["Demo_Updates"].sum()),
        }

    data = ds.ensure_loaded()
    return ds._json_safe(
        {
            "kpis": {
                "total_enrolments": int(total),
                "adult_enrolments": int(adult),
                "biometric_updates": int(bio_t),
                "demographic_updates": int(demo_t),
                "anomaly_count": int(len(anom)),
                "forecast_growth_pct": round(growth, 2),
                "forecast_model": model,
                "rolling_mase": roll.get("rolling_mase"),
                "rolling_smape": roll.get("rolling_smape_pct"),
                "holdout_smape": bt.get("smape_pct"),
                "holdout_mape": bt.get("mape_pct"),
                "decision_band": meta_f.get("decision_band"),
                "active_states": int(enrol["state"].nunique()) if not enrol.empty and "state" in enrol.columns else 0,
                "active_districts": int(enrol["district"].nunique())
                if not enrol.empty and "district" in enrol.columns
                else 0,
            },
            "workload": workload,
            "age_mix": age,
            "daily_trend": daily,
            "top_risk": top_risk,
            "risk_bars": risk_bars,
            "investigation_note": (
                str(anom.iloc[0]["investigation_notes"])
                if not anom.empty and "investigation_notes" in anom.columns
                else None
            ),
            "forecast": forecast_series,
            "forecast_peak": peak,
            "forecast_floor": floor,
            "bakeoff_caption": ", ".join(f"{r.get('model')}={r.get('smape_pct')}%" for r in cmp[:6]) if cmp else "",
            "logs": list(data.get("logs") or [])[-30:],
            "params": {"contamination": contamination, "min_volume": min_volume},
        }
    )


@app.get("/api/insights/dashboard")
def insights_dashboard(
    states: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    contamination: float = 0.05,
    min_volume: int = 50,
):
    eng = ds.engine_for(_parse_states(states), start, end)
    anom = eng.get_anomalies(contamination=contamination, min_volume=min_volume, force=True)
    return {"markdown": eng.generate_dashboard_insight(len(anom), use_llm=True)}


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@app.get("/api/analytics")
def analytics(
    states: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    contamination: float = 0.05,
    min_volume: int = 50,
):
    st_list = _parse_states(states)
    eng = ds.engine_for(st_list, start, end)
    enrol, _, _ = ds.filter_frames(st_list, start, end)
    vol = _vol(enrol)

    daily = []
    if not enrol.empty and "date" in enrol.columns:
        t = enrol.groupby("date", observed=True)[vol].sum().reset_index().sort_values("date")
        daily = [{"date": str(r["date"])[:10], "volume": float(r[vol])} for _, r in t.iterrows()]

    top_states = []
    if not enrol.empty and "state" in enrol.columns:
        ts = enrol.groupby("state", observed=True)[vol].sum().nlargest(10).reset_index()
        top_states = [{"state": str(r["state"]), "volume": float(r[vol])} for _, r in ts.iterrows()]

    corr = eng.get_correlation()
    new = updates = demov = 0.0
    if not corr.empty:
        new = float(corr["Enrolments"].sum())
        updates = float(corr["Bio_Updates"].sum())
        demov = float(corr["Demo_Updates"].sum())
    workload = {"enrolments": new, "bio": updates, "demo": demov}
    ratios = {
        "bio_per_enrol": round(updates / (new + 1), 2),
        "demo_per_enrol": round(demov / (new + 1), 2),
    }

    # low volume watchlist
    watchlist = []
    if not enrol.empty and "district" in enrol.columns and vol in enrol.columns:
        bottom = (
            enrol[enrol[vol] > 0]
            .groupby(["state", "district"], observed=True)[vol]
            .sum()
            .nsmallest(10)
            .reset_index()
        )
        watchlist = [
            {"state": str(r["state"]), "district": str(r["district"]), "volume": float(r[vol])}
            for _, r in bottom.iterrows()
        ]

    anom = eng.get_anomalies(contamination=contamination, min_volume=min_volume, force=True)
    state_radar = []
    if not anom.empty and "state" in anom.columns:
        work = anom.copy()
        work["risk_score"] = pd.to_numeric(work["risk_score"], errors="coerce").fillna(0)
        volc = "volume" if "volume" in work.columns else None
        agg = {"max_risk": ("risk_score", "max"), "mean_risk": ("risk_score", "mean"), "flags": ("risk_score", "count")}
        if volc:
            work[volc] = pd.to_numeric(work[volc], errors="coerce").fillna(0)
            agg["flagged_volume"] = (volc, "sum")
        s = work.groupby("state", observed=True).agg(**agg).reset_index()
        s = s.sort_values("flagged_volume" if "flagged_volume" in s.columns else "max_risk", ascending=False).head(10)
        state_radar = ds.df_records(s)

    scatter = []
    cells = []
    inv_notes = []
    if not anom.empty:
        ycol = "volume" if "volume" in anom.columns else vol
        for _, r in anom.iterrows():
            scatter.append(
                {
                    "district": str(r.get("district", "")),
                    "state": str(r.get("state", "")),
                    "volume": float(r.get(ycol, 0) or 0),
                    "risk_score": float(r.get("risk_score", 0) or 0),
                    "reason": str(r.get("reason", "")),
                }
            )
        cols = [
            c
            for c in (
                "state",
                "district",
                "risk_score",
                "reason",
                "volume",
                "bio_ratio",
                "demo_ratio",
                "cv",
                "investigation_notes",
            )
            if c in anom.columns
        ]
        cells = ds.df_records(anom[cols].head(50))
        if "investigation_notes" in anom.columns:
            inv_notes = ds.df_records(anom[["state", "district", "risk_score", "reason", "investigation_notes"]].head(20))

    adult = _sum(enrol, "adult_enrolments")
    return ds._json_safe(
        {
            "kpis": {
                "total": float(enrol[vol].sum()) if not enrol.empty and vol in enrol.columns else 0,
                "adult": adult,
                "states": int(enrol["state"].nunique()) if not enrol.empty and "state" in enrol.columns else 0,
                "districts": int(enrol["district"].nunique()) if not enrol.empty and "district" in enrol.columns else 0,
                "rows": int(len(enrol)),
                "flags": int(len(anom)),
            },
            "daily": daily,
            "top_states": top_states,
            "workload": workload,
            "ratios": ratios,
            "watchlist": watchlist,
            "state_radar": state_radar,
            "scatter": scatter,
            "risk_cells": cells,
            "investigation_notes": inv_notes,
        }
    )


@app.get("/api/analytics/export/{kind}")
def analytics_export(
    kind: str,
    states: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    st_list = _parse_states(states)
    eng = ds.engine_for(st_list, start, end)
    enrol, _, _ = ds.filter_frames(st_list, start, end)
    vol = _vol(enrol)
    kind = kind.lower()
    if kind == "regional":
        df = enrol.groupby(["state", "district"], observed=True)[vol].sum().reset_index()
        return _csv_response(df, "regional.csv")
    if kind == "trends":
        if "date" not in enrol.columns:
            raise HTTPException(400, "No date column")
        df = enrol.groupby("date", observed=True)[vol].sum().reset_index()
        return _csv_response(df, "trends.csv")
    if kind == "risk":
        return _csv_response(eng.get_anomalies(), "risk.csv")
    if kind == "ops":
        return _csv_response(eng.get_correlation(), "ops.csv")
    raise HTTPException(404, "Unknown export kind")


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------


@app.get("/api/forecast")
def forecast(
    states: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    horizon: int = 30,
    model: str = "Auto",
    growth_factor: float = 0.0,
    series_state: Optional[str] = None,
):
    eng = ds.engine_for(_parse_states(states), start, end)
    enrol, _, _ = ds.filter_frames(_parse_states(states), start, end)
    vol = _vol(enrol)

    cmp = eng.compare_forecast_models()
    comparison = ds.df_records(cmp) if cmp is not None and not cmp.empty else []

    fc, label = eng.forecast_trends(
        horizon=horizon,
        model_type=model if model != "Auto" else "Auto",
        growth_factor=growth_factor,
        state=series_state or None,
    )
    meta = eng._last_forecast_meta or {}

    hist = []
    if not enrol.empty and "date" in enrol.columns:
        h_df = enrol
        if series_state and "state" in enrol.columns:
            h_df = enrol[enrol["state"].astype(str) == str(series_state)]
        h = h_df.groupby("date", observed=True)[vol].sum().reset_index().sort_values("date").tail(90)
        hist = [{"date": str(r["date"])[:10], "volume": float(r[vol])} for _, r in h.iterrows()]

    series = []
    peak = avg = 0.0
    if fc is not None and not fc.empty:
        peak = float(fc["predicted"].max())
        avg = float(fc["predicted"].mean())
        for _, r in fc.iterrows():
            series.append(
                {
                    "date": str(r["date"])[:10],
                    "predicted": float(r["predicted"]),
                    "lower": float(r["lower"]),
                    "upper": float(r["upper"]),
                }
            )

    state_options = []
    if not enrol.empty and "state" in enrol.columns:
        state_options = sorted(enrol["state"].astype(str).unique().tolist())

    return ds._json_safe(
        {
            "candidates": list(FORECAST_CANDIDATES),
            "state_options": state_options,
            "model": label,
            "meta": meta,
            "comparison": comparison,
            "history": hist,
            "forecast": series,
            "resource_planning": {
                "operators_at_40": int(np.ceil(peak / 40)) if peak else 0,
                "peak_daily": peak,
                "avg_daily": avg,
                "per_operator": 40,
            },
        }
    )


@app.get("/api/forecast/export")
def forecast_export(
    states: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    horizon: int = 30,
    model: str = "Auto",
    growth_factor: float = 0.0,
    series_state: Optional[str] = None,
):
    eng = ds.engine_for(_parse_states(states), start, end)
    fc, _ = eng.forecast_trends(
        horizon=horizon, model_type=model, growth_factor=growth_factor, state=series_state or None
    )
    if fc is None or fc.empty:
        raise HTTPException(400, "No forecast")
    out = fc.copy()
    out["date"] = out["date"].astype(str)
    return _csv_response(out, "forecast_data.csv")


@app.get("/api/insights/forecast")
def insights_forecast(
    states: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    horizon: int = 30,
    model: str = "Auto",
    series_state: Optional[str] = None,
):
    eng = ds.engine_for(_parse_states(states), start, end)
    fc, label = eng.forecast_trends(horizon=horizon, model_type=model, state=series_state or None)
    return {"markdown": eng.generate_forecast_insight(fc, label, use_llm=True), "model": label}


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------


def _map_frame(
    enrol: pd.DataFrame,
    depth: str,
    scale: str,
) -> pd.DataFrame:
    if enrol.empty:
        return pd.DataFrame()
    vol = _vol(enrol)
    work = enrol.copy()
    for c in ("state", "district"):
        if c in work.columns:
            work[c] = work[c].astype(str)
    agg = work.groupby(["state", "district"], as_index=False, observed=True)[vol].sum()
    agg = agg.rename(columns={vol: "volume"})
    agg["volume"] = pd.to_numeric(agg["volume"], errors="coerce").fillna(0)
    if depth in ("top5", "Top 5 Priority"):
        agg = (
            agg.sort_values(["state", "volume"], ascending=[True, False])
            .groupby("state", as_index=False, sort=False)
            .head(5)
            .reset_index(drop=True)
        )
    rows = []
    for _, row in agg.iterrows():
        lat, lon, src = resolve_centroid(row["state"], row["district"])
        if src in ("state", "default"):
            lat = float(lat) + _jitter(row["district"], 0)
            lon = float(lon) + _jitter(row["district"], 1)
        rows.append(
            {
                "state": row["state"],
                "district": row["district"],
                "volume": float(row["volume"]),
                "lat": float(lat),
                "lon": float(lon),
                "centroid_source": src,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    min_v, max_v = float(out["volume"].min()), float(out["volume"].max())
    span = max_v - min_v + 1.0
    if scale.lower().startswith("linear"):
        out["norm"] = (out["volume"] - min_v) / span
    else:
        log_v = np.log1p(out["volume"])
        ln_min, ln_max = float(log_v.min()), float(log_v.max())
        out["norm"] = (log_v - ln_min) / (ln_max - ln_min + 0.1)
    out["radius"] = (6 + out["norm"] * 22).astype(float)
    out["elevation"] = (out["norm"] * 80).astype(float)

    def intensity(v):
        r = (v - min_v) / span
        if r < 0.1:
            return "low"
        if r < 0.3:
            return "medium"
        return "high"

    out["intensity"] = out["volume"].map(intensity)
    return out


@app.get("/api/map")
def map_data(
    states: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    depth: str = "all",
    scale: str = "log",
    mode: str = "2d",
):
    enrol, _, _ = ds.filter_frames(_parse_states(states), start, end)
    if enrol.empty:
        return {"points": [], "min": 0, "max": 0, "legend": {}, "kpis": {}, "centroid_sources": {}, "mode": mode}

    vol = _vol(enrol)
    frame = _map_frame(enrol, depth, scale)
    points = ds.df_records(frame)
    min_v = float(frame["volume"].min()) if not frame.empty else 0
    max_v = float(frame["volume"].max()) if not frame.empty else 0
    span = max_v - min_v + 1.0
    vol_by_d = enrol.groupby(enrol["district"].astype(str), observed=True)[vol].sum()
    hotspot = str(vol_by_d.idxmax()) if not vol_by_d.empty else "—"
    src_counts = frame["centroid_source"].value_counts().to_dict() if not frame.empty else {}

    return ds._json_safe(
        {
            "points": points,
            "min": min_v,
            "max": max_v,
            "legend": {
                "low_max": min_v + 0.1 * span,
                "medium_max": min_v + 0.3 * span,
                "labels": ["Low", "Medium", "High"],
            },
            "count": len(points),
            "mode": mode,
            "scale": scale,
            "kpis": {
                "visible_volume": float(enrol[vol].sum()),
                "hotspot": hotspot,
                "districts": int(enrol["district"].nunique()) if "district" in enrol.columns else 0,
            },
            "centroid_sources": src_counts,
        }
    )


@app.get("/api/map/export/{kind}")
def map_export(
    kind: str,
    states: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    depth: str = "all",
    scale: str = "log",
):
    enrol, _, _ = ds.filter_frames(_parse_states(states), start, end)
    frame = _map_frame(enrol, depth, scale)
    if frame.empty:
        raise HTTPException(400, "No map data")
    export = frame.drop(columns=[c for c in ("norm", "radius", "elevation") if c in frame.columns], errors="ignore")
    kind = kind.lower()
    if kind in ("full", "all"):
        return _csv_response(export, "map_data.csv")
    if kind in ("top20", "top_districts"):
        return _csv_response(export.sort_values("volume", ascending=False).head(20), "top_districts.csv")
    if kind in ("top10", "top_states"):
        top = export.groupby("state", as_index=False)["volume"].sum().nlargest(10, "volume")
        return _csv_response(top, "top_states.csv")
    raise HTTPException(404, "Unknown map export")


@app.get("/api/geojson")
def geojson():
    g = ds.load_geojson()
    if not g:
        raise HTTPException(404, "GeoJSON not found")
    return g


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------


class MergeItem(BaseModel):
    scope: str
    original: str
    target: Optional[str] = None
    action: str = "Merge"


class MergeBatch(BaseModel):
    items: List[MergeItem]


class RevertBody(BaseModel):
    ids: List[str]


@app.get("/api/governance")
def governance_status():
    data = ds.ensure_loaded()
    audit = gstore.load_audit_log()
    return ds._json_safe(
        {
            "state_patches": data["state_patches"],
            "district_patches": data["district_patches"],
            "state_deletions": data["state_deletions"],
            "district_deletions": data["district_deletions"],
            "audit": ds.df_records(audit) if audit is not None and not audit.empty else [],
            "store_path": str(gstore.GOVERNANCE_FILE),
            "official_states": __import__("src.geo.normalize", fromlist=["load_official_states"]).load_official_states(),
        }
    )


@app.get("/api/governance/scan")
def governance_scan(scope: str = Query("states")):
    from src.modules.data_admin import find_district_discrepancies, find_state_discrepancies

    data = ds.ensure_loaded()
    if scope == "states":
        issues = find_state_discrepancies(data["enrol"])
    else:
        gov_df = data["enrol"]
        dim = data.get("dim_geo")
        if dim is not None and not dim.empty and "pincode" not in gov_df.columns:
            gov_df = dim.copy()
            if "total_enrolments" not in gov_df.columns:
                gov_df["total_enrolments"] = 1
        issues = find_district_discrepancies(gov_df)

    patches = data["state_patches"] if scope == "states" else data["district_patches"]
    dels = data["state_deletions"] if scope == "states" else data["district_deletions"]
    if issues is not None and not issues.empty:
        issues = issues[
            (~issues["Suspect"].astype(str).isin(patches.keys()))
            & (~issues["Suspect"].astype(str).isin(dels))
        ]
    return {"scope": scope, "issues": ds.df_records(issues) if issues is not None else []}


@app.post("/api/governance/apply")
def governance_apply(batch: MergeBatch):
    data = ds.ensure_loaded()
    state_p = dict(data["state_patches"])
    dist_p = dict(data["district_patches"])
    state_d = list(data["state_deletions"])
    dist_d = list(data["district_deletions"])
    log_rows = []

    for item in batch.items:
        if item.action == "Ignore":
            continue
        is_state = item.scope.lower().startswith("state")
        if is_state:
            if item.action == "Merge" and item.target:
                state_p[item.original] = item.target
            elif item.action == "Delete":
                if item.original not in state_d:
                    state_d.append(item.original)
            scope_label = "State"
        else:
            if item.action == "Merge" and item.target:
                dist_p[item.original] = item.target
            elif item.action == "Delete":
                if item.original not in dist_d:
                    dist_d.append(item.original)
            scope_label = "District"
        log_rows.append(
            {
                "ID": str(uuid.uuid4()),
                "Timestamp": datetime.datetime.now(),
                "Scope": scope_label,
                "Action": item.action,
                "Original": item.original,
                "Target": item.target if item.action == "Merge" else "N/A",
                "User": "Web_UI",
            }
        )

    gstore.save_store(state_p, dist_p, state_d, dist_d)
    if log_rows:
        prev = gstore.load_audit_log()
        new = pd.DataFrame(log_rows)
        gstore.save_audit_log(pd.concat([prev, new], ignore_index=True) if not prev.empty else new)
    ds.reload_data()
    return {"applied": len(log_rows), "meta": meta()}


@app.post("/api/governance/revert")
def governance_revert(body: RevertBody):
    data = ds.ensure_loaded()
    audit = gstore.load_audit_log()
    if audit is None or audit.empty:
        return {"reverted": 0}
    ids = set(body.ids or [])
    to_process = audit[audit["ID"].isin(ids)]
    state_p = dict(data["state_patches"])
    dist_p = dict(data["district_patches"])
    state_d = list(data["state_deletions"])
    dist_d = list(data["district_deletions"])

    for _, row in to_process.iterrows():
        scope, action, orig = row["Scope"], row["Action"], row["Original"]
        if scope == "State":
            if action == "Merge" and orig in state_p:
                del state_p[orig]
            elif action == "Delete" and orig in state_d:
                state_d.remove(orig)
        else:
            if action == "Merge" and orig in dist_p:
                del dist_p[orig]
            elif action == "Delete" and orig in dist_d:
                dist_d.remove(orig)

    remaining = audit[~audit["ID"].isin(ids)]
    gstore.save_store(state_p, dist_p, state_d, dist_d)
    gstore.save_audit_log(remaining)
    ds.reload_data()
    return {"reverted": int(len(to_process)), "meta": meta()}


@app.get("/api/governance/export-pack")
def governance_export_pack():
    data = ds.ensure_loaded()
    audit = gstore.load_audit_log()
    pack = gstore.export_pack(
        data["state_patches"],
        data["district_patches"],
        data["state_deletions"],
        data["district_deletions"],
        audit,
    )
    return Response(
        content=pack,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="governance_pack.json"'},
    )


@app.get("/api/governance/export-audit")
def governance_export_audit():
    audit = gstore.load_audit_log()
    return _csv_response(audit if audit is not None else pd.DataFrame(), "governance_audit.csv")


@app.post("/api/governance/import-pack")
def governance_import_pack(payload: Dict[str, Any] = Body(...)):
    # Accept full pack JSON body
    data = gstore.import_pack(json.dumps(payload))
    gstore.save_store(
        data["state_patches"],
        data["district_patches"],
        data["state_deletions"],
        data["district_deletions"],
    )
    if data.get("audit"):
        adf = pd.DataFrame(data["audit"])
        if "Timestamp" in adf.columns:
            adf["Timestamp"] = pd.to_datetime(adf["Timestamp"], errors="coerce")
        gstore.save_audit_log(adf)
    ds.reload_data()
    return {"ok": True, "meta": meta()}


@app.get("/api/insights/governance")
def insights_governance(scope: str = "states"):
    from src.modules.data_admin import find_district_discrepancies, find_state_discrepancies

    data = ds.ensure_loaded()
    if scope == "districts":
        issues = find_district_discrepancies(
            data.get("dim_geo") if data.get("dim_geo") is not None else data["enrol"]
        )
    else:
        issues = find_state_discrepancies(data["enrol"])
    eng = ds.engine_for()
    text = eng.generate_governance_insight(issues if issues is not None else pd.DataFrame(), use_llm=True)
    return {"markdown": text}


# ---------------------------------------------------------------------------
# Static SPA
# ---------------------------------------------------------------------------

if DIST.exists():
    assets = DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/")
    def spa_index():
        return FileResponse(DIST / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(404)
        candidate = DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
