"""PIN prefix → state heuristic (postal circle approximation)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from src.config import PIN_PREFIX_STATES_PATH
from src.geo.normalize import canonicalize_state


@lru_cache(maxsize=1)
def load_pin_prefix_map(path: Optional[str] = None) -> Dict[str, str]:
    p = Path(path) if path else PIN_PREFIX_STATES_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    return {str(k): str(v) for k, v in raw.items() if not str(k).startswith("_")}


def state_from_pincode(pincode) -> Optional[str]:
    try:
        pin = int(pincode)
    except (TypeError, ValueError):
        return None
    if pin < 100000 or pin > 999999:
        return None
    prefix = f"{pin // 10000:02d}"  # first 2 digits
    mapping = load_pin_prefix_map()
    raw = mapping.get(prefix)
    if not raw:
        return None
    return canonicalize_state(raw)
