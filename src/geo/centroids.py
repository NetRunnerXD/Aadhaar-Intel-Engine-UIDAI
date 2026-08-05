"""District / state centroid lookup for geospatial research maps."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.config import ROOT_DIR

DISTRICT_CENTROIDS_PATH = ROOT_DIR / "assets" / "reference" / "district_centroids.json"

_STATE_CENTROIDS = {
    "Andhra Pradesh": [15.91, 79.74],
    "Arunachal Pradesh": [28.21, 94.72],
    "Assam": [26.20, 92.93],
    "Bihar": [25.09, 85.31],
    "Chhattisgarh": [21.27, 81.86],
    "Goa": [15.29, 74.12],
    "Gujarat": [22.25, 71.19],
    "Haryana": [29.05, 76.08],
    "Himachal Pradesh": [31.10, 77.17],
    "Jharkhand": [23.61, 85.27],
    "Karnataka": [15.31, 75.71],
    "Kerala": [10.85, 76.27],
    "Madhya Pradesh": [22.97, 78.65],
    "Maharashtra": [19.75, 75.71],
    "Manipur": [24.66, 93.90],
    "Meghalaya": [25.46, 91.36],
    "Mizoram": [23.16, 92.93],
    "Nagaland": [26.15, 94.56],
    "Odisha": [20.95, 85.09],
    "Punjab": [31.14, 75.34],
    "Rajasthan": [27.02, 74.21],
    "Sikkim": [27.53, 88.51],
    "Tamil Nadu": [11.12, 78.65],
    "Telangana": [18.11, 79.01],
    "Tripura": [23.94, 91.98],
    "Uttar Pradesh": [26.84, 80.94],
    "Uttarakhand": [30.06, 79.01],
    "West Bengal": [22.98, 87.85],
    "Delhi": [28.70, 77.10],
    "Chandigarh": [30.73, 76.77],
    "Ladakh": [34.15, 77.57],
    "Jammu & Kashmir": [33.77, 76.57],
    "Puducherry": [11.94, 79.80],
    "Lakshadweep": [10.57, 72.64],
    "Andaman & Nicobar Islands": [11.74, 92.65],
    "Dadra & Nagar Haveli And Daman & Diu": [20.18, 73.02],
}


def clean_district_name(name: str) -> str:
    s = str(name).strip()
    s = re.sub(r"[?]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    return s.strip()


@lru_cache(maxsize=1)
def load_district_centroids(path: Optional[str] = None) -> Dict[str, List[float]]:
    p = Path(path) if path else DISTRICT_CENTROIDS_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            out[k] = [float(v[0]), float(v[1])]
    return out


def geo_key(state: str, district: str) -> str:
    return f"{str(state).strip()}|{clean_district_name(district)}"


def resolve_centroid(state: str, district: str) -> Tuple[float, float, str]:
    """Return (lat, lon, source) where source is district | state | default."""
    dcent = load_district_centroids()
    key = geo_key(state, district)
    if key in dcent:
        lat, lon = dcent[key]
        return lat, lon, "district"

    st = str(state).strip()
    dist = clean_district_name(district).lower()
    for k, v in dcent.items():
        if not k.startswith(st + "|"):
            continue
        dname = k.split("|", 1)[-1].lower()
        if dist == dname or dist in dname or dname in dist:
            return v[0], v[1], "district"

    s = str(state)
    if s in _STATE_CENTROIDS:
        return _STATE_CENTROIDS[s][0], _STATE_CENTROIDS[s][1], "state"
    alt = s.replace(" And ", " & ")
    if alt in _STATE_CENTROIDS:
        return _STATE_CENTROIDS[alt][0], _STATE_CENTROIDS[alt][1], "state"
    return 22.0, 79.0, "default"
