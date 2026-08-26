"""Application configuration — paths and load-time defaults."""
import os
from pathlib import Path

# Project root (parent of src/)
ROOT_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MANIFEST_PATH = PROCESSED_DIR / "manifest.json"
GEOJSON_PATH = ROOT_DIR / "assets" / "india_states.geojson"
STATE_ALIASES_PATH = ROOT_DIR / "assets" / "reference" / "state_aliases.json"
OFFICIAL_STATES_PATH = ROOT_DIR / "assets" / "reference" / "official_states.json"
DISTRICT_AS_STATE_PATH = ROOT_DIR / "assets" / "reference" / "district_as_state.json"
DISTRICT_ALIASES_PATH = ROOT_DIR / "assets" / "reference" / "district_aliases.json"
TELANGANA_DISTRICTS_PATH = ROOT_DIR / "assets" / "reference" / "telangana_districts.json"
PIN_PREFIX_STATES_PATH = ROOT_DIR / "assets" / "reference" / "pin_prefix_states.json"
EVAL_GEO_GOLD_PATH = ROOT_DIR / "assets" / "reference" / "eval_geo_gold.json"
RULES_MANIFEST_PATH = ROOT_DIR / "assets" / "reference" / "rules_manifest.json"
INDIA_HOLIDAYS_PATH = ROOT_DIR / "assets" / "reference" / "india_holidays.json"
OUTPUT_DIR = ROOT_DIR / "output"

# Ollama
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:latest")

# Natural key for de-duplication / aggregation (pin grain)
NATURAL_KEY = ["date", "state", "district", "pincode"]
# Analytics grain (faster marts)
DAILY_KEY = ["date", "state", "district"]

# Processed parquet names
MART_ENROL_DAILY = "fact_enrol_daily.parquet"
MART_BIO_DAILY = "fact_bio_daily.parquet"
MART_DEMO_DAILY = "fact_demo_daily.parquet"
MART_AGG_DISTRICT = "agg_district.parquet"
MART_DIM_GEO = "dim_geo.parquet"

# Cache schema version — bump when mart layout / repair rules change
CACHE_SCHEMA_VERSION = 4
GEO_RULE_PACK_VERSION = "1.1.0"

# Pincode validity (India)
PINCODE_MIN = 100000
PINCODE_MAX = 999999

# Forecast reproducibility
FORECAST_RANDOM_SEED = 42

# Auto-build parquet cache on cold CSV load when missing/stale
AUTO_BUILD_CACHE = True

# If True, never re-parse CSVs in the app — require valid processed marts
MARTS_ONLY = os.environ.get("MARTS_ONLY", "0") in ("1", "true", "True", "yes")

# Anomaly defaults (overridable in UI)
ANOMALY_CONTAMINATION = float(os.environ.get("ANOMALY_CONTAMINATION", "0.05"))
ANOMALY_MIN_VOLUME = int(os.environ.get("ANOMALY_MIN_VOLUME", "50"))

# Forecast model selection — top performers kept in the bake-off (MASE on national series)
# Order is display-only; selection sorts by FORECAST_PRIMARY_METRIC
FORECAST_CANDIDATES = (
    "MovingAverage",
    "Drift",
    "Ensemble",
    "SeasonalNaive",
)
FORECAST_HOLDOUT_DAYS = 14
FORECAST_ROLLING_FOLDS = 4
FORECAST_ROLLING_STEP = 7
FORECAST_MIN_TRAIN_DAYS = 40
# Prefer full history; models may still clip extremely long series
FORECAST_MAX_HISTORY_DAYS = 400
# Primary metric for Auto ranking: "mase" | "smape_pct" | "rmse"
FORECAST_PRIMARY_METRIC = "mase"
# Non-baseline must beat both SeasonalNaive and MA by this margin on primary metric
FORECAST_BEAT_BASELINE_EPS = 0.0
# Legacy alias used by older call sites
FORECAST_BEAT_MA_EPS = FORECAST_BEAT_BASELINE_EPS
# Conformal residual level (e.g. 0.1 → ~90% interval under exchangeability)
FORECAST_CONFORMAL_ALPHA = 0.1
# Complete missing calendar days with 0 (preserves DOW / holiday structure)
FORECAST_FILL_MISSING_DAYS = True

# Decision thresholds on rolling mean sMAPE (documented ops guidance)
FORECAST_SMAPE_THRESHOLDS = {
    "tight": 20.0,       # sMAPE < 20: usable for short-horizon staffing bands
    "directional": 40.0, # 20–40: directional only
    # >= 40: exploratory / monitor actuals
}
# Parallel MASE bands (lower is better; ~1.0 = seasonal-naive quality)
FORECAST_MASE_THRESHOLDS = {
    "tight": 0.85,
    "directional": 1.15,
}

ANOMALY_SMAPE_NOTE = "Anomaly scores are unsupervised; not calibrated to fraud labels."
