"""Data loading, validation, normalization, de-duplication, and cache access."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.config import (
    AUTO_BUILD_CACHE,
    DATA_DIR,
    MARTS_ONLY,
    NATURAL_KEY,
    PINCODE_MAX,
    PINCODE_MIN,
    PROCESSED_DIR,
)
from src.geo.normalize import apply_state_canonicalization, load_official_states
from src.geo.repair import full_geo_repair

# Column schemas returned to the app (stable empty frames)
ENROL_COLS = [
    "date", "state", "district", "pincode",
    "age_0_5", "age_5_17", "age_18_greater",
    "adult_enrolments", "total_enrolments",
]
BIO_COLS = ["date", "state", "district", "pincode", "bio_age_5_17", "bio_age_17_", "bio_stress"]
DEMO_COLS = ["date", "state", "district", "pincode", "demo_age_5_17", "demo_age_17_", "update_volume"]

# Daily marts omit pincode
ENROL_DAILY_COLS = [
    "date", "state", "district",
    "age_0_5", "age_5_17", "age_18_greater",
    "adult_enrolments", "total_enrolments",
]
BIO_DAILY_COLS = ["date", "state", "district", "bio_age_5_17", "bio_age_17_", "bio_stress"]
DEMO_DAILY_COLS = ["date", "state", "district", "demo_age_5_17", "demo_age_17_", "update_volume"]

ENROL_NUMERIC = ["age_0_5", "age_5_17", "age_18_greater", "adult_enrolments", "total_enrolments"]
BIO_NUMERIC = ["bio_age_5_17", "bio_age_17_", "bio_stress"]
DEMO_NUMERIC = ["demo_age_5_17", "demo_age_17_", "update_volume"]


def empty_enrol(daily: bool = False) -> pd.DataFrame:
    return pd.DataFrame(columns=ENROL_DAILY_COLS if daily else ENROL_COLS)


def empty_bio(daily: bool = False) -> pd.DataFrame:
    return pd.DataFrame(columns=BIO_DAILY_COLS if daily else BIO_COLS)


def empty_demo(daily: bool = False) -> pd.DataFrame:
    return pd.DataFrame(columns=DEMO_DAILY_COLS if daily else DEMO_COLS)


class DataLoader:
    def __init__(self, data_path=None, processed_path=None, prefer_cache: bool = True):
        self.data_path = os.path.normpath(str(data_path or DATA_DIR))
        self.processed_path = Path(processed_path or PROCESSED_DIR)
        self.prefer_cache = prefer_cache
        self.source: str = "none"  # cache | csv | none
        self.dim_geo: pd.DataFrame = pd.DataFrame(columns=["state", "district", "pincode"])
        self.agg_district: pd.DataFrame = pd.DataFrame()
        self.manifest: Dict = {}
        self.load_report: Dict = {
            "files_seen": 0,
            "files_loaded": 0,
            "files_skipped": [],
            "rows_raw": {"enrol": 0, "bio": 0, "demo": 0},
            "rows_after_dedup": {"enrol": 0, "bio": 0, "demo": 0},
            "rows_quarantined": {"enrol": 0, "bio": 0, "demo": 0},
            "duplicate_keys_collapsed": {"enrol": 0, "bio": 0, "demo": 0},
            "unknown_states": [],
            "district_as_state_repairs": {},
            "geo_repair_stats": {
                "district_as_state": 0,
                "district_aliases": 0,
                "ap_to_telangana": 0,
            },
            "errors": [],
            "warnings": [],
            "source": "none",
            "cache_valid": False,
        }

    @staticmethod
    def _optimize(df: pd.DataFrame) -> pd.DataFrame:
        """Downcast numerics and category-encode geography."""
        if df is None or df.empty:
            return df
        for col in df.select_dtypes(include=["float64"]).columns:
            df[col] = pd.to_numeric(df[col], downcast="float")
        for col in df.select_dtypes(include=["int64"]).columns:
            df[col] = pd.to_numeric(df[col], downcast="integer")
        for col in ("state", "district"):
            if col in df.columns:
                df[col] = df[col].astype("category")
        return df

    def _classify(self, cols: List[str]) -> str | None:
        cols = [c.lower().strip() for c in cols]
        if any("bio_age" in c for c in cols):
            return "bio"
        if any("demo_age" in c for c in cols):
            return "demo"
        if any(c in ("age_0_5", "age_18_greater", "age_5_17") for c in cols):
            return "enrol"
        return None

    def _standardize_geo_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
        if "state" in df.columns:
            df["state"] = apply_state_canonicalization(df["state"].astype(str))
        if "district" in df.columns:
            df["district"] = (
                df["district"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True).str.title()
            )
        if "pincode" in df.columns:
            df["pincode"] = pd.to_numeric(df["pincode"], errors="coerce").fillna(0).astype(int)
        return df

    def _repair_geo(self, df: pd.DataFrame, kind: str) -> pd.DataFrame:
        """District-as-state, district aliases, AP→Telangana boundary fixes."""
        if df is None or df.empty:
            return df
        repaired, stats = full_geo_repair(df)
        bucket = self.load_report.setdefault("geo_repair_stats", {})
        for k, v in stats.items():
            bucket[k] = int(bucket.get(k, 0)) + int(v)
        if stats.get("district_as_state"):
            self.load_report["warnings"].append(
                f"{kind}: repaired {stats['district_as_state']:,} district-as-state rows"
            )
        if stats.get("district_aliases"):
            self.load_report["warnings"].append(
                f"{kind}: applied {stats['district_aliases']:,} district alias normalizations"
            )
        if stats.get("ap_to_telangana"):
            self.load_report["warnings"].append(
                f"{kind}: reassigned {stats['ap_to_telangana']:,} AP→Telangana district rows"
            )
        # keep legacy key for UI
        if stats.get("district_as_state"):
            self.load_report.setdefault("district_as_state_repairs", {})
            self.load_report["district_as_state_repairs"][kind] = int(stats["district_as_state"])
        return repaired

    def _quarantine_invalid(self, df: pd.DataFrame, kind: str) -> pd.DataFrame:
        if df.empty:
            return df
        before = len(df)
        mask = pd.Series(True, index=df.index)
        official = set(load_official_states())

        if "date" in df.columns:
            mask &= df["date"].notna()

        if "pincode" in df.columns:
            pin_ok = (df["pincode"] >= PINCODE_MIN) & (df["pincode"] <= PINCODE_MAX)
            mask &= pin_ok

        if "state" in df.columns:
            st = df["state"].astype(str)
            # Drop Unknown and any remaining non-official states (true garbage)
            mask &= st.ne("Unknown") & st.isin(official)

        cleaned = df.loc[mask].copy()
        dropped = before - len(cleaned)
        self.load_report["rows_quarantined"][kind] = int(
            self.load_report["rows_quarantined"].get(kind, 0)
        ) + dropped
        if dropped:
            self.load_report["warnings"].append(
                f"{kind}: quarantined {dropped:,} rows (bad date/pincode/non-official state)"
            )
        return cleaned

    def _dedup_aggregate(self, df: pd.DataFrame, value_cols: List[str], kind: str) -> pd.DataFrame:
        if df.empty:
            return df
        key = [c for c in NATURAL_KEY if c in df.columns]
        if len(key) < 4:
            return df
        before = len(df)
        present_vals = [c for c in value_cols if c in df.columns]
        if not present_vals:
            return df.drop_duplicates(subset=key, keep="first")
        agg = df.groupby(key, as_index=False, observed=True)[present_vals].sum()
        collapsed = before - len(agg)
        self.load_report["duplicate_keys_collapsed"][kind] = max(0, collapsed)
        self.load_report["rows_after_dedup"][kind] = len(agg)
        if collapsed > 0:
            self.load_report["warnings"].append(
                f"{kind}: collapsed {collapsed:,} duplicate key rows by sum"
            )
        return agg

    def _process_enrol(self, frames: List[pd.DataFrame]) -> pd.DataFrame:
        if not frames:
            return empty_enrol(daily=False)
        raw = pd.concat(frames, ignore_index=True)
        raw.columns = raw.columns.str.lower().str.strip()
        self.load_report["rows_raw"]["enrol"] = len(raw)

        for c in ("age_0_5", "age_5_17", "age_18_greater"):
            if c not in raw.columns:
                raw[c] = 0
            raw[c] = pd.to_numeric(raw[c], errors="coerce").fillna(0)

        raw["adult_enrolments"] = raw["age_18_greater"]
        raw["total_enrolments"] = raw["age_0_5"] + raw["age_5_17"] + raw["age_18_greater"]

        for c in ("date", "state", "district", "pincode"):
            if c not in raw.columns:
                raw[c] = np.nan if c == "date" else (0 if c == "pincode" else "")
        df = raw[ENROL_COLS].copy()
        df = self._standardize_geo_dates(df)
        df = self._repair_geo(df, "enrol")
        df = self._quarantine_invalid(df, "enrol")
        df = self._dedup_aggregate(df, ENROL_NUMERIC, "enrol")
        return self._optimize(df)

    def _process_bio(self, frames: List[pd.DataFrame]) -> pd.DataFrame:
        if not frames:
            return empty_bio(daily=False)
        raw = pd.concat(frames, ignore_index=True)
        raw.columns = raw.columns.str.lower().str.strip()
        self.load_report["rows_raw"]["bio"] = len(raw)

        for c in ("bio_age_5_17", "bio_age_17_"):
            if c not in raw.columns:
                raw[c] = 0
            raw[c] = pd.to_numeric(raw[c], errors="coerce").fillna(0)
        raw["bio_stress"] = raw["bio_age_5_17"] + raw["bio_age_17_"]

        for c in ("date", "state", "district", "pincode"):
            if c not in raw.columns:
                raw[c] = np.nan if c == "date" else (0 if c == "pincode" else "")
        df = raw[BIO_COLS].copy()
        df = self._standardize_geo_dates(df)
        df = self._repair_geo(df, "bio")
        df = self._quarantine_invalid(df, "bio")
        df = self._dedup_aggregate(df, BIO_NUMERIC, "bio")
        return self._optimize(df)

    def _process_demo(self, frames: List[pd.DataFrame]) -> pd.DataFrame:
        if not frames:
            return empty_demo(daily=False)
        raw = pd.concat(frames, ignore_index=True)
        raw.columns = raw.columns.str.lower().str.strip()
        self.load_report["rows_raw"]["demo"] = len(raw)

        for c in ("demo_age_5_17", "demo_age_17_"):
            if c not in raw.columns:
                raw[c] = 0
            raw[c] = pd.to_numeric(raw[c], errors="coerce").fillna(0)
        raw["update_volume"] = raw["demo_age_5_17"] + raw["demo_age_17_"]

        for c in ("date", "state", "district", "pincode"):
            if c not in raw.columns:
                raw[c] = np.nan if c == "date" else (0 if c == "pincode" else "")
        df = raw[DEMO_COLS].copy()
        df = self._standardize_geo_dates(df)
        df = self._repair_geo(df, "demo")
        df = self._quarantine_invalid(df, "demo")
        df = self._dedup_aggregate(df, DEMO_NUMERIC, "demo")
        return self._optimize(df)

    def _record_unknown_states(self, *dfs: pd.DataFrame) -> None:
        official = set(load_official_states())
        unknown = set()
        for df in dfs:
            if df is None or df.empty or "state" not in df.columns:
                continue
            states = df["state"].astype(str).unique()
            for s in states:
                if s not in official and s != "Unknown":
                    unknown.add(s)
        self.load_report["unknown_states"] = sorted(unknown)
        if unknown:
            self.load_report["warnings"].append(
                f"{len(unknown)} non-official state labels remain after normalization"
            )

    def _load_from_csv(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[str]]:
        """Pin-level clean load from CSV shards (used by ETL and CSV fallback)."""
        logs: List[str] = []
        datasets: Dict[str, List[pd.DataFrame]] = {"enrol": [], "bio": [], "demo": []}

        if not os.path.exists(self.data_path):
            msg = f"Error: Data path not found: {self.data_path}"
            logs.append(msg)
            self.load_report["errors"].append(msg)
            return empty_enrol(False), empty_demo(False), empty_bio(False), logs

        files = [f for f in os.listdir(self.data_path) if f.lower().endswith(".csv")]
        self.load_report["files_seen"] = len(files)
        logs.append(f"Loading {len(files)} CSV files from {self.data_path}...")

        for f in files:
            path = os.path.join(self.data_path, f)
            try:
                cols = list(pd.read_csv(path, nrows=0).columns)
                kind = self._classify(cols)
                if not kind:
                    self.load_report["files_skipped"].append(f)
                    logs.append(f"Skipped (unknown schema): {f}")
                    continue
                datasets[kind].append(pd.read_csv(path, low_memory=False))
                self.load_report["files_loaded"] += 1
            except Exception as e:
                self.load_report["files_skipped"].append(f)
                self.load_report["errors"].append(f"{f}: {e}")
                logs.append(f"Skipped {f}: {e}")

        df_enrol = self._process_enrol(datasets["enrol"])
        df_bio = self._process_bio(datasets["bio"])
        df_demo = self._process_demo(datasets["demo"])

        if df_bio.empty and not df_enrol.empty:
            df_bio = df_enrol[["date", "state", "district", "pincode"]].copy()
            base = df_enrol["adult_enrolments"] if "adult_enrolments" in df_enrol.columns else 0
            df_bio["bio_age_5_17"] = 0
            df_bio["bio_age_17_"] = (base * 0.4).astype(int)
            df_bio["bio_stress"] = df_bio["bio_age_17_"]
            logs.append("Warning: no biometric files; synthesized bio_stress from enrolments")
            self.load_report["warnings"].append("Synthetic bio data used")

        self._record_unknown_states(df_enrol, df_bio, df_demo)

        for kind, df in (("enrol", df_enrol), ("bio", df_bio), ("demo", df_demo)):
            logs.append(
                f"{kind}: raw={self.load_report['rows_raw'][kind]:,} "
                f"final={len(df):,} quarantined={self.load_report['rows_quarantined'][kind]:,} "
                f"dedup_collapsed={self.load_report['duplicate_keys_collapsed'][kind]:,}"
            )
        if self.load_report["unknown_states"]:
            sample = ", ".join(self.load_report["unknown_states"][:8])
            more = len(self.load_report["unknown_states"]) - 8
            suffix = f" (+{more} more)" if more > 0 else ""
            logs.append(f"Non-official states: {sample}{suffix}")

        self.source = "csv"
        self.load_report["source"] = "csv"
        return df_enrol, df_demo, df_bio, logs

    def _try_load_cache(self) -> Optional[Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[str]]]:
        from src.etl.build_cache import cache_is_valid, load_manifest, load_marts

        data_dir = Path(self.data_path)
        if not cache_is_valid(data_dir, self.processed_path):
            self.load_report["cache_valid"] = False
            return None

        marts = load_marts(self.processed_path)
        self.manifest = load_manifest(self.processed_path)
        self.dim_geo = marts.get("dim_geo", pd.DataFrame())
        self.agg_district = marts.get("agg_district", pd.DataFrame())

        enrol = marts["enrol_daily"]
        bio = marts["bio_daily"]
        demo = marts["demo_daily"]

        # Restore load_report from manifest when present
        saved = self.manifest.get("load_report") or {}
        for key in (
            "rows_raw",
            "rows_quarantined",
            "duplicate_keys_collapsed",
            "unknown_states",
            "district_as_state_repairs",
            "geo_repair_stats",
            "warnings",
            "errors",
            "files_seen",
            "files_loaded",
        ):
            if key in saved:
                self.load_report[key] = saved[key]

        self.source = "cache"
        self.load_report["source"] = "cache"
        self.load_report["cache_valid"] = True
        self.load_report["warnings"] = list(self.load_report.get("warnings") or [])
        self.load_report["warnings"].insert(
            0,
            f"Loaded processed marts from {self.processed_path} "
            f"(enrol={len(enrol):,}, bio={len(bio):,}, demo={len(demo):,} daily rows)",
        )

        logs = [
            f"Cache hit: {self.processed_path}",
            f"Built at: {self.manifest.get('built_at', 'unknown')}",
            f"enrol_daily={len(enrol):,} bio_daily={len(bio):,} demo_daily={len(demo):,}",
            f"dim_geo={len(self.dim_geo):,} agg_district={len(self.agg_district):,}",
        ]
        if self.load_report.get("unknown_states"):
            sample = ", ".join(self.load_report["unknown_states"][:8])
            logs.append(f"Non-official states: {sample}")
        return enrol, demo, bio, logs

    def _aggregate_to_daily(
        self, enrol: pd.DataFrame, demo: pd.DataFrame, bio: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        from src.etl.build_cache import build_marts_from_frames

        marts = build_marts_from_frames(enrol, demo, bio)
        self.dim_geo = marts["dim_geo"]
        self.agg_district = marts["agg_district"]
        return marts["enrol_daily"], marts["demo_daily"], marts["bio_daily"]

    def get_data(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[str]]:
        """
        Returns analytics-ready frames (daily grain when possible).

        Order: (df_enrol, df_demo, df_bio, logs) — historical app contract.
        """
        # 1) Prefer valid parquet cache
        if self.prefer_cache:
            cached = self._try_load_cache()
            if cached is not None:
                return cached

        # Research / prod: app should not re-parse multi-GB CSV paths
        if MARTS_ONLY:
            msg = (
                "MARTS_ONLY=1 and processed cache is missing or stale. "
                "Run: python -m src.etl.build_cache --force"
            )
            self.load_report["errors"].append(msg)
            self.load_report["source"] = "marts_only_miss"
            return empty_enrol(True), empty_demo(True), empty_bio(True), [msg]

        # 2) CSV path (pin grain), then reduce to daily for the app
        enrol_pin, demo_pin, bio_pin, logs = self._load_from_csv()
        if enrol_pin.empty and demo_pin.empty and bio_pin.empty:
            return empty_enrol(True), empty_demo(True), empty_bio(True), logs

        # 3) Auto-build cache for next cold start
        if AUTO_BUILD_CACHE:
            try:
                from src.etl.build_cache import (
                    build_marts_from_frames,
                    source_fingerprint,
                    write_marts,
                )

                marts = build_marts_from_frames(enrol_pin, demo_pin, bio_pin)
                fp = source_fingerprint(Path(self.data_path))
                write_marts(marts, self.processed_path, fp, load_report=self.load_report)
                self.dim_geo = marts["dim_geo"]
                self.agg_district = marts["agg_district"]
                logs.append(f"Wrote processed cache → {self.processed_path}")
                self.load_report["warnings"].append(f"Cache built at {self.processed_path}")
                self.source = "csv+cache"
                self.load_report["source"] = "csv+cache"
                return marts["enrol_daily"], marts["demo_daily"], marts["bio_daily"], logs
            except Exception as e:
                logs.append(f"Cache build failed (using in-memory daily): {e}")
                self.load_report["warnings"].append(f"Cache build failed: {e}")

        enrol_d, demo_d, bio_d = self._aggregate_to_daily(enrol_pin, demo_pin, bio_pin)
        logs.append(
            f"Serving daily grain in-memory: enrol={len(enrol_d):,} bio={len(bio_d):,} demo={len(demo_d):,}"
        )
        return enrol_d, demo_d, bio_d, logs
