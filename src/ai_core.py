"""Research analytics: composite-key anomalies + multi-model forecast selection."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.config import (
    ANOMALY_CONTAMINATION,
    ANOMALY_MIN_VOLUME,
    FORECAST_RANDOM_SEED,
)
from src.forecasting import ForecastBackend
from src.geo.centroids import clean_district_name


class AnalyticsEngine:
    def __init__(self, df_enrol, df_demo, df_bio):
        self.df_enrol = self._prep_geo(df_enrol)
        self.df_demo = self._prep_geo(df_demo)
        self.df_bio = self._prep_geo(df_bio)
        self._anomaly_cache: Optional[pd.DataFrame] = None
        self._anomaly_params: Tuple = ()
        self._last_forecast_meta: Dict[str, Any] = {}
        self._model_comparison: List[Dict[str, Any]] = []
        self._forecast_backend = ForecastBackend(seed=FORECAST_RANDOM_SEED)

    @staticmethod
    def _prep_geo(df: Optional[pd.DataFrame]) -> pd.DataFrame:
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()
        out = df.copy()
        if "district" in out.columns:
            # clean ? and punctuation without breaking categories badly
            out["district"] = out["district"].astype(str).map(clean_district_name)
        return out

    def _enrol_volume_col(self) -> str:
        if self.df_enrol.empty:
            return "total_enrolments"
        if "total_enrolments" in self.df_enrol.columns:
            return "total_enrolments"
        if "adult_enrolments" in self.df_enrol.columns:
            return "adult_enrolments"
        return "total_enrolments"

    def get_market_share(self, volume_col: str | None = None):
        if self.df_enrol.empty:
            return pd.DataFrame(columns=["state", "district", "adult_enrolments", "total_enrolments"])
        col = volume_col or self._enrol_volume_col()
        if col not in self.df_enrol.columns:
            return pd.DataFrame()
        gcols = [c for c in ("state", "district") if c in self.df_enrol.columns]
        agg_map = {}
        if "adult_enrolments" in self.df_enrol.columns:
            agg_map["adult_enrolments"] = "sum"
        if "total_enrolments" in self.df_enrol.columns:
            agg_map["total_enrolments"] = "sum"
        if not agg_map:
            agg_map[col] = "sum"
        return self.df_enrol.groupby(gcols, observed=True).agg(agg_map).reset_index()

    def get_correlation(self):
        """Workload by (state, district) — composite key to avoid cross-state name collisions."""
        if self.df_enrol.empty:
            return pd.DataFrame(
                columns=["state", "district", "Enrolments", "Bio_Updates", "Demo_Updates"]
            )
        vol = self._enrol_volume_col()
        gcols = [c for c in ("state", "district") if c in self.df_enrol.columns]
        e = self.df_enrol.groupby(gcols, observed=True)[vol].sum().rename("Enrolments")

        def _g(df, col, name):
            if df is None or df.empty or col not in df.columns:
                return pd.Series(dtype="float64", name=name)
            keys = [c for c in ("state", "district") if c in df.columns]
            return df.groupby(keys, observed=True)[col].sum().rename(name)

        b = _g(self.df_bio, "bio_stress", "Bio_Updates")
        d = _g(self.df_demo, "update_volume", "Demo_Updates")
        merged = pd.concat([e, b, d], axis=1).fillna(0).reset_index()
        for col in ("Enrolments", "Bio_Updates", "Demo_Updates"):
            if col not in merged.columns:
                merged[col] = 0
        return merged

    def _district_feature_matrix(self) -> pd.DataFrame:
        vol = self._enrol_volume_col()
        if self.df_enrol.empty or vol not in self.df_enrol.columns:
            return pd.DataFrame()

        enrol = self.df_enrol.copy()
        if not pd.api.types.is_datetime64_any_dtype(enrol["date"]):
            enrol["date"] = pd.to_datetime(enrol["date"], errors="coerce")

        gcols = [c for c in ("state", "district") if c in enrol.columns]
        totals = enrol.groupby(gcols, observed=True)[vol].sum().rename("volume").reset_index()

        daily = enrol.groupby(gcols + ["date"], observed=True)[vol].sum().reset_index()
        stats = daily.groupby(gcols, observed=True)[vol].agg(["mean", "std", "count"]).reset_index()
        stats["cv"] = stats["std"] / (stats["mean"] + 1.0)
        stats["active_days"] = stats["count"]

        if not daily.empty:
            max_d = daily["date"].max()
            recent = daily[daily["date"] >= max_d - pd.Timedelta(days=30)]
            prior = daily[
                (daily["date"] >= max_d - pd.Timedelta(days=60))
                & (daily["date"] < max_d - pd.Timedelta(days=30))
            ]
            r = recent.groupby(gcols, observed=True)[vol].mean().rename("recent_mean")
            p = prior.groupby(gcols, observed=True)[vol].mean().rename("prior_mean")
            trend = pd.concat([r, p], axis=1).fillna(0).reset_index()
            trend["wow_growth"] = (trend["recent_mean"] - trend["prior_mean"]) / (
                trend["prior_mean"] + 1.0
            )
        else:
            trend = totals[gcols].copy()
            trend["wow_growth"] = 0.0

        corr = self.get_correlation()
        if not corr.empty:
            c2 = corr.rename(
                columns={
                    "Enrolments": "corr_enrol",
                    "Bio_Updates": "bio_updates",
                    "Demo_Updates": "demo_updates",
                }
            )
            join_cols = [c for c in ("state", "district") if c in c2.columns and c in totals.columns]
            totals = totals.merge(
                c2[join_cols + ["bio_updates", "demo_updates"]],
                on=join_cols,
                how="left",
            )
        if "bio_updates" not in totals.columns:
            totals["bio_updates"] = 0.0
        if "demo_updates" not in totals.columns:
            totals["demo_updates"] = 0.0
        totals["bio_updates"] = totals["bio_updates"].fillna(0)
        totals["demo_updates"] = totals["demo_updates"].fillna(0)

        totals["bio_ratio"] = totals["bio_updates"] / (totals["volume"] + 1.0)
        totals["demo_ratio"] = totals["demo_updates"] / (totals["volume"] + 1.0)
        totals["log_volume"] = np.log1p(totals["volume"])

        # peer context: state median volume
        if "state" in totals.columns:
            state_med = totals.groupby("state", observed=True)["volume"].transform("median")
            totals["volume_vs_state_median"] = totals["volume"] / (state_med + 1.0)

        feat = totals.merge(stats[gcols + ["cv", "active_days"]], on=gcols, how="left")
        feat = feat.merge(trend[gcols + ["wow_growth"]], on=gcols, how="left")
        num_cols = feat.select_dtypes(include=["number"]).columns
        feat[num_cols] = feat[num_cols].fillna(0)
        return feat

    def get_anomalies(
        self,
        contamination: float | None = None,
        min_volume: int | None = None,
        force: bool = False,
    ) -> pd.DataFrame:
        contamination = ANOMALY_CONTAMINATION if contamination is None else float(contamination)
        min_volume = ANOMALY_MIN_VOLUME if min_volume is None else int(min_volume)
        params = (contamination, min_volume)
        if self._anomaly_cache is not None and not force and self._anomaly_params == params:
            return self._anomaly_cache

        feat = self._district_feature_matrix()
        empty_cols = [
            "state",
            "district",
            "volume",
            "risk_score",
            "reason",
            "investigation_notes",
        ]
        if feat.empty:
            out = pd.DataFrame(columns=empty_cols)
            self._anomaly_cache, self._anomaly_params = out, params
            return out

        feat = feat[feat["volume"] >= min_volume].copy() if "volume" in feat.columns else feat
        if len(feat) < 10:
            out = feat.copy()
            out["risk_score"] = 0
            out["reason"] = ""
            out["investigation_notes"] = "Insufficient peer cells after min_volume filter"
            self._anomaly_cache, self._anomaly_params = out, params
            return out

        feature_cols = [
            c
            for c in (
                "log_volume",
                "cv",
                "bio_ratio",
                "demo_ratio",
                "wow_growth",
                "active_days",
                "volume_vs_state_median",
            )
            if c in feat.columns
        ]
        X = feat[feature_cols].astype(float).replace([np.inf, -np.inf], 0).fillna(0)
        scaler = StandardScaler()
        Xs = scaler.fit_transform(X)

        iso = IsolationForest(
            contamination=min(max(contamination, 0.01), 0.2),
            random_state=FORECAST_RANDOM_SEED,
            n_estimators=200,
        )
        labels = iso.fit_predict(Xs)
        scores = iso.decision_function(Xs)
        risk_raw = -scores
        risk_norm = (risk_raw - risk_raw.min()) / (risk_raw.max() - risk_raw.min() + 1e-9)

        work = feat.copy()
        work["anomaly"] = labels
        work["risk_score"] = np.where(labels == -1, (risk_norm * 90 + 10).astype(int), 0)
        work["adult_enrolments"] = work["volume"]
        work["total_enrolments"] = work["volume"]

        z = pd.DataFrame(Xs, columns=feature_cols, index=work.index)
        abs_z = z.abs()
        top_feat = abs_z.idxmax(axis=1)
        reason_map = {
            "log_volume": "Unusual total volume vs peers",
            "cv": "High day-to-day volatility",
            "bio_ratio": "Abnormal biometric/enrolment ratio",
            "demo_ratio": "Abnormal demographic/enrolment ratio",
            "wow_growth": "Sharp recent growth/decline",
            "active_days": "Irregular activity footprint",
            "volume_vs_state_median": "Volume far from state median",
        }
        work["reason"] = top_feat.map(reason_map).fillna("Multi-feature outlier")
        work["driver_feature"] = top_feat
        work["driver_z"] = abs_z.max(axis=1).round(2)

        def _note(row):
            return (
                f"Unit=({row.get('state')}, {row.get('district')}); "
                f"volume={row.get('volume')}; bio_ratio={row.get('bio_ratio', 0):.2f}; "
                f"demo_ratio={row.get('demo_ratio', 0):.2f}; cv={row.get('cv', 0):.2f}; "
                f"vs_state_med={row.get('volume_vs_state_median', 0):.2f}; "
                f"driver={row.get('driver_feature')}(|z|={row.get('driver_z')}). "
                f"IsolationForest contamination={contamination}, min_volume={min_volume}."
            )

        work["investigation_notes"] = work.apply(_note, axis=1)

        flagged = work[work["risk_score"] > 0].sort_values("risk_score", ascending=False)
        self._anomaly_cache, self._anomaly_params = flagged, params
        return flagged

    def _daily_series(self, state: Optional[str] = None) -> pd.DataFrame:
        """
        National (or state) daily enrolment series with continuous calendar.
        Zero/missing days are filled — do not drop y==0 (breaks DOW/holiday structure).
        """
        from src.forecasting import complete_daily_calendar

        vol = self._enrol_volume_col()
        if self.df_enrol.empty or vol not in self.df_enrol.columns:
            return pd.DataFrame(columns=["date", "y"])
        df = self.df_enrol.copy()
        if state and "state" in df.columns:
            df = df[df["state"].astype(str) == str(state)]
        if not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        daily = df.groupby("date", observed=True)[vol].sum().sort_index().reset_index()
        daily = daily.dropna(subset=["date"]).rename(columns={vol: "y"})
        daily["y"] = pd.to_numeric(daily["y"], errors="coerce").fillna(0.0).astype(float)
        return complete_daily_calendar(daily)

    def compare_forecast_models(self, holdout_days: int | None = None, candidates: Tuple[str, ...] | None = None):
        """Rolling-origin CV comparison (fallback single holdout)."""
        daily = self._daily_series()
        fb = self._forecast_backend
        df = fb.compare_models(daily, use_rolling=True)
        self._model_comparison = fb.last_comparison
        self._last_forecast_meta = {
            **(self._last_forecast_meta or {}),
            "model_comparison": fb.last_comparison,
        }
        return df

    def select_best_model(self) -> str:
        daily = self._daily_series()
        model, _ = self._forecast_backend.select_model(daily)
        return model

    def backtest_forecast(self, holdout_days: int = 14, model_type: str = "Seasonal") -> Dict[str, Any]:
        daily = self._daily_series()
        return self._forecast_backend.single_holdout(daily, holdout_days, model_type)

    def rolling_forecast_evaluation(self) -> pd.DataFrame:
        return self._forecast_backend.rolling_origin_cv(self._daily_series())

    def forecast_trends(
        self,
        horizon: int = 30,
        model_type: str = "Auto",
        growth_factor: float = 0.0,
        seed: int = FORECAST_RANDOM_SEED,
        state: Optional[str] = None,
    ) -> Tuple[Optional[pd.DataFrame], str]:
        """
        Rolling-CV model selection (beat-MA gate), holiday-aware candidate,
        split-conformal intervals. Optional state-level series.
        """
        try:
            growth_factor = float(growth_factor)
        except (TypeError, ValueError):
            growth_factor = 0.0
        daily = self._daily_series(state=state)
        out, algo = self._forecast_backend.forecast(
            daily, horizon=horizon, model_type=model_type, growth_factor=growth_factor
        )
        self._last_forecast_meta = dict(self._forecast_backend.last_meta)
        if state:
            self._last_forecast_meta["state"] = state
        self._model_comparison = self._forecast_backend.last_comparison
        return out, algo

    def generate_forecast_insight(self, forecast_df, model_type, use_llm: bool = True) -> str:
        if forecast_df is None or forecast_df.empty:
            return "Insufficient data for insight."
        start, end = float(forecast_df.iloc[0]["predicted"]), float(forecast_df.iloc[-1]["predicted"])
        change_pct = ((end / start) - 1) * 100 if start > 0 else 0.0
        meta = self._last_forecast_meta or {}
        bt = meta.get("backtest") or {}
        evidence = {
            "selected_model": meta.get("model") or model_type,
            "selection_mode": meta.get("selection"),
            "horizon_days": len(forecast_df),
            "change_pct": round(change_pct, 2),
            "peak": round(float(forecast_df["predicted"].max()), 1),
            "floor": round(float(forecast_df["predicted"].min()), 1),
            "holdout_mape_pct": bt.get("mape_pct"),
            "holdout_smape_pct": bt.get("smape_pct"),
            "holdout_rmse": bt.get("rmse"),
            "holdout_mase": bt.get("mase"),
            "train_days": meta.get("train_days"),
            "data_end": meta.get("data_end"),
            "model_comparison": meta.get("model_comparison"),
            "rolling_smape_pct": (meta.get("rolling") or {}).get("rolling_smape_pct"),
            "rolling_mase": (meta.get("rolling") or {}).get("rolling_mase"),
            "primary_metric": meta.get("primary_metric"),
            "decision_band": meta.get("decision_band"),
            "interval_method": meta.get("interval_method"),
            "conformal_q": meta.get("conformal_q"),
            "selection_reason": meta.get("selection"),
            "calendar_filled": meta.get("calendar_filled"),
        }
        method = (
            "Top-4 bake-off: MovingAverage, Drift, Ensemble, SeasonalNaive; rolling-origin CV; "
            "Auto by MASE only if beats SeasonalNaive and MA; split conformal intervals."
        )
        from src.ai.research_insights import analysis_insight

        return analysis_insight(
            "Enrolment forecast",
            evidence,
            method,
            use_llm=use_llm,
            focus=(
                "State which model won and what the path means for staffing envelopes. "
                "Give concrete monitoring actions based on decision band / MASE / sMAPE."
            ),
        )

    def generate_dashboard_insight(self, anomaly_count: int, use_llm: bool = True) -> str:
        vol = self._enrol_volume_col()
        total = float(self.df_enrol[vol].sum()) if not self.df_enrol.empty else 0
        bio = float(self.df_bio["bio_stress"].sum()) if not self.df_bio.empty and "bio_stress" in self.df_bio.columns else 0
        demo = (
            float(self.df_demo["update_volume"].sum())
            if not self.df_demo.empty and "update_volume" in self.df_demo.columns
            else 0
        )
        anom = self.get_anomalies()
        top_risk = []
        if not anom.empty:
            cols = [c for c in ("state", "district", "risk_score", "reason") if c in anom.columns]
            top_risk = anom.head(5)[cols].to_dict(orient="records")
        top_states = {}
        if not self.df_enrol.empty:
            top_states = (
                self.df_enrol.groupby("state", observed=True)[vol].sum().nlargest(5).round(0).astype(int).to_dict()
            )
        max_date = None
        if not self.df_enrol.empty and "date" in self.df_enrol.columns:
            max_date = str(pd.to_datetime(self.df_enrol["date"]).max().date())

        evidence = {
            "total_enrolments": int(total),
            "biometric_updates": int(bio),
            "demographic_updates": int(demo),
            "bio_per_enrol": round(bio / (total + 1), 2),
            "demo_per_enrol": round(demo / (total + 1), 2),
            "anomaly_count": anomaly_count,
            "contamination": ANOMALY_CONTAMINATION,
            "min_volume": ANOMALY_MIN_VOLUME,
            "top_states_by_enrolment": top_states,
            "top_risk_cells": top_risk,
            "data_as_of": max_date,
            "unit_of_analysis": "state × district (composite key)",
        }
        method = (
            "Daily marts aggregation; IsolationForest on multi-features "
            "(log volume, CV, bio/demo ratios, growth, activity, vs state median)."
        )
        from src.ai.research_insights import analysis_insight

        return analysis_insight(
            "Operations overview",
            evidence,
            method,
            use_llm=use_llm,
            focus=(
                "Prioritise workload balance (enrol vs bio vs demo) and which flagged cells to review first. "
                "Give practical next steps. Do not allege fraud."
            ),
        )

    def generate_governance_insight(self, issues_df: pd.DataFrame, use_llm: bool = True) -> str:
        if issues_df is None or issues_df.empty:
            evidence = {"open_issues": 0, "high_conf_gt_0_9": 0}
        else:
            sample_bits = []
            for _, row in issues_df.head(6).iterrows():
                sample_bits.append(
                    f"{row.get('Suspect')} → {row.get('Fix')} "
                    f"(conf={float(row.get('Conf', 0)):.0%}, vol={row.get('Suspect_Vol', '?')})"
                )
            evidence = {
                "open_issues": int(len(issues_df)),
                "high_conf_gt_0_9": int((issues_df["Conf"] > 0.9).sum()) if "Conf" in issues_df.columns else 0,
                "example_issues": sample_bits,
            }
        method = "String similarity (difflib) + optional PIN overlap; human-in-the-loop merge/delete."
        from src.ai.research_insights import analysis_insight

        return analysis_insight(
            "Name governance",
            evidence,
            method,
            use_llm=use_llm,
            focus=(
                "Recommend Auto-Fix vs Merge all vs careful per-row review. "
                "Give concrete stewardship actions, not punishment language."
            ),
        )
