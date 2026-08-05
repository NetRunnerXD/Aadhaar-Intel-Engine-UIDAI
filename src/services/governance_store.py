"""Persist governance patches and audit log across sessions."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.config import OUTPUT_DIR

GOVERNANCE_FILE = OUTPUT_DIR / "governance_patches.json"
AUDIT_FILE = OUTPUT_DIR / "governance_audit.csv"


def _ensure_output() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def default_store() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "state_patches": {},
        "district_patches": {},
        "state_deletions": [],
        "district_deletions": [],
    }


def load_store(path: Path = GOVERNANCE_FILE) -> Dict[str, Any]:
    _ensure_output()
    if not path.exists():
        return default_store()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        base = default_store()
        base.update({k: data.get(k, base[k]) for k in base})
        base["state_patches"] = dict(data.get("state_patches") or {})
        base["district_patches"] = dict(data.get("district_patches") or {})
        base["state_deletions"] = list(data.get("state_deletions") or [])
        base["district_deletions"] = list(data.get("district_deletions") or [])
        return base
    except (OSError, json.JSONDecodeError):
        return default_store()


def save_store(
    state_patches: Dict[str, str],
    district_patches: Dict[str, str],
    state_deletions: List[str],
    district_deletions: List[str],
    path: Path = GOVERNANCE_FILE,
) -> Path:
    _ensure_output()
    payload = {
        "version": 1,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "state_patches": dict(state_patches or {}),
        "district_patches": dict(district_patches or {}),
        "state_deletions": list(state_deletions or []),
        "district_deletions": list(district_deletions or []),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def load_audit_log(path: Path = AUDIT_FILE) -> pd.DataFrame:
    cols = ["ID", "Timestamp", "Scope", "Action", "Original", "Target", "User"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(path)
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        for c in cols:
            if c not in df.columns:
                df[c] = None
        return df[cols]
    except Exception:
        return pd.DataFrame(columns=cols)


def save_audit_log(df: pd.DataFrame, path: Path = AUDIT_FILE) -> Path:
    _ensure_output()
    out = df.copy() if df is not None else pd.DataFrame()
    out.to_csv(path, index=False)
    return path


def export_pack(
    state_patches,
    district_patches,
    state_deletions,
    district_deletions,
    audit_df: Optional[pd.DataFrame] = None,
) -> str:
    pack = {
        "version": 1,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "state_patches": dict(state_patches or {}),
        "district_patches": dict(district_patches or {}),
        "state_deletions": list(state_deletions or []),
        "district_deletions": list(district_deletions or []),
        "audit": (audit_df.to_dict(orient="records") if audit_df is not None and not audit_df.empty else []),
    }
    return json.dumps(pack, indent=2, default=str, ensure_ascii=False)


def import_pack(raw: str) -> Dict[str, Any]:
    data = json.loads(raw)
    return {
        "state_patches": dict(data.get("state_patches") or {}),
        "district_patches": dict(data.get("district_patches") or {}),
        "state_deletions": list(data.get("state_deletions") or []),
        "district_deletions": list(data.get("district_deletions") or []),
        "audit": data.get("audit") or [],
    }
