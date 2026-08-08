# -*- coding: utf-8 -*-
"""
AI analysis insights — operational, not a research paper.

Hybrid design:
  - Key numbers are ALWAYS engine-authored (LLM never invents metrics).
  - LLM writes short Insights + Actions.
  - Offline / failure → deterministic Insights + Actions from the same evidence.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from src.ai.ollama_client import OllamaClient, get_ollama_client, strip_model_artifacts


ANALYSIS_SYSTEM = """You are an operations analyst for Aadhaar (UIDAI) enrolment and update data.

Audience: programme managers and data stewards. Tone: clear, direct, practical.

Hard rules:
1. Use ONLY facts in the provided Evidence. Never invent counts, %, districts, dates, or model scores.
2. Do NOT invent or restate MASE, sMAPE, MAPE, RMSE, or other model-error scores. The engine already printed those; you interpret meaning only (e.g. "error is high", "band is directional").
3. Do NOT claim fraud, ghost beneficiaries, migration crime, or policy success/failure.
4. Write exactly two sections with these headings:

### Insights
2–4 short bullets. What the numbers mean in plain language (volume, risk flags, forecast quality, name quality).
Do not quote MASE/sMAPE figures.

### Actions
2–4 concrete next steps an operator can take this week (review cells, re-scan names, monitor actuals vs forecast, adjust staffing envelope, merge suggested names, change contamination, etc.).
Each action should be specific and tied to the evidence.

5. Do not write a research paper. No Method, Limitations, Abstract, or long essays.
6. Optional single line at the end starting with "Caveat:" only if uncertainty is high.
7. Markdown bullets only. No preamble or closing pleasantries.
"""

FEW_SHOT_USER = """Title: Forecast analysis
Evidence summary:
- selected_model: MovingAverage
- mase: 0.99
- smape_pct: 33.4
- change_pct: 4.2
- peak: 72000
- floor: 51000
- horizon_days: 30
- decision_band: directional
- data_end: 2025-12-31

Write ### Insights and ### Actions. Do not restate MASE/sMAPE numbers."""

FEW_SHOT_ASSISTANT = """### Insights
- Selected path is **MovingAverage**; quality is near seasonal-naive (useful for trend, not exact daily hits).
- 30-day path is roughly a **4.2%** rise; expected daily range about **51k–72k**.
- Decision band is **directional** — plan envelopes, not day-exact quotas.

### Actions
- Use the path for a wide staffing envelope (peak ~72k), not daily quotas.
- Compare actual enrolments to the forecast each Monday; widen plans if misses exceed the conformal band.
- Keep scenario shock at 0% until error metrics improve or more history is available.
Caveat: multi-step intervals are approximate; re-check after large reporting lag days.
"""

# LLM must not invent bake-off error scores; engine owns those figures
_METRIC_CLAIM_RE = re.compile(
    r"\b(mase|smape|mape|nrmse|rmse)\b|"
    r"\b(?:smape|mape)\s*(?:of|=|:)?\s*\d|"
    r"\b\d+(?:\.\d+)?\s*%\s*(?:smape|mape)\b",
    re.I,
)


