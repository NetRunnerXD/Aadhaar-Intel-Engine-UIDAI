from pathlib import Path

p = Path(r"D:\Project\Aadhaar-Intel-Engine-UIDAI\docs\build_symposium_paper.py")
t = p.read_text(encoding="utf-8")
start = t.find('donut = IMG / "efficiency_donut.png"')
end = t.find("# 5 Limitations")
assert start > 0 and end > start, (start, end)

new = r'''donut = IMG / "efficiency_donut.png"
if donut.exists():
    add_image(donut, 3.0)
else:
    placeholder_box("Figure 2 — Workload mix donut")
caption("Fig. 2. Workload mix (enrolments vs biometric vs demographic updates).")

add_mixed_para([("4.3 Anomaly detection and forecasting", True, False)], size=10, space_before=4, space_after=3)
add_para(
    "With contamination 0.05 and min_volume 50, dozens of (state, district) cells are flagged; drivers include "
    "volume vs state median, bio/demo ratios, volatility, and growth (Figure 3)—unsupervised outliers, not fraud "
    "adjudication. Table 2 shows a representative holdout bake-off: Moving Average lowest sMAPE (~33%), Linear "
    "competitive, Seasonal weaker. Auto mode deploys the winner with residual-bootstrap P10–P90 bands (Figure 4).",
    first_line=0.25,
    size=10,
)

anom = IMG / "anomaly_scatter.png"
if not anom.exists():
    anom = FIG / "AI_Anomaly_Detection.png"
if anom.exists():
    add_image(anom, 4.0)
else:
    placeholder_box("Figure 3 — Anomaly / risk radar")
caption("Fig. 3. Anomaly visualisation over district-scale units (unsupervised).")

add_table(
    ["Model", "Holdout MAPE (%)", "Holdout sMAPE (%)", "RMSE (approx.)"],
    [
        ["Moving Average (7-day)", "28.4", "33.4", "38.6k"],
        ["Linear Ridge", "28.6", "35.9", "41.1k"],
        ["Seasonal (DOW × level)", "46.6", "55.6", "49.7k"],
    ],
)
caption("Table 2. Representative 14-day holdout bake-off (national daily enrolments; rounded).")

fc = IMG / "stochastic_forecast.png"
if not fc.exists():
    fc = FIG / "AI_Forecast.png"
if fc.exists():
    add_image(fc, 4.2)
else:
    placeholder_box("Figure 4 — Forecast chart with confidence bands")
caption("Fig. 4. Historical series with selected model forecast and uncertainty band.")

add_mixed_para([("4.4 Interfaces", True, False)], size=10, space_before=4, space_after=3)
add_para(
    "Geospatial views use district centroids when known, else state centroids with jitter (centroid_source exposed). "
    "Governance supports residual fuzzy scans, high-confidence merges, audit/revert, and durable patch packs. "
    "Figure 5 shows the research dashboard; map/governance/AI-brief captures are placeholders in Appendix A.",
    first_line=0.25,
    size=10,
)

dash = IMG / "dashboard_main.png"
if dash.exists():
    add_image(dash, 4.2)
else:
    placeholder_box("Figure 5 — Research dashboard screenshot")
caption("Fig. 5. Research dashboard (KPIs, AI brief, age mix, risk monitor).")

placeholder_box(
    "Figs. 6–7 placeholders (camera-ready)",
    "[6: Geospatial map]  [7: Governance console and/or hybrid AI brief panel]",
)
caption("Figs. 6–7. Optional camera-ready UI screenshots.")

'''

t2 = t[:start] + new + t[end:]
t2 = t2.replace("add_image(arch, 4.8)", "add_image(arch, 4.0)")
t2 = t2.replace("add_image(arch, 5.9)", "add_image(arch, 4.0)")
# slightly smaller body for abstract block spacing
t2 = t2.replace("space_after=12, size=9)", "space_after=8, size=9)")
p.write_text(t2, encoding="utf-8")
print("OK patched")
