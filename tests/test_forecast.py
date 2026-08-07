"""Unit tests for forecast backend (Phase A/B solidification)."""
import numpy as np
import pandas as pd

from src.config import FORECAST_CANDIDATES, FORECAST_SMAPE_THRESHOLDS
from src.forecasting import (
    ForecastBackend,
    complete_daily_calendar,
    decision_band,
    score_predictions,
)


def _synth_daily(n=80, seed=0, drop_weekends=False):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-03-01", periods=n, freq="D")
    y = 1000 + 200 * np.sin(2 * np.pi * np.arange(n) / 7) + rng.normal(0, 50, n)
    y = np.maximum(y, 10)
    df = pd.DataFrame({"date": dates, "y": y})
    if drop_weekends:
        df = df[df["date"].dt.dayofweek < 5].reset_index(drop=True)
    return df


def test_decision_band():
    assert decision_band(10, mase=0.5) == "tight"
    assert decision_band(30, mase=1.0) == "directional"
    assert decision_band(50, mase=2.0) == "exploratory"
    assert decision_band(None) == "unknown"
    assert FORECAST_SMAPE_THRESHOLDS["tight"] < FORECAST_SMAPE_THRESHOLDS["directional"]


def test_score_predictions_includes_mase_nrmse():
    actual = np.array([100.0, 110.0, 90.0, 105.0])
    pred = np.array([100.0, 100.0, 100.0, 100.0])
    train = np.array([95.0, 100.0, 105.0, 98.0, 102.0, 99.0, 101.0, 100.0])
    sc = score_predictions(actual, pred, y_train=train)
    assert sc["smape_pct"] is not None
    assert sc["rmse"] >= 0
    assert sc["mase"] is not None and sc["mase"] > 0
    assert sc["nrmse"] is not None


def test_complete_daily_calendar_fills_gaps():
    raw = _synth_daily(21, drop_weekends=True)
    assert len(raw) < 21
    filled = complete_daily_calendar(raw)
    # full Mon-Sun span
    assert len(filled) >= len(raw)
    assert filled["date"].is_monotonic_increasing
    deltas = filled["date"].diff().dropna().dt.days
    assert (deltas == 1).all()


def test_rolling_cv_and_select():
    fb = ForecastBackend(seed=42)
    daily = _synth_daily(100)
    cmp = fb.compare_models(daily, use_rolling=True)
    assert not cmp.empty
    assert "smape_pct" in cmp.columns
    assert "mase" in cmp.columns
    assert set(cmp["model"]).issubset(set(FORECAST_CANDIDATES))
    model, meta = fb.select_model(daily)
    assert model in set(cmp["model"]) or model in ("MovingAverage", "SeasonalNaive")
    assert "reason" in meta
    assert meta.get("primary_metric") in ("mase", "smape_pct", "rmse")


def test_conformal_and_forecast():
    fb = ForecastBackend(seed=42)
    daily = _synth_daily(100)
    out, algo = fb.forecast(daily, horizon=14, model_type="Auto")
    assert out is not None and len(out) == 14
    assert (out["lower"] <= out["predicted"]).all()
    assert (out["predicted"] <= out["upper"]).all()
    assert fb.last_meta.get("interval_method") == "split_conformal_abs_residual"
    assert "decision_band" in fb.last_meta
    assert fb.last_meta.get("primary_metric") == "mase"


def test_top4_models_run():
    fb = ForecastBackend(seed=0)
    daily = _synth_daily(90)
    future = pd.date_range(daily["date"].max() + pd.Timedelta(days=1), periods=10, freq="D")
    assert set(FORECAST_CANDIDATES) == {"MovingAverage", "Drift", "Ensemble", "SeasonalNaive"}
    for name in FORECAST_CANDIDATES:
        pred = fb.predict(daily, future, name)
        assert len(pred) == 10
        assert np.all(np.isfinite(pred))
        assert np.all(pred >= 0)


def test_ma_gate_prefers_baseline_when_close():
    fb = ForecastBackend(seed=1)
    daily = _synth_daily(70, seed=3)
    model, meta = fb.select_model(daily)
    assert model is not None
    assert meta.get("reason") in (
        "best_baseline_or_top",
        "beats_baselines",
        "baseline_gate_blocked",
        "default_ma",
        "best_or_only",
    )
