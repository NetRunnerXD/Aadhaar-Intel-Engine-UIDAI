# -*- coding: utf-8 -*-
"""Capture live Streamlit UI screenshots + live plotly charts for the paper."""
from __future__ import annotations

import time
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

# White background for print-friendly paper figures
pio.templates.default = "plotly_white"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "live_captures"
OUT.mkdir(parents=True, exist_ok=True)

APP_URL = "http://127.0.0.1:8501"


def capture_ui():
    from playwright.sync_api import sync_playwright

    shots = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(APP_URL, wait_until="networkidle", timeout=180_000)
        page.wait_for_selector("[data-testid='stAppViewContainer']", timeout=120_000)
        # Wait for KPI numbers / main header
        try:
            page.get_by_text("Research Dashboard", exact=False).wait_for(timeout=120_000)
        except Exception:
            page.wait_for_timeout(15_000)
        page.wait_for_timeout(8000)
        # Let LLM brief finish if it auto-runs
        try:
            page.get_by_text("Writing grounded", exact=False).wait_for(state="hidden", timeout=90_000)
        except Exception:
            page.wait_for_timeout(5000)

        def shot(name: str):
            path = OUT / f"{name}.png"
            page.screenshot(path=str(path), full_page=True)
            shots[name] = path
            print("saved", path, path.stat().st_size)

        # Dashboard (default)
        shot("01_dashboard")

        # Navigate via sidebar radio labels
        modules = [
            ("Analytics", "02_analytics"),
            ("Forecast", "03_forecast"),
            ("Geospatial Intel", "04_geospatial"),
            ("Data Governance", "05_governance"),
            ("Dashboard", "01_dashboard"),  # re-capture dashboard after warm
        ]

        for label, name in modules:
            try:
                # Streamlit radio options
                loc = page.get_by_text(label, exact=True)
                if loc.count() == 0:
                    loc = page.locator(f"label:has-text('{label}')")
                loc.first.click(timeout=15_000)
                page.wait_for_timeout(6000)
                # expand AI brief if present
                for exp in ("AI analysis", "AI research brief", "Research brief", "AI insight", "AI governance"):
                    try:
                        el = page.get_by_text(exp, exact=False)
                        if el.count():
                            el.first.click(timeout=2000)
                            page.wait_for_timeout(1500)
                    except Exception:
                        pass
                # Forecast: ensure bake-off visible
                if "Forecast" in label:
                    page.wait_for_timeout(3000)
                # Governance: try start scan if button exists
                if "Governance" in label:
                    for btn in ("Start State Scan", "Start District Scan"):
                        try:
                            b = page.get_by_role("button", name=btn)
                            if b.count():
                                b.first.click(timeout=3000)
                                page.wait_for_timeout(4000)
                        except Exception:
                            pass
                shot(name)
            except Exception as e:
                print("nav fail", label, e)
                shot(name + "_partial")

        browser.close()
    return shots


