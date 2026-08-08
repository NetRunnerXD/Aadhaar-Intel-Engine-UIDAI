# Streamlit ↔ React feature parity

## Summary

React professional UI (`python run_web.py`) is brought to **feature parity** with Streamlit modules. Streamlit remains available via `streamlit run app.py`.

## Gaps that were closed (parity pass)

### Global
- All states in filter (search + select all / clear)
- Date range, reset/reload, MARTS_ONLY + data quality drawer (load_report + logs)
- Collapsible sidebar (persisted), mobile menu

### Dashboard
- Adult 18+ delta, anomaly params, auto AI analysis
- Age mix **donut**, workload pie, risk bar chart
- Investigation table (volume, ratios, cv, notes), Open Governance
- 30-day outlook + peak/floor/sMAPE, system logs

### Analytics
- Adult KPI, bio/demo ratios, low-volume watchlist
- Risk radar + scatter, investigation notes
- Export pack: regional / trends / risk / ops CSV

### Forecast
- Per-state series scope, resource planning, methods + CSV download
- Auto AI analysis, full bake-off metrics

### Geospatial
- KPIs (volume, hotspot, districts)
- Mode 2D / heatmap / volumetric, depth (Top 5 default), log/linear scale — same as Streamlit command center
- Carto Positron basemap, state GeoJSON borders, district centroids + jitter, intensity legend
- deck.gl Scatterplot / Heatmap / Column layers with Streamlit-matched radius & elevation scaling
- Centroid source counts, CSV exports (full, top 20 districts, top 10 states)

### Governance
- Tabs: Fix / Audit & Revert / Import-Export
- Merge / Delete / Ignore + target override, pagination, merge all, auto-fix
- Revert selected / all, audit filters, pack JSON import/export, deletion counts

## Intentional presentation differences
- Map HTML export (pydeck `to_html`) is Streamlit-only
- Styling is custom React (not Streamlit chrome)
