"""Shared filter helpers applied across all dashboard modules."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None


def get_active_filters() -> Dict[str, Any]:
    if st is None:
        return {"state": [], "date_range": None}
    filters = st.session_state.get("active_filters", {})
    return {
        "state": filters.get("state") or [],
        "date_range": filters.get("date_range"),
    }


def apply_filters(
    df: pd.DataFrame,
    states: Optional[List[str]] = None,
    date_range=None,
    use_session: bool = True,
) -> pd.DataFrame:
    """
    Filter a dataframe by optional state list and date range.

    date_range: (start_date, end_date) as date/datetime, or None.
    When use_session=True and args are None, pulls from session_state.
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    if use_session and st is not None:
        active = get_active_filters()
        if states is None:
            states = active.get("state") or []
        if date_range is None:
            date_range = active.get("date_range")

    out = df
    if states and "state" in out.columns:
        out = out[out["state"].isin(states)]

    if date_range and "date" in out.columns and len(date_range) == 2:
        start, end = date_range[0], date_range[1]
        if start is not None and end is not None:
            dates = pd.to_datetime(out["date"], errors="coerce")
            start_ts = pd.Timestamp(start)
            end_ts = pd.Timestamp(end)
            # Inclusive end-of-day for pure dates
            if end_ts == end_ts.normalize():
                end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
            out = out.loc[(dates >= start_ts) & (dates <= end_ts)]

    return out