def _fmt_num(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        if abs(v) >= 10:
            return f"{v:,.1f}"
        # Keep bake-off precision (MASE often 3–4 decimals; sMAPE already %)
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s if s else "0"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _humanize_key(key: str) -> str:
    return key.replace("_", " ").strip()


def compact_evidence(evidence: Dict[str, Any], max_items: int = 18) -> Dict[str, Any]:
    """Shrink evidence for the LLM: drop huge nested structures, format numbers."""
    skip_nested = {"model_comparison", "sample", "top_risk_cells", "top_risk_districts"}
    priority = [
        "selected_model",
        "selection_mode",
        "series_scope",
        # Canonical selected-model metrics (match bake-off / UI KPIs)
        "mase",
        "smape_pct",
        "metric_source",
        "decision_band",
        "primary_metric",
        "change_pct",
        "peak",
        "floor",
        "horizon_days",
        "train_days",
        "data_end",
        "data_as_of",
        # Secondary detail (not mixed into the primary score line)
        "rolling_mase",
        "rolling_smape_pct",
        "holdout_mase",
        "holdout_smape_pct",
        "holdout_mape_pct",
        "holdout_rmse",
        "total_enrolments",
        "biometric_updates",
        "demographic_updates",
        "bio_per_enrol",
        "demo_per_enrol",
        "anomaly_count",
        "contamination",
        "min_volume",
        "active_states",
        "unit_of_analysis",
        "open_issues",
        "high_conf_gt_0_9",
    ]
    out: Dict[str, Any] = {}
    has_canonical = evidence.get("mase") is not None or evidence.get("smape_pct") is not None
    # When canonical selected-model scores exist, omit holdout/rolling aliases so the LLM
    # cannot mix single-holdout sMAPE with rolling MASE.
    secondary_metrics = {
        "rolling_mase",
        "rolling_smape_pct",
        "holdout_mase",
        "holdout_smape_pct",
        "holdout_mape_pct",
        "holdout_rmse",
    }
    for k in priority:
        if has_canonical and k in secondary_metrics:
            continue
        if k in evidence and evidence[k] is not None:
            out[k] = evidence[k]
    for k, v in evidence.items():
        if k in out or k in skip_nested:
            continue
        if has_canonical and k in secondary_metrics:
            continue
        if isinstance(v, (dict, list)) and k not in ("top_flagged_cells",):
            continue
        if len(out) >= max_items:
            break
        out[k] = v
    # compact list fields
    for list_key in ("top_flagged_cells", "top_risk_cells", "example_issues"):
        if list_key in evidence and evidence[list_key] is not None:
            raw = evidence[list_key]
            if isinstance(raw, list):
                out[list_key] = raw[:5]
            else:
                out[list_key] = raw
    return out


def evidence_markdown(evidence: Dict[str, Any]) -> str:
    compact = compact_evidence(evidence, max_items=24)
    lines = []
    for k, v in compact.items():
        if isinstance(v, list):
            lines.append(f"- **{_humanize_key(k)}**:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- **{_humanize_key(k)}**: {_fmt_num(v) if isinstance(v, (int, float)) else v}")
    return "\n".join(lines)


def _selected_scores(evidence: Dict[str, Any]) -> Tuple[Any, Any]:
    """Canonical MASE / sMAPE for the selected model (bake-off row)."""
    e = evidence or {}
    mase = e.get("mase")
    if mase is None:
        mase = e.get("rolling_mase") if e.get("rolling_mase") is not None else e.get("holdout_mase")
    smape = e.get("smape_pct")
    if smape is None:
        smape = (
            e.get("rolling_smape_pct")
            if e.get("rolling_smape_pct") is not None
            else e.get("holdout_smape_pct")
        )
    return mase, smape


def locked_forecast_metric_bullet(evidence: Dict[str, Any]) -> Optional[str]:
    """
    Engine-authored line that must match the model comparison table for the selected model.
    Always preferred over any LLM-written scores.
    """
    e = evidence or {}
    model = e.get("selected_model")
    if model is None:
        return None
    mase, smape = _selected_scores(e)
    bits = [f"Selected model **{model}**"]
    if mase is not None:
        mase_s = str(mase) if not isinstance(mase, float) else (
            f"{mase:.4f}".rstrip("0").rstrip(".") if mase != int(mase) else str(int(mase))
        )
        bits.append(f"MASE {mase_s}")
    if smape is not None:
        smape_s = str(smape) if not isinstance(smape, float) else (
            f"{smape:.4f}".rstrip("0").rstrip(".") if smape != int(smape) else str(int(smape))
        )
        bits.append(f"sMAPE {smape_s}%")
    if e.get("decision_band"):
        bits.append(f"band **{e['decision_band']}**")
    return " · ".join(bits) + "."


def _scrub_metric_claims(bullets: List[str]) -> List[str]:
    """Drop LLM bullets that restate MASE/sMAPE/etc. so they cannot disagree with the table."""
    out: List[str] = []
    for b in bullets or []:
        if _METRIC_CLAIM_RE.search(b):
            continue
        out.append(b)
    return out


def _auto_insights(evidence: Dict[str, Any]) -> List[str]:
    e = compact_evidence(evidence)
    bullets: List[str] = []

    locked = locked_forecast_metric_bullet(evidence)
    if locked:
        bullets.append(locked)
    elif e.get("selected_model") is not None:
        bits = [f"Selected model **{e['selected_model']}**"]
        if e.get("decision_band"):
            bits.append(f"band **{e['decision_band']}**")
        if e.get("series_scope"):
            bits.append(f"scope **{e['series_scope']}**")
        bullets.append(" · ".join(bits) + ".")

    if e.get("change_pct") is not None:
        try:
            ch = float(e["change_pct"])
            direction = "up" if ch >= 0 else "down"
            bullets.append(
                f"Point path is about **{_fmt_num(abs(ch))}% {direction}** over "
                f"{e.get('horizon_days', 'the')} days "
                f"(peak {_fmt_num(e.get('peak'))}, floor {_fmt_num(e.get('floor'))})."
            )
        except (TypeError, ValueError):
            pass

    if e.get("anomaly_count") is not None:
        n = int(e["anomaly_count"])
        if n == 0:
            bullets.append("No state×district cells exceed the multi-feature risk threshold under current settings.")
        else:
            bullets.append(
                f"**{_fmt_num(n)}** state×district cells flagged "
                f"(contamination={e.get('contamination', 'n/a')}, min volume={e.get('min_volume', 'n/a')})."
            )

    if e.get("bio_per_enrol") is not None:
        bullets.append(
            f"Updates dominate new enrolment: bio/enrol ≈ **{_fmt_num(e.get('bio_per_enrol'))}**, "
            f"demo/enrol ≈ **{_fmt_num(e.get('demo_per_enrol'))}**."
        )

    if e.get("open_issues") is not None:
        bullets.append(
            f"**{_fmt_num(e.get('open_issues'))}** residual place-name issues remain "
            f"({_fmt_num(e.get('high_conf_gt_0_9'))} with similarity > 0.9)."
        )

    if e.get("top_flagged_cells"):
        bullets.append(f"Highest-priority flag: {e['top_flagged_cells'][0]}.")

    if not bullets:
        bullets.append("Engine metrics are listed under Key numbers; no strong directional claim yet.")
    return bullets[:4]


def _auto_actions(evidence: Dict[str, Any]) -> List[str]:
    e = compact_evidence(evidence)
    actions: List[str] = []

    # Same metric pair as insights / bake-off table (do not mix holdout sMAPE with rolling MASE)
    smape = e.get("smape_pct")
    if smape is None:
        smape = e.get("rolling_smape_pct") if e.get("rolling_smape_pct") is not None else e.get("holdout_smape_pct")
    mase = e.get("mase")
    if mase is None:
        mase = e.get("rolling_mase") if e.get("rolling_mase") is not None else e.get("holdout_mase")
    band = str(e.get("decision_band") or "")
    try:
        s = float(smape) if smape is not None else None
    except (TypeError, ValueError):
        s = None
    try:
        m = float(mase) if mase is not None else None
    except (TypeError, ValueError):
        m = None

    if e.get("selected_model") is not None:
        if (m is not None and m >= 1.15) or (s is not None and s >= 40) or band == "exploratory":
            actions.append(
                "Treat the forecast as exploratory: monitor actuals daily and avoid hard staffing quotas from the point path."
            )
        elif band == "directional" or (s is not None and s >= 20) or (m is not None and m >= 0.85):
            actions.append(
                "Use the forecast for a wide staffing envelope (peak/floor); re-check actuals vs band each week."
            )
        else:
            actions.append(
                f"Use **{e['selected_model']}** as the planning baseline; keep scenario shock near 0% unless you have a known campaign."
            )

    if e.get("anomaly_count") is not None and int(e.get("anomaly_count") or 0) > 0:
        actions.append(
            "Open Analytics → Risk radar and review top flagged state×district cells (volume, volatility, bio/demo ratios)."
        )

    if e.get("open_issues") is not None and int(e.get("open_issues") or 0) > 0:
        n_hi = e.get("high_conf_gt_0_9")
        if n_hi is not None and int(n_hi) > 0:
            actions.append(
                f"In Data Governance, Auto-Fix or Merge all on **{_fmt_num(n_hi)}** high-confidence name matches, then re-scan."
            )
        else:
            actions.append("In Data Governance, review pending name issues and Merge suggested targets where correct.")

    if e.get("bio_per_enrol") is not None:
        try:
            if float(e["bio_per_enrol"]) > 5:
                actions.append("Weight centre capacity plans toward biometric/demo update queues, not only new enrolments.")
        except (TypeError, ValueError):
            pass

    if not actions:
        actions.append("Refresh filters and re-run analysis after the next data load; combine metrics with local centre knowledge.")
    return actions[:4]


def _auto_caveat(evidence: Dict[str, Any]) -> Optional[str]:
    e = compact_evidence(evidence)
    if e.get("decision_band") == "exploratory":
        return "Caveat: error band is exploratory — do not treat point forecasts as commitments."
    if e.get("anomaly_count") is not None:
        return "Caveat: risk scores are unsupervised peer outliers, not fraud labels."
    if e.get("open_issues") is not None:
        return "Caveat: name repair is rule-based; confirm high-impact merges before bulk apply."
    return None


def format_analysis(
    title: str,
    insights: List[str],
    actions: List[str],
    evidence: Dict[str, Any],
    source_note: str,
    caveat: Optional[str] = None,
) -> str:
    ins = "\n".join(f"- {b}" for b in insights)
    act = "\n".join(f"- {b}" for b in actions)
    body = (
        f"### AI analysis — {title}\n\n"
        f"#### Insights\n{ins}\n\n"
        f"#### Actions\n{act}\n\n"
    )
    if caveat:
        body += f"{caveat}\n\n"
    body += f"#### Key numbers (engine)\n{evidence_markdown(evidence)}\n\n_{source_note}_"
    return body


def deterministic_analysis(
    title: str,
    evidence: Dict[str, Any],
    method: str = "",
    findings: Optional[List[str]] = None,
    limitations: Optional[List[str]] = None,
) -> str:
    """Offline / fallback analysis. `findings` maps to insights if provided."""
    insights = findings or _auto_insights(evidence)
    actions = _auto_actions(evidence)
    caveat = _auto_caveat(evidence)
    # optional one-line caveat from legacy limitations list
    if not caveat and limitations:
        caveat = f"Caveat: {limitations[0]}"
    return format_analysis(
        title,
        insights,
        actions,
        evidence,
        "Source: analytics engine (deterministic analysis)",
        caveat=caveat,
    )


# Back-compat name
deterministic_research_insight = deterministic_analysis


def _extract_section(text: str, name: str) -> str:
    pattern = rf"#{{2,4}}\s*{re.escape(name)}\s*\r?\n([\s\S]*?)(?=\r?\n#{{2,4}}\s|\Z)"
    m = re.search(pattern, text, flags=re.I)
    return m.group(1).strip() if m else ""


def _bullets(body: str) -> List[str]:
    if not body:
        return []
    lines = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*•]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        if line.lower().startswith("caveat:"):
            continue
        if line:
            lines.append(line)
    return lines


