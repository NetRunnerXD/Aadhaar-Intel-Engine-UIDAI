"""Research analytics: composite-key anomalies + multi-model forecast selection."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from src.config import (
    ANOMALY_CONTAMINATION,
    ANOMALY_MIN_VOLUME,
    FORECAST_CANDIDATES,
    FORECAST_HOLDOUT_DAYS,
    FORECAST_RANDOM_SEED,
)
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

    def _daily_series(self) -> pd.DataFrame:
        vol = self._enrol_volume_col()
        if self.df_enrol.empty or vol not in self.df_enrol.columns:
            return pd.DataFrame(columns=["date", "y"])
        df = self.df_enrol.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        daily = df.groupby("date", observed=True)[vol].sum().sort_index().reset_index()
        daily = daily.dropna(subset=["date"]).rename(columns={vol: "y"})
        daily["y"] = daily["y"].astype(float)
        return daily[daily["y"] > 0].reset_index(drop=True)

    def _make_time_features(self, dates: pd.Series, origin: Optional[pd.Timestamp] = None) -> pd.DataFrame:
        d = pd.to_datetime(dates)
        if origin is None:
            origin = d.min()
        origin = pd.Timestamp(origin)
        dow = d.dt.dayofweek
        t = (d - origin).dt.days.astype(float)
        return pd.DataFrame(
            {
                "t": t.values,
                "dow_sin": np.sin(2 * np.pi * dow / 7.0).values,
                "dow_cos": np.cos(2 * np.pi * dow / 7.0).values,
                "month_sin": np.sin(2 * np.pi * d.dt.month / 12.0).values,
                "month_cos": np.cos(2 * np.pi * d.dt.month / 12.0).values,
                "is_weekend": (dow >= 5).astype(float).values,
            }
        )

    def _recent_window(self, daily: pd.DataFrame, max_days: int = 90) -> pd.DataFrame:
        if daily.empty or len(daily) <= max_days:
            return daily
        return daily.iloc[-max_days:].reset_index(drop=True)

    def _seasonal_naive_predict(self, daily: pd.DataFrame, future_dates: pd.DatetimeIndex) -> np.ndarray:
        d = self._recent_window(daily, 90).copy()
        d["dow"] = pd.to_datetime(d["date"]).dt.dayofweek
        level = float(d["y"].tail(14).mean())
        dow_mean = d.groupby("dow")["y"].mean()
        overall = float(d["y"].mean()) or 1.0
        factors = (dow_mean / overall).to_dict()
        mid = len(d) // 2
        if mid >= 7:
            t1 = float(d["y"].iloc[:mid].mean()) or 1.0
            t2 = float(d["y"].iloc[mid:].mean())
            daily_trend = (t2 / t1) ** (1.0 / max(len(d) - mid, 1)) - 1.0
            daily_trend = float(np.clip(daily_trend, -0.02, 0.02))
        else:
            daily_trend = 0.0
        preds = []
        for i, dt in enumerate(future_dates):
            factor = float(factors.get(pd.Timestamp(dt).dayofweek, 1.0))
            preds.append(max(level * factor * ((1.0 + daily_trend) ** (i + 1)), 0.0))
        return np.asarray(preds, dtype=float)

    def _ma_predict(self, daily: pd.DataFrame, future_dates: pd.DatetimeIndex, window: int = 7) -> np.ndarray:
        level = float(daily["y"].tail(window).mean()) if len(daily) else 0.0
        return np.full(len(future_dates), max(level, 0.0), dtype=float)

    def _ridge_predict(self, daily: pd.DataFrame, future_dates: pd.DatetimeIndex):
        d = self._recent_window(daily, 120)
        y = d["y"].astype(float).values
        origin = d["date"].min()
        X = self._make_time_features(d["date"], origin=origin)[["t"]]
        model = Ridge(alpha=2.0)
        model.fit(X.values, y)
        fitted = model.predict(X.values)
        resid = y - fitted
        X_fut = self._make_time_features(pd.Series(future_dates), origin=origin)[["t"]]
        base = np.maximum(model.predict(X_fut.values), 0.0)
        return base, resid, fitted

    def _predict_holdout(self, train: pd.DataFrame, test_dates: pd.DatetimeIndex, model_type: str) -> np.ndarray:
        m = model_type.lower()
        if m.startswith("seasonal"):
            return self._seasonal_naive_predict(train, test_dates)
        if m.startswith("moving") or m == "ma":
            return self._ma_predict(train, test_dates)
        base, _, _ = self._ridge_predict(train, test_dates)
        return base

    def _score_predictions(self, actual: np.ndarray, preds: np.ndarray) -> Dict[str, Any]:
        mask = actual > 1
        if mask.any():
            mape = float(np.mean(np.abs(actual[mask] - preds[mask]) / actual[mask]) * 100)
            smape = float(
                np.mean(
                    2
                    * np.abs(actual[mask] - preds[mask])
                    / (np.abs(actual[mask]) + np.abs(preds[mask]) + 1e-9)
                )
                * 100
            )
        else:
            mape, smape = None, None
        rmse = float(np.sqrt(np.mean((actual - preds) ** 2)))
        return {
            "mape_pct": round(mape, 2) if mape is not None else None,
            "smape_pct": round(smape, 2) if smape is not None else None,
            "rmse": round(rmse, 2),
            "mean_actual": round(float(actual.mean()), 1),
            "mean_pred": round(float(preds.mean()), 1),
        }

    def compare_forecast_models(
        self, holdout_days: int | None = None, candidates: Tuple[str, ...] | None = None
    ) -> pd.DataFrame:
        """Holdout bake-off for research reporting."""
        holdout_days = holdout_days or FORECAST_HOLDOUT_DAYS
        candidates = candidates or FORECAST_CANDIDATES
        daily = self._daily_series()
        if len(daily) < holdout_days + 21:
            return pd.DataFrame()

        train = daily.iloc[:-holdout_days].copy()
        test = daily.iloc[-holdout_days:].copy()
        future = pd.DatetimeIndex(test["date"])
        actual = test["y"].values.astype(float)
        rows = []
        for name in candidates:
            preds = self._predict_holdout(train, future, name)
            scores = self._score_predictions(actual, preds)
            rows.append({"model": name, "holdout_days": holdout_days, **scores})
        df = pd.DataFrame(rows)
        # rank by sMAPE then MAPE then RMSE
        df["_rank"] = df["smape_pct"].fillna(1e9)
        df = df.sort_values(["_rank", "mape_pct", "rmse"]).drop(columns=["_rank"]).reset_index(drop=True)
        self._model_comparison = df.to_dict(orient="records")
        return df

    def select_best_model(self) -> str:
        cmp_df = self.compare_forecast_models()
        if cmp_df.empty:
            return "Seasonal"
        return str(cmp_df.iloc[0]["model"])

    def backtest_forecast(self, holdout_days: int = 14, model_type: str = "Seasonal") -> Dict[str, Any]:
        daily = self._daily_series()
        if len(daily) < holdout_days + 21:
            return {
                "mape_pct": None,
                "smape_pct": None,
                "rmse": None,
                "holdout_days": holdout_days,
                "status": "insufficient_history",
                "model": model_type,
            }
        train = daily.iloc[:-holdout_days].copy()
        test = daily.iloc[-holdout_days:].copy()
        preds = self._predict_holdout(train, pd.DatetimeIndex(test["date"]), model_type)
        scores = self._score_predictions(test["y"].values.astype(float), preds)
        return {"status": "ok", "model": model_type, "holdout_days": holdout_days, **scores}

    def forecast_trends(
        self,
        horizon: int = 30,
        growth_factor: float = 0.0,
        model_type: str = "Auto",
        seed: int = FORECAST_RANDOM_SEED,
    ) -> Tuple[Optional[pd.DataFrame], str]:
        daily = self._daily_series()
        if daily.empty or len(daily) < 14:
            return None, "No Data"

        # Model selection
        if str(model_type).lower() in ("auto", "best", "select"):
            cmp_df = self.compare_forecast_models()
            algo = str(cmp_df.iloc[0]["model"]) if not cmp_df.empty else "Seasonal"
            selection = "auto"
        else:
            algo = model_type
            if str(algo).lower().startswith("linear"):
                algo = "Linear"
            elif str(algo).lower().startswith("moving"):
                algo = "MovingAverage"
            else:
                algo = "Seasonal"
            self.compare_forecast_models()  # still publish comparison
            selection = "manual"

        last_date = daily["date"].max()
        future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")

        if algo == "Seasonal":
            base = self._seasonal_naive_predict(daily, future_dates)
        elif algo == "MovingAverage":
            base = self._ma_predict(daily, future_dates)
        else:
            base, _, _ = self._ridge_predict(daily, future_dates)

        hist = self._recent_window(daily, 60).copy()
        baseline = hist["y"].rolling(7, min_periods=1).mean().shift(1).fillna(hist["y"].mean())
        resid = (hist["y"] - baseline).values

        if growth_factor:
            ramp = 1.0 + growth_factor * np.linspace(1.0 / horizon, 1.0, horizon)
            base = np.asarray(base, dtype=float) * ramp
        base = np.maximum(np.asarray(base, dtype=float), 0.0)

        rng = np.random.default_rng(seed)
        resid = np.asarray(resid, dtype=float)
        resid = resid[np.isfinite(resid)]
        if len(resid) < 5:
            resid = np.array([0.0])
        sims = np.asarray(
            [np.maximum(base + rng.choice(resid, size=horizon, replace=True), 0.0) for _ in range(300)]
        )
        predicted = np.median(sims, axis=0)
        lower = np.percentile(sims, 10, axis=0)
        upper = np.percentile(sims, 90, axis=0)

        holdout = min(FORECAST_HOLDOUT_DAYS, max(7, len(daily) // 8))
        bt = self.backtest_forecast(holdout_days=holdout, model_type=algo)
        self._last_forecast_meta = {
            "model": algo,
            "selection": selection,
            "horizon": horizon,
            "growth_factor": growth_factor,
            "backtest": bt,
            "model_comparison": self._model_comparison,
            "train_days": len(daily),
            "residual_std": float(np.std(resid)) if len(resid) else 0.0,
            "data_end": str(pd.Timestamp(last_date).date()),
        }

        return (
            pd.DataFrame(
                {"date": future_dates, "predicted": predicted, "upper": upper, "lower": lower}
            ),
            algo,
        )

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
            "train_days": meta.get("train_days"),
            "data_end": meta.get("data_end"),
            "model_comparison": meta.get("model_comparison"),
        }
        method = (
            "Holdout evaluation of Seasonal (DOW×level), Linear (Ridge on t), and MovingAverage (7-day). "
            "Auto-select minimizes holdout sMAPE. Intervals = residual bootstrap P10–P90."
        )
        from src.ai.research_insights import research_insight

        return research_insight(
            "Enrolment volume forecast",
            evidence,
            method,
            use_llm=use_llm,
            focus=(
                "Explain which model won the holdout bake-off and what the 30-day path implies "
                "for staffing envelopes. Comment on whether holdout sMAPE supports tight day-level targets."
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
            "Descriptive aggregation of daily marts; IsolationForest on scaled multi-features "
            "(log volume, CV, bio/demo ratios, growth, activity, vs state median). "
            "No causal identification strategy."
        )
        from src.ai.research_insights import research_insight

        return research_insight(
            "Operations research brief",
            evidence,
            method,
            use_llm=use_llm,
            focus=(
                "Prioritise workload balance (enrol vs bio vs demo) and which flagged cells to investigate first. "
                "Do not allege fraud."
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
        from src.ai.research_insights import research_insight

        return research_insight(
            "Governance residual triage",
            evidence,
            method,
            use_llm=use_llm,
            focus=(
                "Recommend which high-confidence merges are safe to auto-fix vs which need human review. "
                "Emphasise data stewardship, not punishment."
            ),
        )