def capture_live_charts():
    """Generate paper figures from the same data pipeline the app uses."""
    import sys

    sys.path.insert(0, str(ROOT))
    from src.ai_core import AnalyticsEngine
    from src.config import DATA_DIR, PROCESSED_DIR
    from src.data_manager import DataLoader

    loader = DataLoader(str(DATA_DIR), processed_path=PROCESSED_DIR, prefer_cache=True)
    enrol, demo, bio, logs = loader.get_data()
    eng = AnalyticsEngine(enrol, demo, bio)

    paths = {}

    # Workload pie
    corr = eng.get_correlation()
    vals = [
        float(corr["Enrolments"].sum()) if not corr.empty else 0,
        float(corr["Bio_Updates"].sum()) if not corr.empty else 0,
        float(corr["Demo_Updates"].sum()) if not corr.empty else 0,
    ]
    fig = px.pie(
        names=["New enrolments", "Biometric updates", "Demographic updates"],
        values=vals,
        hole=0.45,
        title="Workload mix (live data)",
        color_discrete_sequence=["#10b981", "#f59e0b", "#8b5cf6"],
    )
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=420, width=640, font=dict(size=12))
    p = OUT / "chart_workload_mix.png"
    fig.write_image(str(p), scale=2)
    paths["workload"] = p
    print("chart", p)

    # Anomaly bar (district cells)
    anom = eng.get_anomalies(contamination=0.05, min_volume=50, force=True)
    if not anom.empty:
        top = anom.head(10).copy()
        top["label"] = top["district"].astype(str) + " (" + top["state"].astype(str).str[:12] + ")"
        fig = px.bar(
            top,
            x="risk_score",
            y="label",
            orientation="h",
            color="risk_score",
            color_continuous_scale="Reds",
            title="Top risk cells — Isolation Forest (live)",
            hover_data=[c for c in ("reason", "volume") if c in top.columns],
        )
        fig.update_layout(
            margin=dict(l=20, r=20, t=50, b=20),
            height=480,
            width=720,
            yaxis={"categoryorder": "total ascending"},
            coloraxis_showscale=False,
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
        )
        p = OUT / "chart_anomalies.png"
        fig.write_image(str(p), scale=2)
        paths["anomalies"] = p
        print("chart", p)

        # State risk radar — top 10 by flagged volume (matches Analytics UI)
        volc = next((c for c in ("volume", "total_enrolments", "adult_enrolments") if c in anom.columns), None)
        work = anom.copy()
        work["state"] = work["state"].astype(str)
        work["risk_score"] = work["risk_score"].astype(float)
        agg = {
            "max_risk": ("risk_score", "max"),
            "mean_risk": ("risk_score", "mean"),
            "flags": ("risk_score", "count"),
        }
        if volc:
            work[volc] = work[volc].astype(float)
            agg["flagged_volume"] = (volc, "sum")
        stsum = work.groupby("state", observed=True).agg(**agg).reset_index()
        if "flagged_volume" in stsum.columns:
            stsum = stsum.sort_values("flagged_volume", ascending=False).head(10)
        else:
            stsum = stsum.sort_values("max_risk", ascending=False).head(10)

        def _fmt_vol(v):
            try:
                v = float(v)
            except Exception:
                return "—"
            if v >= 1_000_000:
                return f"{v/1e6:.1f}M"
            if v >= 1_000:
                return f"{v/1e3:.1f}k"
            return f"{int(v)}"

        labels = []
        for _, row in stsum.iterrows():
            vol_txt = _fmt_vol(row["flagged_volume"]) if "flagged_volume" in stsum.columns else "—"
            labels.append(f"{row['state']}<br>vol {vol_txt}")
        r_max = stsum["max_risk"].astype(float).tolist()
        r_mean = stsum["mean_risk"].astype(float).tolist()
        theta = labels
        fig = go.Figure()
        fig.add_trace(
            go.Scatterpolar(
                r=r_max + [r_max[0]],
                theta=theta + [theta[0]],
                fill="toself",
                name="Max risk",
                mode="lines+markers",
                line=dict(color="#dc2626", width=2),
                fillcolor="rgba(220,38,38,0.22)",
            )
        )
        fig.add_trace(
            go.Scatterpolar(
                r=r_mean + [r_mean[0]],
                theta=theta + [theta[0]],
                fill="toself",
                name="Mean risk",
                mode="lines",
                line=dict(color="#f59e0b", width=1.5, dash="dot"),
                fillcolor="rgba(245,158,11,0.12)",
            )
        )
        max_axis = max(100, int(max(r_max)) + 8)
        fig.update_layout(
            title="Risk radar — top 10 states by flagged volume (live)",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            height=520,
            width=720,
            margin=dict(l=70, r=70, t=60, b=50),
            legend=dict(orientation="h", y=1.08),
            polar=dict(
                bgcolor="#ffffff",
                radialaxis=dict(range=[0, max_axis], title="Risk score", gridcolor="#e2e8f0"),
                angularaxis=dict(rotation=90, direction="clockwise", gridcolor="#e2e8f0"),
            ),
        )
        p = OUT / "chart_risk_radar.png"
        fig.write_image(str(p), scale=2)
        paths["risk_radar"] = p
        print("chart", p)

    # Forecast
    fc, label = eng.forecast_trends(horizon=30, model_type="Auto")
    vol = "total_enrolments" if "total_enrolments" in enrol.columns else "adult_enrolments"
    hist = (
        enrol.groupby("date", observed=True)[vol]
        .sum()
        .reset_index()
        .sort_values("date")
        .tail(90)
    )
    # kaleido cannot serialize pandas Timestamp
    hx = hist["date"].astype(str).tolist()
    hy = hist[vol].astype(float).tolist()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=hx, y=hy, name="Historical", line=dict(color="#2563eb", width=2))
    )
    if fc is not None and not fc.empty:
        fx = fc["date"].astype(str).tolist()
        fig.add_trace(
            go.Scatter(
                x=fx + fx[::-1],
                y=fc["upper"].astype(float).tolist() + fc["lower"].astype(float).tolist()[::-1],
                fill="toself",
                fillcolor="rgba(245, 158, 11, 0.2)",
                line=dict(color="rgba(0,0,0,0)"),
                name="P10–P90",
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=fx,
                y=fc["predicted"].astype(float).tolist(),
                name=f"Forecast ({label})",
                line=dict(color="#d97706", width=2, dash="dash"),
            )
        )
    meta = eng._last_forecast_meta or {}
    bt = meta.get("backtest") or {}
    title = f"National daily enrolments — {label}"
    if bt.get("smape_pct") is not None:
        title += f"  |  holdout sMAPE {bt['smape_pct']}%"
    fig.update_layout(
        title=title,
        margin=dict(l=40, r=20, t=60, b=40),
        height=420,
        width=780,
        legend=dict(orientation="h", y=1.08),
        xaxis_title="Date",
        yaxis_title="Daily volume",
    )
    p = OUT / "chart_forecast.png"
    fig.write_image(str(p), scale=2)
    paths["forecast"] = p
    print("chart", p)

    # Simple architecture-style diagram as HTML/plotly annotation is hard;
    # write a clean matplotlib flowchart
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

        fig, ax = plt.subplots(figsize=(8.5, 2.8))
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 3)
        ax.axis("off")
        boxes = [
            (0.3, 1.0, "Raw CSV\nshards"),
            (2.3, 1.0, "Clean &\ngeo repair"),
            (4.3, 1.0, "Parquet\ndaily marts"),
            (6.3, 1.0, "Analytics\nengine"),
            (8.2, 1.0, "Streamlit\n+ LLM brief"),
        ]
        for x, y, text in boxes:
            ax.add_patch(
                FancyBboxPatch(
                    (x, y),
                    1.5,
                    1.1,
                    boxstyle="round,pad=0.05,rounding_size=0.15",
                    facecolor="#e8f1fb",
                    edgecolor="#1e3a5f",
                    linewidth=1.5,
                )
            )
            ax.text(x + 0.75, y + 0.55, text, ha="center", va="center", fontsize=9, color="#0f172a")
        for i in range(len(boxes) - 1):
            x1 = boxes[i][0] + 1.5
            x2 = boxes[i + 1][0]
            ax.annotate(
                "",
                xy=(x2, 1.55),
                xytext=(x1, 1.55),
                arrowprops=dict(arrowstyle="->", color="#334155", lw=1.5),
            )
        ax.set_title("Aadhaar Intel Engine — data path (live pipeline)", fontsize=11, pad=8)
        p = OUT / "chart_architecture.png"
        fig.tight_layout()
        fig.savefig(str(p), dpi=180, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        paths["architecture"] = p
        print("chart", p)
    except Exception as e:
        print("arch diagram fail", e)

    # Bake-off table as image for paper optional
    cmp = eng.compare_forecast_models()
    if not cmp.empty:
        fig = go.Figure(
            data=[
                go.Table(
                    header=dict(
                        values=list(cmp.columns),
                        fill_color="#dbeafe",
                        align="center",
                        font=dict(size=12),
                    ),
                    cells=dict(
                        values=[cmp[c].tolist() for c in cmp.columns],
                        align="center",
                        font=dict(size=11),
                        height=28,
                    ),
                )
            ]
        )
        fig.update_layout(title="Forecast model bake-off (live holdout)", margin=dict(l=10, r=10, t=40, b=10), height=280, width=780)
        p = OUT / "chart_bakeoff.png"
        fig.write_image(str(p), scale=2)
        paths["bakeoff"] = p
        print("chart", p)

    return paths


if __name__ == "__main__":
    print("Capturing live charts from data pipeline...")
    charts = capture_live_charts()
    print("Capturing UI screenshots from", APP_URL)
    try:
        ui = capture_ui()
    except Exception as e:
        print("UI capture failed:", e)
        ui = {}
    print("Done. Charts:", list(charts.keys()), "UI:", list(ui.keys()))
