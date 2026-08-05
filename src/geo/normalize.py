"""State name canonicalization against official list + alias map."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.config import OFFICIAL_STATES_PATH, STATE_ALIASES_PATH


def _normalize_key(name: str) -> str:
    """Lowercase, collapse whitespace, unify &/and for alias lookup."""
    s = str(name).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


@lru_cache(maxsize=1)
def load_official_states(path: Optional[str] = None) -> List[str]:
    p = Path(path) if path else OFFICIAL_STATES_PATH
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return list(data)


@lru_cache(maxsize=1)
def load_state_aliases(path: Optional[str] = None) -> Dict[str, str]:
    p = Path(path) if path else STATE_ALIASES_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    # Keys already lower; re-key through normalizer for safety
    return {_normalize_key(k): v for k, v in raw.items()}


def canonicalize_state(name, aliases: Optional[Dict[str, str]] = None, official: Optional[List[str]] = None) -> str:
    """
    Map a raw state string to a canonical official name when possible.
    Returns original title-cased string if no mapping found.
    """
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return "Unknown"

    raw = str(name).strip()
    if not raw or raw.lower() in {"nan", "none", "null"}:
        return "Unknown"

    # Purely numeric / garbage
    if re.fullmatch(r"\d+", raw):
        return "Unknown"

    aliases = aliases if aliases is not None else load_state_aliases()
    official = official if official is not None else load_official_states()
    official_set = set(official)
    official_by_key = {_normalize_key(s): s for s in official}

    key = _normalize_key(raw)

    if key in aliases:
        return aliases[key]

    if key in official_by_key:
        return official_by_key[key]

    # Title-case fallback (keep & style loosely)
    titled = re.sub(r"\s+", " ", raw).strip()
    titled = titled.title()
    titled = titled.replace(" And ", " & ")
    # Fix common title-case glitches
    titled = titled.replace("Nct Of Delhi", "Delhi")
    if titled in official_set:
        return titled
    tkey = _normalize_key(titled)
    if tkey in official_by_key:
        return official_by_key[tkey]
    if tkey in aliases:
        return aliases[tkey]

    return titled


def apply_state_canonicalization(series: pd.Series) -> pd.Series:
    """Vectorized via unique values — avoids per-row Python cost on multi-million rows."""
    aliases = load_state_aliases()
    official = load_official_states()
    uniques = pd.unique(series.astype(str))
    mapping = {u: canonicalize_state(u, aliases, official) for u in uniques}
    return series.astype(str).map(mapping)


def is_known_state(name: str, official: Optional[List[str]] = None) -> bool:
    official = official if official is not None else load_official_states()
    return canonicalize_state(name) in set(official)
