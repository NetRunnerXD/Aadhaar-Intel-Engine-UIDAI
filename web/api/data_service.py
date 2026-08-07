# -*- coding: utf-8 -*-
"""Shared data load + filter helpers for the web API (reuses Streamlit stack)."""
from __future__ import annotations

import json
import threading
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.ai.ollama_client import get_ollama_client
from src.ai_core import AnalyticsEngine
from src.config import DATA_DIR, GEOJSON_PATH, MARTS_ONLY, PROCESSED_DIR
from src.data_manager import DataLoader
from src.modules import data_admin
from src.services import governance_store as gstore

_lock = threading.RLock()
_cache: Dict[str, Any] = {}


def _json_safe(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date, pd.Timestamp)):
        return str(obj)[:10] if hasattr(obj, "date") else str(obj)
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, pd.Series):
        return _json_safe(obj.to_dict())
    if pd.isna(obj):
        return None
    try:
        if hasattr(obj, "item"):
            return obj.item()
    except Exception:
        pass
    return str(obj)


def ensure_loaded(force: bool = False) -> Dict[str, Any]:
    with _lock:
        if _cache.get("ready") and not force:
            return _cache
        loader = DataLoader(str(DATA_DIR), processed_path=PROCESSED_DIR, prefer_cache=True)
        enrol, demo, bio, logs = loader.get_data()

        # Apply durable governance patches (same as Streamlit path)
        store = gstore.load_store()
        state_patches = dict(store.get("state_patches") or {})
        district_patches = dict(store.get("district_patches") or {})
        state_dels = list(store.get("state_deletions") or [])
        district_dels = list(store.get("district_deletions") or [])

        def _apply(df: pd.DataFrame) -> pd.DataFrame:
            if df is None or df.empty:
                return df if df is not None else pd.DataFrame()
            out = df.copy()
            if state_patches and "state" in out.columns:
                out["state"] = out["state"].astype(str).replace(state_patches)
            if district_patches and "district" in out.columns:
                out["district"] = out["district"].astype(str).replace(district_patches)
            if state_dels and "state" in out.columns:
                out = out[~out["state"].astype(str).isin(state_dels)]
            if district_dels and "district" in out.columns:
                out = out[~out["district"].astype(str).isin(district_dels)]
            return out

        enrol_c = _apply(enrol)
        demo_c = _apply(demo)
        bio_c = _apply(bio)

        _cache.clear()
        _cache.update(
            {
                "ready": True,
                "enrol": enrol_c,
                "demo": demo_c,
                "bio": bio_c,
                "raw_enrol": enrol,
                "raw_demo": demo,
                "raw_bio": bio,
                "logs": logs or [],
                "load_report": loader.load_report or {},
                "dim_geo": loader.dim_geo,
                "agg_district": loader.agg_district,
                "source": loader.source,
                "state_patches": state_patches,
                "district_patches": district_patches,
                "state_deletions": state_dels,
                "district_deletions": district_dels,
            }
        )
        return _cache


def reload_data() -> Dict[str, Any]:
    return ensure_loaded(force=True)


def filter_frames(
    states: Optional[List[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = ensure_loaded()
    enrol, demo, bio = data["enrol"].copy(), data["demo"].copy(), data["bio"].copy()

    def _filt(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()
        out = df
        if states and "state" in out.columns:
            out = out[out["state"].astype(str).isin([str(s) for s in states])]
        if (start or end) and "date" in out.columns:
            d = pd.to_datetime(out["date"], errors="coerce")
            if start:
                out = out[d >= pd.Timestamp(start)]
            if end:
                out = out[d <= pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)]
        return out

    return _filt(enrol), _filt(demo), _filt(bio)


def engine_for(
    states: Optional[List[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> AnalyticsEngine:
    e, d, b = filter_frames(states, start, end)
    return AnalyticsEngine(e, d, b)


def meta_payload() -> Dict[str, Any]:
    data = ensure_loaded()
    enrol = data["enrol"]
    states = sorted(enrol["state"].astype(str).unique().tolist()) if not enrol.empty and "state" in enrol.columns else []
    min_d = max_d = None
    if not enrol.empty and "date" in enrol.columns:
        dates = pd.to_datetime(enrol["date"], errors="coerce").dropna()
        if not dates.empty:
            min_d = str(dates.min().date())
            max_d = str(dates.max().date())
    ollama = get_ollama_client().status()
    return _json_safe(
        {
            "source": data["source"],
            "marts_only": MARTS_ONLY,
            "states": states,
            "date_min": min_d,
            "date_max": max_d,
            "rows": {
                "enrol": int(len(data["enrol"])),
                "bio": int(len(data["bio"])),
                "demo": int(len(data["demo"])),
            },
            "llm": {
                "available": ollama.available,
                "model": ollama.model,
                "error": ollama.error,
            },
            "load_report": data["load_report"],
            "governance": {
                "state_merges": len(data["state_patches"]),
                "district_merges": len(data["district_patches"]),
            },
        }
    )


def load_geojson() -> Optional[dict]:
    path = Path(GEOJSON_PATH)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def df_records(df: pd.DataFrame, limit: Optional[int] = None) -> List[dict]:
    if df is None or df.empty:
        return []
    out = df.head(limit) if limit else df
    # Convert timestamps
    records = out.copy()
    for col in records.columns:
        if pd.api.types.is_datetime64_any_dtype(records[col]):
            records[col] = records[col].astype(str)
    return _json_safe(records.to_dict(orient="records"))
