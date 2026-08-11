from pathlib import Path

p = Path(r"D:\Project\Aadhaar-Intel-Engine-UIDAI\src\ai_core.py")
t = p.read_text(encoding="utf-8")
a = t.find("    def compare_forecast_models")
b = t.find("    def generate_forecast_insight")
assert a > 0 and b > a, (a, b)

new = '''
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
        growth_factor: float = 0.0,
        model_type: str = "Auto",
        seed: int = FORECAST_RANDOM_SEED,
        state: Optional[str] = None,
    ) -> Tuple[Optional[pd.DataFrame], str]:
        """
        Rolling-CV model selection (beat-MA gate), holiday-aware candidate,
        split-conformal intervals. Optional state-level series.
        """
        daily = self._daily_series(state=state)
        out, algo = self._forecast_backend.forecast(
            daily, horizon=horizon, model_type=model_type, growth_factor=growth_factor
        )
        self._last_forecast_meta = dict(self._forecast_backend.last_meta)
        if state:
            self._last_forecast_meta["state"] = state
        self._model_comparison = self._forecast_backend.last_comparison
        return out, algo

'''

# Remove old methods that are now unused if still present (select_best might duplicate)
# Also remove orphan methods between - done by splice

t2 = t[:a] + new + t[b:]
# Remove leftover private forecast helpers that may still exist before compare - keep them for now
# Update generate_forecast_insight method text for conformal + rolling
t2 = t2.replace(
    '"model_comparison": meta.get("model_comparison"),\n        }\n'
    '        method = (\n'
    '            "Holdout evaluation of Seasonal (DOW×level), Linear (Ridge on t), and MovingAverage (7-day). "\n'
    '            "Auto-select minimizes holdout sMAPE. Intervals = residual bootstrap P10–P90."\n'
    "        )",
    '"model_comparison": meta.get("model_comparison"),\n'
    '            "rolling_smape_pct": (meta.get("rolling") or {}).get("rolling_smape_pct"),\n'
    '            "decision_band": meta.get("decision_band"),\n'
    '            "interval_method": meta.get("interval_method"),\n'
    '            "conformal_q": meta.get("conformal_q"),\n'
    '            "selection_reason": meta.get("selection"),\n'
    "        }\n"
    "        method = (\n"
    '            "Rolling-origin CV across Seasonal / Linear / MovingAverage / SeasonalHoliday; "\n'
    '            "auto-select beats MovingAverage only if mean sMAPE is strictly better; "\n'
    '            "intervals = split conformal absolute residual quantile."\n'
    "        )",
)

p.write_text(t2, encoding="utf-8")
print("patched ai_core forecast section")