def _parse_llm_analysis(text: str) -> Tuple[List[str], List[str], Optional[str]]:
    text = strip_model_artifacts(text)
    insights = _bullets(_extract_section(text, "Insights") or _extract_section(text, "Finding"))
    actions = _bullets(
        _extract_section(text, "Actions")
        or _extract_section(text, "Action")
        or _extract_section(text, "Recommendations")
    )
    caveat = None
    for line in text.splitlines():
        if line.strip().lower().startswith("caveat:"):
            caveat = line.strip()
            break
    return insights, actions, caveat


def analysis_insight(
    title: str,
    evidence: Dict[str, Any],
    method: str = "",
    findings: Optional[List[str]] = None,
    limitations: Optional[List[str]] = None,
    use_llm: bool = True,
    client: Optional[OllamaClient] = None,
    focus: Optional[str] = None,
) -> str:
    """
    Hybrid AI analysis: Insights + Actions + engine Key numbers.
    """
    base = deterministic_analysis(title, evidence, method, findings, limitations)
    if not use_llm:
        return base

    client = client or get_ollama_client()
    status = client.status()
    if not status.available:
        return deterministic_analysis(title, evidence, method, findings, limitations).replace(
            "deterministic analysis",
            f"engine analysis · LLM offline ({status.error})",
        )

    compact = compact_evidence(evidence)
    focus_line = focus or "Emphasise practical insights and concrete operator actions."
    user = (
        f"Title: {title}\n"
        f"Focus: {focus_line}\n"
        f"Context (do not invent beyond Evidence): {method}\n\n"
        f"Evidence summary (authoritative — do not contradict):\n"
        f"{json.dumps(compact, indent=2, default=str)}\n\n"
        "Write ### Insights and ### Actions now."
    )

    try:
        text = client.chat(
            [
                {"role": "system", "content": ANALYSIS_SYSTEM},
                {"role": "user", "content": FEW_SHOT_USER},
                {"role": "assistant", "content": FEW_SHOT_ASSISTANT},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        llm_insights, llm_actions, llm_caveat = _parse_llm_analysis(text)
        # Engine-owned metric line first; strip any LLM bullets that restate MASE/sMAPE
        locked = locked_forecast_metric_bullet(evidence)
        llm_clean = _scrub_metric_claims(llm_insights or [])
        seed = findings or _auto_insights(evidence)
        seed_clean = [b for b in seed if b != locked]
        final_insights: List[str] = []
        if locked:
            final_insights.append(locked)
        for b in llm_clean + seed_clean:
            if b not in final_insights:
                final_insights.append(b)
        if not final_insights:
            final_insights = seed or _auto_insights(evidence)

        final_actions = _scrub_metric_claims(llm_actions or []) or _auto_actions(evidence)
        caveat = llm_caveat or _auto_caveat(evidence)

        if len(final_insights) < 1 and len(final_actions) < 1:
            return base + f"\n\n_LLM output incomplete; showing engine analysis. Raw: {text[:200]}_"

        return format_analysis(
            title,
            final_insights[:5],
            final_actions[:5],
            evidence,
            f"Source: hybrid · narrative by `{status.model}` · MASE/sMAPE from bake-off table",
            caveat=caveat,
        )
    except Exception as e:
        return base + f"\n\n_LLM call failed ({e}); engine analysis above._"


# Back-compat API used across the app
def research_insight(*args, **kwargs) -> str:
    return analysis_insight(*args, **kwargs)
