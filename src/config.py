"""Application configuration — paths and load-time defaults."""
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
OUTPUT_DIR = ROOT_DIR / "output"

# Ollama
OLLAMA_HOST = __import__("os").environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = __import__("os").environ.get("OLLAMA_MODEL", "qwen2.5:latest")

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
CACHE_SCHEMA_VERSION = 3

# Pincode validity (India)
PINCODE_MIN = 100000
PINCODE_MAX = 999999

# Forecast reproducibility
FORECAST_RANDOM_SEED = 42

# Auto-build parquet cache on cold CSV load when missing/stale
AUTO_BUILD_CACHE = True

# If True, never re-parse CSVs in the app — require valid processed marts
MARTS_ONLY = __import__("os").environ.get("MARTS_ONLY", "0") in ("1", "true", "True", "yes")

# Anomaly defaults (overridable in UI)
ANOMALY_CONTAMINATION = float(__import__("os").environ.get("ANOMALY_CONTAMINATION", "0.05"))
ANOMALY_MIN_VOLUME = int(__import__("os").environ.get("ANOMALY_MIN_VOLUME", "50"))

# Forecast model selection
FORECAST_CANDIDATES = ("Seasonal", "Linear", "MovingAverage")
FORECAST_HOLDOUT_DAYS = 14
