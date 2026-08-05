"""
Build processed parquet marts from raw CSV shards.

Usage:
    python -m src.etl.build_cache
    python -m src.etl.build_cache --force
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.config import (
    CACHE_SCHEMA_VERSION,
    DAILY_KEY,
    DATA_DIR,
    MANIFEST_PATH,
    MART_AGG_DISTRICT,
    MART_BIO_DAILY,
    MART_DEMO_DAILY,
    MART_DIM_GEO,
    MART_ENROL_DAILY,
    PROCESSED_DIR,
)
from src.data_manager import (
    BIO_NUMERIC,
    DEMO_NUMERIC,
    ENROL_NUMERIC,
    DataLoader,
)


def list_csv_files(data_dir: Path) -> List[Path]:
    if not data_dir.exists():
        return []
    return sorted(p for p in data_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv")


def source_fingerprint(data_dir: Path) -> str:
    """
    Stable fingerprint of raw CSV inputs (name + size + mtime_ns).
    Does not hash full file contents (too slow for 200MB+).
    """
    h = hashlib.sha256()
    h.update(str(CACHE_SCHEMA_VERSION).encode())
    for path in list_csv_files(data_dir):
        st = path.stat()
        h.update(path.name.encode("utf-8"))
        h.update(str(st.st_size).encode())
        h.update(str(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))).encode())
    return h.hexdigest()


def mart_paths(processed_dir: Path) -> Dict[str, Path]:
    return {
        "enrol_daily": processed_dir / MART_ENROL_DAILY,
        "bio_daily": processed_dir / MART_BIO_DAILY,
        "demo_daily": processed_dir / MART_DEMO_DAILY,
        "agg_district": processed_dir / MART_AGG_DISTRICT,
        "dim_geo": processed_dir / MART_DIM_GEO,
        "manifest": processed_dir / MANIFEST_PATH.name,
    }


def cache_is_valid(data_dir: Path = DATA_DIR, processed_dir: Path = PROCESSED_DIR) -> bool:
    paths = mart_paths(processed_dir)
    required = ["enrol_daily", "bio_daily", "demo_daily", "agg_district", "dim_geo", "manifest"]
    if not all(paths[k].exists() for k in required):
        return False
    try:
        with open(paths["manifest"], encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    if manifest.get("schema_version") != CACHE_SCHEMA_VERSION:
        return False
    expected = source_fingerprint(data_dir)
    return manifest.get("source_fingerprint") == expected


def _to_daily(df: pd.DataFrame, value_cols: List[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=DAILY_KEY + value_cols)
    keys = [c for c in DAILY_KEY if c in df.columns]
    vals = [c for c in value_cols if c in df.columns]
    if not keys or not vals:
        return df
    out = df.groupby(keys, as_index=False, observed=True)[vals].sum()
    return out


def _build_dim_geo(enrol: pd.DataFrame, bio: pd.DataFrame, demo: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for df in (enrol, bio, demo):
        if df is None or df.empty:
            continue
        cols = [c for c in ("state", "district", "pincode") if c in df.columns]
        if len(cols) < 2:
            continue
        frames.append(df[cols].drop_duplicates())
    if not frames:
        return pd.DataFrame(columns=["state", "district", "pincode"])
    geo = pd.concat(frames, ignore_index=True).drop_duplicates()
    for col in ("state", "district"):
        if col in geo.columns:
            geo[col] = geo[col].astype(str)
    if "pincode" in geo.columns:
        geo["pincode"] = pd.to_numeric(geo["pincode"], errors="coerce").fillna(0).astype(int)
    return geo


def _build_agg_district(enrol_daily: pd.DataFrame) -> pd.DataFrame:
    if enrol_daily is None or enrol_daily.empty:
        return pd.DataFrame(columns=["state", "district", "total_enrolments", "adult_enrolments"])
    vals = [c for c in ("total_enrolments", "adult_enrolments", "age_0_5", "age_5_17", "age_18_greater") if c in enrol_daily.columns]
    keys = [c for c in ("state", "district") if c in enrol_daily.columns]
    return enrol_daily.groupby(keys, as_index=False, observed=True)[vals].sum()


def _optimize_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for col in out.select_dtypes(include=["float64"]).columns:
        out[col] = pd.to_numeric(out[col], downcast="float")
    for col in out.select_dtypes(include=["int64"]).columns:
        out[col] = pd.to_numeric(out[col], downcast="integer")
    for col in ("state", "district"):
        if col in out.columns:
            out[col] = out[col].astype("category")
    return out


def build_marts_from_frames(
    enrol: pd.DataFrame,
    demo: pd.DataFrame,
    bio: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    enrol_daily = _optimize_for_parquet(_to_daily(enrol, ENROL_NUMERIC))
    bio_daily = _optimize_for_parquet(_to_daily(bio, BIO_NUMERIC))
    demo_daily = _optimize_for_parquet(_to_daily(demo, DEMO_NUMERIC))
    dim_geo = _optimize_for_parquet(_build_dim_geo(enrol, bio, demo))
    agg_district = _optimize_for_parquet(_build_agg_district(enrol_daily))
    return {
        "enrol_daily": enrol_daily,
        "bio_daily": bio_daily,
        "demo_daily": demo_daily,
        "dim_geo": dim_geo,
        "agg_district": agg_district,
    }


def write_marts(
    marts: Dict[str, pd.DataFrame],
    processed_dir: Path,
    fingerprint: str,
    load_report: Optional[Dict[str, Any]] = None,
    build_seconds: float = 0.0,
) -> Path:
    processed_dir.mkdir(parents=True, exist_ok=True)
    paths = mart_paths(processed_dir)

    marts["enrol_daily"].to_parquet(paths["enrol_daily"], index=False)
    marts["bio_daily"].to_parquet(paths["bio_daily"], index=False)
    marts["demo_daily"].to_parquet(paths["demo_daily"], index=False)
    marts["agg_district"].to_parquet(paths["agg_district"], index=False)
    marts["dim_geo"].to_parquet(paths["dim_geo"], index=False)

    manifest = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "source_fingerprint": fingerprint,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "build_seconds": round(build_seconds, 3),
        "row_counts": {k: int(len(v)) for k, v in marts.items()},
        "files": {k: paths[k].name for k in ("enrol_daily", "bio_daily", "demo_daily", "agg_district", "dim_geo")},
        "load_report": load_report or {},
    }
    with open(paths["manifest"], "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    return paths["manifest"]


def build_cache(
    data_dir: Path = DATA_DIR,
    processed_dir: Path = PROCESSED_DIR,
    force: bool = False,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any]]:
    """
    Process CSVs and write parquet marts.
    Returns (marts, summary).
    """
    data_dir = Path(data_dir)
    processed_dir = Path(processed_dir)
    fp = source_fingerprint(data_dir)

    if not force and cache_is_valid(data_dir, processed_dir):
        marts = load_marts(processed_dir)
        return marts, {"status": "skipped", "reason": "cache_valid", "fingerprint": fp}

    t0 = time.time()
    loader = DataLoader(str(data_dir))
    enrol, demo, bio, logs = loader._load_from_csv()  # pin-level clean
    marts = build_marts_from_frames(enrol, demo, bio)
    elapsed = time.time() - t0
    write_marts(marts, processed_dir, fp, load_report=loader.load_report, build_seconds=elapsed)

    summary = {
        "status": "built",
        "fingerprint": fp,
        "build_seconds": round(elapsed, 3),
        "row_counts": {k: int(len(v)) for k, v in marts.items()},
        "logs": logs,
        "load_report": loader.load_report,
    }
    return marts, summary


def load_marts(processed_dir: Path = PROCESSED_DIR) -> Dict[str, pd.DataFrame]:
    paths = mart_paths(processed_dir)
    def _read(p: Path) -> pd.DataFrame:
        df = pd.read_parquet(p)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df

    return {
        "enrol_daily": _read(paths["enrol_daily"]),
        "bio_daily": _read(paths["bio_daily"]),
        "demo_daily": _read(paths["demo_daily"]),
        "agg_district": _read(paths["agg_district"]),
        "dim_geo": _read(paths["dim_geo"]),
    }


def load_manifest(processed_dir: Path = PROCESSED_DIR) -> Dict[str, Any]:
    path = mart_paths(processed_dir)["manifest"]
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build Aadhaar Intel processed parquet marts")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--force", action="store_true", help="Rebuild even if cache is valid")
    args = parser.parse_args(argv)

    print(f"Data dir:      {args.data_dir}")
    print(f"Processed dir: {args.processed_dir}")
    print(f"Force:         {args.force}")
    print(f"Fingerprint:   {source_fingerprint(args.data_dir)[:16]}...")

    marts, summary = build_cache(args.data_dir, args.processed_dir, force=args.force)
    print(f"Status: {summary['status']}")
    if summary.get("build_seconds") is not None:
        print(f"Build seconds: {summary.get('build_seconds')}")
    print("Row counts:")
    for k, n in summary.get("row_counts", {k: len(v) for k, v in marts.items()}).items():
        print(f"  {k}: {n:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
