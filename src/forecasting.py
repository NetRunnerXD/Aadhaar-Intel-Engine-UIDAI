# -*- coding: utf-8 -*-
"""
Forecasting backend — research-grade, sklearn-only.

Architecture:
  SeriesBuilder (calendar fill) → model registry → rolling-origin CV
  → beat SeasonalNaive+MA gate on primary metric (MASE by default)
  → split-conformal intervals

Models: SeasonalNaive, MovingAverage, Drift, Seasonal, Linear, SeasonalHoliday,
        RidgeLags, HistGB, Ensemble (median of top non-ensemble CV winners).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

from src.config import (
    FORECAST_BEAT_BASELINE_EPS,
    FORECAST_CANDIDATES,
    FORECAST_CONFORMAL_ALPHA,
    FORECAST_FILL_MISSING_DAYS,
    FORECAST_HOLDOUT_DAYS,
    FORECAST_MASE_THRESHOLDS,
    FORECAST_MAX_HISTORY_DAYS,
    FORECAST_MIN_TRAIN_DAYS,
    FORECAST_PRIMARY_METRIC,
    FORECAST_RANDOM_SEED,
    FORECAST_ROLLING_FOLDS,
    FORECAST_ROLLING_STEP,
    FORECAST_SMAPE_THRESHOLDS,
    INDIA_HOLIDAYS_PATH,
)

# ---------------------------------------------------------------------------
# Holidays
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_holiday_set(path: Optional[str] = None) -> Tuple[set, set]:
    p = Path(path) if path else INDIA_HOLIDAYS_PATH
    if not p.exists():
        return set(), set()
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    dates = set(raw.get("dates") or [])
    fixed = set(raw.get("fixed_md") or [])
    return dates, fixed


def _holiday_flags(dates: pd.Series) -> np.ndarray:
    d = pd.to_datetime(dates)
    exact_set, fixed_set = load_holiday_set()
    flags = []
    for ts in d:
        s = str(pd.Timestamp(ts).date())
        md = pd.Timestamp(ts).strftime("%m-%d")
        flags.append(1.0 if (s in exact_set or md in fixed_set) else 0.0)
    return np.asarray(flags, dtype=float)


# ---------------------------------------------------------------------------
# Series construction
# ---------------------------------------------------------------------------


def complete_daily_calendar(
    daily: pd.DataFrame,
    fill_value: float = 0.0,
    max_history: int = FORECAST_MAX_HISTORY_DAYS,
) -> pd.DataFrame:
    """Ensure continuous daily dates; fill gaps; optionally trim long history."""
    if daily is None or daily.empty:
        return pd.DataFrame(columns=["date", "y"])
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["y"] = pd.to_numeric(d["y"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date")
    d = d.groupby("date", as_index=False)["y"].sum()
    if d.empty:
        return pd.DataFrame(columns=["date", "y"])

    if FORECAST_FILL_MISSING_DAYS:
        full_idx = pd.date_range(d["date"].min(), d["date"].max(), freq="D")
        d = (
            d.set_index("date")
            .reindex(full_idx)
            .rename_axis("date")
            .reset_index()
        )
        d["y"] = d["y"].fillna(fill_value)

    d["y"] = d["y"].astype(float).clip(lower=0.0)
    if max_history and len(d) > max_history:
        d = d.iloc[-max_history:].reset_index(drop=True)
    else:
        d = d.reset_index(drop=True)
    return d


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def decision_band(smape: Optional[float], mase: Optional[float] = None) -> str:
    """Prefer MASE when present; fall back to sMAPE thresholds."""
    if mase is not None and np.isfinite(mase):
        if mase < FORECAST_MASE_THRESHOLDS["tight"]:
            return "tight"
        if mase < FORECAST_MASE_THRESHOLDS["directional"]:
            return "directional"
        return "exploratory"
    if smape is None:
        return "unknown"
    if smape < FORECAST_SMAPE_THRESHOLDS["tight"]:
        return "tight"
    if smape < FORECAST_SMAPE_THRESHOLDS["directional"]:
        return "directional"
    return "exploratory"


def _seasonal_naive_insample_mae(y: np.ndarray, season: int = 7) -> float:
    y = np.asarray(y, dtype=float)
    if len(y) <= season:
        mae = float(np.mean(np.abs(np.diff(y)))) if len(y) > 1 else float(np.mean(np.abs(y)))
        return mae if mae > 1e-9 else 1.0
    err = np.abs(y[season:] - y[:-season])
    mae = float(np.mean(err)) if len(err) else 1.0
    return mae if mae > 1e-9 else 1.0


def score_predictions(
    actual: np.ndarray,
    preds: np.ndarray,
    y_train: Optional[np.ndarray] = None,
    season: int = 7,
) -> Dict[str, Any]:
    actual = np.asarray(actual, dtype=float)
    preds = np.asarray(preds, dtype=float)
    mask = np.isfinite(actual) & np.isfinite(preds)
    actual, preds = actual[mask], preds[mask]
    if len(actual) == 0:
        return {
            "mape_pct": None,
            "smape_pct": None,
            "rmse": None,
            "nrmse": None,
            "mase": None,
            "bias": None,
            "mean_actual": None,
            "mean_pred": None,
            "decision_band": "unknown",
        }

    pos = actual > 1
    if pos.any():
        mape = float(np.mean(np.abs(actual[pos] - preds[pos]) / actual[pos]) * 100)
        smape = float(
            np.mean(
                2
                * np.abs(actual[pos] - preds[pos])
                / (np.abs(actual[pos]) + np.abs(preds[pos]) + 1e-9)
            )
            * 100
        )
    else:
        mape, smape = None, None

    rmse = float(np.sqrt(np.mean((actual - preds) ** 2)))
    mean_a = float(actual.mean())
    nrmse = float(rmse / mean_a) if mean_a > 1e-9 else None
    bias = float(np.mean(preds - actual))

    if y_train is not None and len(y_train):
        scale = _seasonal_naive_insample_mae(np.asarray(y_train, dtype=float), season=season)
    else:
        scale = _seasonal_naive_insample_mae(actual, season=season)
    mase = float(np.mean(np.abs(actual - preds)) / scale)

    return {
        "mape_pct": round(mape, 2) if mape is not None else None,
        "smape_pct": round(smape, 2) if smape is not None else None,
        "rmse": round(rmse, 2),
        "nrmse": round(nrmse, 4) if nrmse is not None else None,
        "mase": round(mase, 4),
        "bias": round(bias, 2),
        "mean_actual": round(mean_a, 1),
        "mean_pred": round(float(preds.mean()), 1),
        "decision_band": decision_band(smape, mase),
    }


def _primary_key() -> str:
    m = (FORECAST_PRIMARY_METRIC or "mase").lower()
    if m in ("smape", "smape_pct"):
        return "smape_pct"
    if m == "rmse":
        return "rmse"
    return "mase"


# ---------------------------------------------------------------------------
# Feature helpers (lag models)
# ---------------------------------------------------------------------------

_LAGS = (1, 7, 14, 28)
_ROLL = (7, 14)


def _feature_row(history: List[float], date: pd.Timestamp) -> List[float]:
    """Build one feature vector from full history list ending at day before `date`."""
    y = history
    n = len(y)

    def lag(k: int) -> float:
        return float(y[-k]) if n >= k else float(y[-1]) if n else 0.0

    def roll_mean(w: int) -> float:
        if n == 0:
            return 0.0
        return float(np.mean(y[-min(w, n) :]))

    def roll_std(w: int) -> float:
        if n < 2:
            return 0.0
        return float(np.std(y[-min(w, n) :]))

    dd = pd.Timestamp(date)
    dow = dd.dayofweek
    month = dd.month
    hol = float(_holiday_flags(pd.Series([dd]))[0])
    # day-before / day-after holiday approx via lag flags not available; use hol only
    feats = [
        lag(1),
        lag(7),
        lag(14),
        lag(28),
        roll_mean(7),
        roll_mean(14),
        roll_std(7),
        roll_std(14),
        np.sin(2 * np.pi * dow / 7.0),
        np.cos(2 * np.pi * dow / 7.0),
        np.sin(2 * np.pi * month / 12.0),
        np.cos(2 * np.pi * month / 12.0),
        1.0 if dow >= 5 else 0.0,
        hol,
        float(n),  # weak trend proxy: time index
    ]
    return feats


def _build_supervised(daily: pd.DataFrame, min_hist: int = 28) -> Tuple[np.ndarray, np.ndarray]:
    y = daily["y"].astype(float).tolist()
    dates = pd.to_datetime(daily["date"]).tolist()
    X_rows, y_rows = [], []
    for i in range(min_hist, len(y)):
        hist = y[:i]
        X_rows.append(_feature_row(hist, dates[i]))
        y_rows.append(y[i])
    if not X_rows:
        return np.zeros((0, 15)), np.zeros(0)
    return np.asarray(X_rows, dtype=float), np.asarray(y_rows, dtype=float)


def _recursive_predict(
    daily: pd.DataFrame,
    future: pd.DatetimeIndex,
    predict_one: Callable[[np.ndarray], float],
    min_hist: int = 28,
) -> np.ndarray:
    hist = daily["y"].astype(float).tolist()
    out = []
    for dt in future:
        if len(hist) < min_hist:
            # warm-up: seasonal naive-ish
            pred = hist[-7] if len(hist) >= 7 else (hist[-1] if hist else 0.0)
        else:
            x = np.asarray(_feature_row(hist, pd.Timestamp(dt)), dtype=float).reshape(1, -1)
            pred = float(predict_one(x))
        pred = max(pred, 0.0)
        out.append(pred)
        hist.append(pred)
    return np.asarray(out, dtype=float)


# ---------------------------------------------------------------------------
# ForecastBackend
# ---------------------------------------------------------------------------


class ForecastBackend:
    def __init__(self, seed: int = FORECAST_RANDOM_SEED):
        self.seed = seed
        self.last_comparison: List[Dict[str, Any]] = []
        self.last_rolling: Dict[str, Any] = {}
        self.last_meta: Dict[str, Any] = {}

    def prepare_series(self, daily: pd.DataFrame) -> pd.DataFrame:
        return complete_daily_calendar(daily)

    # ---- individual models ----
    def predict_ma(self, daily: pd.DataFrame, future: pd.DatetimeIndex, window: int = 7) -> np.ndarray:
        d = self.prepare_series(daily)
        level = float(d["y"].tail(window).mean()) if len(d) else 0.0
        # mild weekly shape using last 28d DOW factors if available
        if len(d) >= 14:
            tmp = d.tail(28).copy()
            tmp["dow"] = pd.to_datetime(tmp["date"]).dt.dayofweek
            overall = float(tmp["y"].mean()) or 1.0
            factors = (tmp.groupby("dow")["y"].mean() / overall).to_dict()
            return np.asarray(
                [max(level * float(factors.get(pd.Timestamp(dt).dayofweek, 1.0)), 0.0) for dt in future]
            )
        return np.full(len(future), max(level, 0.0))

    def predict_seasonal_naive(self, daily: pd.DataFrame, future: pd.DatetimeIndex) -> np.ndarray:
        d = self.prepare_series(daily)
        y = d["y"].astype(float).values
        if len(y) == 0:
            return np.zeros(len(future))
        out = []
        # extend with predictions so multi-step uses seasonal pattern
        hist = list(y)
        for i, _dt in enumerate(future):
            if len(hist) >= 7:
                pred = hist[-7]
            else:
                pred = hist[-1]
            pred = max(float(pred), 0.0)
            out.append(pred)
            hist.append(pred)
        return np.asarray(out)

    def predict_drift(self, daily: pd.DataFrame, future: pd.DatetimeIndex) -> np.ndarray:
        d = self.prepare_series(daily)
        y = d["y"].astype(float).values
        if len(y) < 2:
            level = float(y[-1]) if len(y) else 0.0
            return np.full(len(future), max(level, 0.0))
        slope = (y[-1] - y[0]) / max(len(y) - 1, 1)
        # damp slope for long horizons
        slope = float(np.clip(slope, -0.05 * (np.mean(y) + 1), 0.05 * (np.mean(y) + 1)))
        return np.asarray([max(y[-1] + slope * (i + 1), 0.0) for i in range(len(future))])

    def predict_seasonal(self, daily: pd.DataFrame, future: pd.DatetimeIndex) -> np.ndarray:
        d = self.prepare_series(daily)
        d = d if len(d) <= FORECAST_MAX_HISTORY_DAYS else d.iloc[-FORECAST_MAX_HISTORY_DAYS:]
        d = d.copy()
        d["dow"] = pd.to_datetime(d["date"]).dt.dayofweek
        level = float(d["y"].tail(14).mean())
        overall = float(d["y"].mean()) or 1.0
        factors = (d.groupby("dow")["y"].mean() / overall).to_dict()
        mid = len(d) // 2
        if mid >= 7:
            t1 = float(d["y"].iloc[:mid].mean()) or 1.0
            t2 = float(d["y"].iloc[mid:].mean())
            trend = float(np.clip((t2 / t1) ** (1.0 / max(len(d) - mid, 1)) - 1.0, -0.02, 0.02))
        else:
            trend = 0.0
        out = []
        for i, dt in enumerate(future):
            f = float(factors.get(pd.Timestamp(dt).dayofweek, 1.0))
            out.append(max(level * f * ((1.0 + trend) ** (i + 1)), 0.0))
        return np.asarray(out)

    def predict_linear(self, daily: pd.DataFrame, future: pd.DatetimeIndex) -> np.ndarray:
        d = self.prepare_series(daily)
        origin = pd.Timestamp(d["date"].min())
        t = np.array([(pd.Timestamp(x) - origin).days for x in d["date"]], dtype=float).reshape(-1, 1)
        y = d["y"].astype(float).values
        model = Ridge(alpha=2.0)
        model.fit(t, y)
        t_f = np.array([(pd.Timestamp(x) - origin).days for x in future], dtype=float).reshape(-1, 1)
        return np.maximum(model.predict(t_f), 0.0)

    def predict_seasonal_holiday(self, daily: pd.DataFrame, future: pd.DatetimeIndex) -> np.ndarray:
        d = self.prepare_series(daily).copy()
        origin = pd.Timestamp(d["date"].min())
        dd = pd.to_datetime(d["date"])
        X = np.column_stack(
            [
                (dd - origin).dt.days.astype(float).values,
                np.sin(2 * np.pi * dd.dt.dayofweek / 7.0),
                np.cos(2 * np.pi * dd.dt.dayofweek / 7.0),
                (dd.dt.dayofweek >= 5).astype(float).values,
                _holiday_flags(dd),
            ]
        )
        y = d["y"].astype(float).values
        model = Ridge(alpha=1.5)
        model.fit(X, y)
        ff = pd.DatetimeIndex(pd.to_datetime(future))
        dow = np.asarray(ff.dayofweek, dtype=float)
        Xf = np.column_stack(
            [
                np.array([(pd.Timestamp(x) - origin).days for x in future], dtype=float),
                np.sin(2 * np.pi * dow / 7.0),
                np.cos(2 * np.pi * dow / 7.0),
                (dow >= 5).astype(float),
                _holiday_flags(pd.Series(ff)),
            ]
        )
        return np.maximum(model.predict(Xf), 0.0)

    def predict_ridge_lags(self, daily: pd.DataFrame, future: pd.DatetimeIndex) -> np.ndarray:
        d = self.prepare_series(daily)
        X, y = _build_supervised(d, min_hist=28)
        if len(y) < 20:
            return self.predict_seasonal_naive(d, future)
        model = Ridge(alpha=3.0)
        model.fit(X, y)
        return _recursive_predict(d, future, lambda x: float(model.predict(x)[0]), min_hist=28)

    def predict_hist_gb(self, daily: pd.DataFrame, future: pd.DatetimeIndex) -> np.ndarray:
        d = self.prepare_series(daily)
        X, y = _build_supervised(d, min_hist=28)
        if len(y) < 40:
            return self.predict_ridge_lags(d, future)
        model = HistGradientBoostingRegressor(
            max_depth=4,
            learning_rate=0.06,
            max_iter=120,
            min_samples_leaf=8,
            l2_regularization=0.1,
            random_state=self.seed,
        )
        model.fit(X, y)
        return _recursive_predict(d, future, lambda x: float(model.predict(x)[0]), min_hist=28)

    def predict_ensemble(
        self,
        daily: pd.DataFrame,
        future: pd.DatetimeIndex,
        members: Optional[List[str]] = None,
    ) -> np.ndarray:
        """Median of non-Ensemble bake-off members (top baselines)."""
        if members is None:
            members = [m for m in FORECAST_CANDIDATES if m != "Ensemble"]
            if not members:
                members = ["MovingAverage", "Drift", "SeasonalNaive"]
        mats = []
        for m in members:
            if m == "Ensemble":
                continue
            try:
                mats.append(self.predict(daily, future, m))
            except Exception:
                continue
        if not mats:
            return self.predict_ma(daily, future)
        stack = np.vstack(mats)
        return np.maximum(np.median(stack, axis=0), 0.0)

    def predict(self, daily: pd.DataFrame, future: pd.DatetimeIndex, model: str) -> np.ndarray:
        m = (model or "").strip()
        key = m.lower().replace(" ", "").replace("_", "")
        d = self.prepare_series(daily)
        if key in ("seasonalnaive", "snaive", "naive"):
            return self.predict_seasonal_naive(d, future)
        if key in ("movingaverage", "movingavg", "ma"):
            return self.predict_ma(d, future)
        if key == "drift":
            return self.predict_drift(d, future)
        if key in ("seasonalholiday",):
            return self.predict_seasonal_holiday(d, future)
        if key == "seasonal":
            return self.predict_seasonal(d, future)
        if key in ("linear", "ridge"):
            return self.predict_linear(d, future)
        if key in ("ridgelags", "aridge", "lassolags"):
            return self.predict_ridge_lags(d, future)
        if key in ("histgb", "hgb", "gbdt", "gradientboosting"):
            return self.predict_hist_gb(d, future)
        if key == "ensemble":
            return self.predict_ensemble(d, future)
        return self.predict_linear(d, future)

    def normalize_model_name(self, model: str) -> str:
        key = (model or "").lower().replace(" ", "").replace("_", "")
        mapping = {
            "seasonalnaive": "SeasonalNaive",
            "snaive": "SeasonalNaive",
            "naive": "SeasonalNaive",
            "movingaverage": "MovingAverage",
            "movingavg": "MovingAverage",
            "ma": "MovingAverage",
            "drift": "Drift",
            "seasonalholiday": "SeasonalHoliday",
            "seasonal": "Seasonal",
            "linear": "Linear",
            "ridge": "Linear",
            "ridgelags": "RidgeLags",
            "aridge": "RidgeLags",
            "histgb": "HistGB",
            "hgb": "HistGB",
            "gbdt": "HistGB",
            "ensemble": "Ensemble",
        }
        return mapping.get(key, model)

    # ---- evaluation ----
    def single_holdout(self, daily: pd.DataFrame, holdout_days: int, model: str) -> Dict[str, Any]:
        d = self.prepare_series(daily)
        if len(d) < holdout_days + FORECAST_MIN_TRAIN_DAYS:
            return {"status": "insufficient", "model": model}
        train = d.iloc[:-holdout_days]
        test = d.iloc[-holdout_days:]
        preds = self.predict(train, pd.DatetimeIndex(test["date"]), model)
        scores = score_predictions(test["y"].values, preds, y_train=train["y"].values)
        scores.update({"status": "ok", "model": self.normalize_model_name(model), "holdout_days": holdout_days})
        return scores

    def rolling_origin_cv(
        self,
        daily: pd.DataFrame,
        models: Tuple[str, ...] | None = None,
        folds: int = FORECAST_ROLLING_FOLDS,
        horizon: int = FORECAST_HOLDOUT_DAYS,
        step: int = FORECAST_ROLLING_STEP,
    ) -> pd.DataFrame:
        models = models or FORECAST_CANDIDATES
        d = self.prepare_series(daily)
        n = len(d)
        rows = []
        for k in range(folds):
            test_end = n - k * step
            test_start = test_end - horizon
            if test_start < FORECAST_MIN_TRAIN_DAYS:
                break
            train = d.iloc[:test_start]
            test = d.iloc[test_start:test_end]
            if len(test) < max(5, horizon // 2):
                continue
            for model in models:
                try:
                    preds = self.predict(train, pd.DatetimeIndex(test["date"]), model)
                    sc = score_predictions(test["y"].values, preds, y_train=train["y"].values)
                except Exception as e:
                    sc = {
                        "mape_pct": None,
                        "smape_pct": None,
                        "rmse": None,
                        "nrmse": None,
                        "mase": None,
                        "bias": None,
                        "mean_actual": None,
                        "mean_pred": None,
                        "decision_band": "unknown",
                        "error": str(e)[:80],
                    }
                rows.append(
                    {
                        "fold": k,
                        "model": self.normalize_model_name(model),
                        "train_end_idx": test_start,
                        "n_train": len(train),
                        "n_test": len(test),
                        **sc,
                    }
                )
        df = pd.DataFrame(rows)
        self.last_rolling = {
            "folds": int(df["fold"].nunique()) if not df.empty else 0,
            "rows": len(df),
        }
        return df

    def compare_models(self, daily: pd.DataFrame, use_rolling: bool = True) -> pd.DataFrame:
        d = self.prepare_series(daily)
        pk = _primary_key()
        if use_rolling and len(d) >= FORECAST_MIN_TRAIN_DAYS + FORECAST_HOLDOUT_DAYS + FORECAST_ROLLING_STEP:
            rdf = self.rolling_origin_cv(d)
            if not rdf.empty:
                agg = (
                    rdf.groupby("model", as_index=False)
                    .agg(
                        mase=("mase", "mean"),
                        smape_pct=("smape_pct", "mean"),
                        mape_pct=("mape_pct", "mean"),
                        rmse=("rmse", "mean"),
                        nrmse=("nrmse", "mean"),
                        bias=("bias", "mean"),
                        n_folds=("fold", "nunique"),
                    )
                    .reset_index(drop=True)
                )
                for c in ("mase", "smape_pct", "mape_pct", "rmse", "nrmse", "bias"):
                    if c in agg.columns:
                        agg[c] = agg[c].round(4 if c in ("mase", "nrmse") else 2)
                # sort by primary metric ascending
                sort_col = pk if pk in agg.columns else "smape_pct"
                agg = agg.sort_values([sort_col, "smape_pct", "rmse"], na_position="last").reset_index(drop=True)
                agg["decision_band"] = [
                    decision_band(s, m) for s, m in zip(agg["smape_pct"], agg["mase"])
                ]
                agg["eval"] = "rolling_origin"
                agg["primary_metric"] = sort_col
                self.last_comparison = agg.to_dict(orient="records")
                return agg

        rows = []
        for model in FORECAST_CANDIDATES:
            sc = self.single_holdout(d, FORECAST_HOLDOUT_DAYS, model)
            if sc.get("status") == "ok":
                rows.append({**sc, "n_folds": 1, "eval": "single_holdout"})
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        sort_col = pk if pk in df.columns else "smape_pct"
        df = df.sort_values([sort_col, "smape_pct", "rmse"], na_position="last").reset_index(drop=True)
        df["primary_metric"] = sort_col
        self.last_comparison = df.to_dict(orient="records")
        return df

    def select_model(self, daily: pd.DataFrame) -> Tuple[str, Dict[str, Any]]:
        """
        Pick best model by primary metric (default MASE).
        Non-baseline must beat both SeasonalNaive and MovingAverage.
        """
        d = self.prepare_series(daily)
        cmp = self.compare_models(d, use_rolling=True)
        if cmp.empty:
            return "MovingAverage", {"selection": "default_ma", "reason": "insufficient_history"}

        pk = _primary_key()
        if pk not in cmp.columns:
            pk = "smape_pct"

        def _score(row) -> float:
            v = row.get(pk)
            return float(v) if v is not None and np.isfinite(v) else 1e9

        baselines = {}
        for name in ("SeasonalNaive", "MovingAverage"):
            sub = cmp[cmp["model"] == name]
            if not sub.empty:
                baselines[name] = _score(sub.iloc[0])

        best = cmp.iloc[0]
        best_model = str(best["model"])
        best_score = _score(best)

        meta = {
            "selection": "rolling_cv",
            "comparison": self.last_comparison,
            "primary_metric": pk,
            "baselines": baselines,
            "best_raw": best_model,
            "best_score": best_score,
            "beat_baseline_eps": FORECAST_BEAT_BASELINE_EPS,
        }

        if best_model in ("SeasonalNaive", "MovingAverage", "Drift"):
            meta["selected"] = best_model
            meta["reason"] = "best_baseline_or_top"
            return best_model, meta

        # Must beat both available baselines
        ok = True
        for bname, bscore in baselines.items():
            if best_score >= bscore - FORECAST_BEAT_BASELINE_EPS:
                ok = False
                meta["blocked_by"] = bname
                break

        if ok and baselines:
            meta["selected"] = best_model
            meta["reason"] = "beats_baselines"
            return best_model, meta

        # Fall back to best baseline among SeasonalNaive / MA
        fallback = "MovingAverage"
        if "SeasonalNaive" in baselines and "MovingAverage" in baselines:
            fallback = (
                "SeasonalNaive"
                if baselines["SeasonalNaive"] <= baselines["MovingAverage"]
                else "MovingAverage"
            )
        elif "SeasonalNaive" in baselines:
            fallback = "SeasonalNaive"
        meta["selected"] = fallback
        meta["reason"] = "baseline_gate_blocked"
        return fallback, meta

    def conformal_interval(
        self,
        daily: pd.DataFrame,
        base: np.ndarray,
        model: str,
        alpha: float = FORECAST_CONFORMAL_ALPHA,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        d = self.prepare_series(daily)
        hold = min(FORECAST_HOLDOUT_DAYS, max(7, len(d) // 6))
        if len(d) < hold + FORECAST_MIN_TRAIN_DAYS:
            lvl = float(d["y"].mean()) if len(d) else 0.0
            q = max(0.2 * lvl, 1.0)
            return np.maximum(base - q, 0.0), base + q, q

        train = d.iloc[:-hold]
        test = d.iloc[-hold:]
        cal_pred = self.predict(train, pd.DatetimeIndex(test["date"]), model)
        resid = np.abs(test["y"].values.astype(float) - cal_pred)
        resid = resid[np.isfinite(resid)]
        if len(resid) < 3:
            q = float(np.std(resid)) if len(resid) else 1.0
        else:
            level = np.ceil((len(resid) + 1) * (1 - alpha)) / len(resid)
            level = min(max(level, 0.0), 1.0)
            q = float(np.quantile(resid, level))
        lower = np.maximum(base - q, 0.0)
        upper = base + q
        return lower, upper, q

    def forecast(
        self,
        daily: pd.DataFrame,
        horizon: int = 30,
        model_type: str = "Auto",
        growth_factor: float = 0.0,
    ) -> Tuple[Optional[pd.DataFrame], str]:
        d = self.prepare_series(daily)
        if d is None or d.empty or len(d) < 14:
            return None, "No Data"

        if str(model_type).lower() in ("auto", "best", "select"):
            algo, sel_meta = self.select_model(d)
            selection = sel_meta.get("reason", "auto")
        else:
            algo = self.normalize_model_name(model_type)
            self.compare_models(d)
            sel_meta = {"selection": "manual", "comparison": self.last_comparison}
            selection = "manual"

        last_date = pd.Timestamp(d["date"].max())
        future = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")
        base = self.predict(d, future, algo)
        try:
            gf = float(growth_factor)
        except (TypeError, ValueError):
            gf = 0.0
        if gf:
            ramp = 1.0 + gf * np.linspace(1.0 / horizon, 1.0, horizon)
            base = np.asarray(base, dtype=float) * ramp
        base = np.maximum(np.asarray(base, dtype=float), 0.0)

        lower, upper, q_hat = self.conformal_interval(d, base, algo)

        bt = self.single_holdout(d, min(FORECAST_HOLDOUT_DAYS, max(7, len(d) // 8)), algo)
        rolling_summary = {}
        if self.last_comparison:
            for row in self.last_comparison:
                if row.get("model") == algo:
                    rolling_summary = {
                        "rolling_smape_pct": row.get("smape_pct"),
                        "rolling_mape_pct": row.get("mape_pct"),
                        "rolling_rmse": row.get("rmse"),
                        "rolling_mase": row.get("mase"),
                        "rolling_nrmse": row.get("nrmse"),
                        "n_folds": row.get("n_folds"),
                        "decision_band": row.get("decision_band")
                        or decision_band(row.get("smape_pct"), row.get("mase")),
                    }
                    break

        self.last_meta = {
            "model": algo,
            "selection": selection,
            "selection_meta": sel_meta,
            "horizon": horizon,
            "growth_factor": growth_factor,
            "backtest": bt,
            "model_comparison": self.last_comparison,
            "rolling": rolling_summary,
            "conformal_alpha": FORECAST_CONFORMAL_ALPHA,
            "conformal_q": round(q_hat, 2),
            "interval_method": "split_conformal_abs_residual",
            "decision_band": rolling_summary.get("decision_band")
            or decision_band(bt.get("smape_pct"), bt.get("mase")),
            "thresholds_smape": FORECAST_SMAPE_THRESHOLDS,
            "thresholds_mase": FORECAST_MASE_THRESHOLDS,
            "primary_metric": _primary_key(),
            "train_days": len(d),
            "data_end": str(last_date.date()),
            "candidates": list(FORECAST_CANDIDATES),
            "calendar_filled": FORECAST_FILL_MISSING_DAYS,
        }

        out = pd.DataFrame(
            {
                "date": future,
                "predicted": base,
                "lower": lower,
                "upper": upper,
            }
        )
        return out, algo
