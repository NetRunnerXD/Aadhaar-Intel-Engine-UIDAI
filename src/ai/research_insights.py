"""
Research-structured AI insights.

Hybrid design:
  - Evidence block is ALWAYS engine-authored (numbers never invented by the LLM).
  - LLM writes Finding, Interpretation, and Limitations in plain language.
  - Offline / failure → high-quality deterministic narrative from the same evidence.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from src.ai.ollama_client import OllamaClient, get_ollama_client, strip_model_artifacts


RESEARCH_SYSTEM = """You are a senior quantitative analyst writing briefings for Aadhaar (UIDAI) operations research.

Audience: programme managers and data stewards. Tone: clear, professional, neutral.

Hard rules:
1. Use ONLY facts present in the provided Evidence. Never invent counts, %, districts, or dates.
2. Do NOT claim fraud, ghost beneficiaries, migration, or policy success/failure. Describe operational patterns only.
3. Prefer plain language over jargon; define sMAPE/MAPE briefly if you mention them.
4. Write exactly three sections with these headings:

### Finding
2–4 short bullets. Lead with the single most important takeaway.

### Interpretation
A short paragraph (3–5 sentences) explaining what the numbers mean for operations, staffing, or data quality review. Be specific to the metrics given.

### Limitations
2–3 bullets on uncertainty, data caveats, or what cannot be concluded.

5. Do not repeat the raw Evidence list; the UI already shows it.
6. Do not use HTML. Markdown bullets only. No preamble or closing pleasantries.
"""

FEW_SHOT_USER = """Title: Example forecast briefing
Method: Holdout bake-off of Seasonal / Linear / MovingAverage; selected by minimum sMAPE.
Evidence summary:
- selected_model: MovingAverage
- holdout_smape_pct: 33.4
- change_pct: 4.2
- peak: 72000
- floor: 51000
- horizon_days: 30
- data_end: 2025-12-31

Write Finding, Interpretation, Limitations."""

FEW_SHOT_ASSISTANT = """### Finding
- Holdout evaluation prefers the **MovingAverage** model (sMAPE 33.4%).
- The 30-day point path implies about a **4.2%** rise versus the start of the horizon.
- Expected daily volume ranges roughly **51,000–72,000** under the selected model.

### Interpretation
Near-term planning should treat the MovingAverage path as a stable baseline rather than a sharp trend call: sMAPE near one-third means day-level misses remain material. Peak and floor bounds are useful for staffing envelopes, but the elevated error suggests reviewing the forecast daily against actuals. Scenario shocks (if applied) should be read as what-if overlays, not validated demand.

### Limitations
- Holdout error is still high; intervals are residual bootstrap bands, not certified prediction intervals.
- No external drivers (holidays, centre capacity, campaigns) are in the model.
- National aggregation can mask state-level swings.
"""


def _fmt_num(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        if abs(v) >= 10:
            return f"{v:,.1f}"
        return f"{v:.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _humanize_key(key: str) -> str:
    return key.replace("_", " ").strip()


def compact_evidence(evidence: Dict[str, Any], max_items: int = 18) -> Dict[str, Any]:
    """
    Shrink evidence for the LLM: drop huge nested structures, format numbers,
    keep only the most informative keys.
    """
    skip_nested = {"model_comparison", "sample", "top_risk_cells", "top_risk_districts"}
    priority = [
        "selected_model",
        "selection_mode",
        "holdout_smape_pct",
        "holdout_mape_pct",
        "holdout_rmse",
        "change_pct",
        "peak",
        "floor",
        "horizon_days",
        "train_days",
        "data_end",
        "data_as_of",
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
    for k in priority:
        if k in evidence and evidence[k] is not None:
            out[k] = evidence[k]
        if len(out) >= max_items:
            break
    for k, v in evidence.items():
        if k in out or k in skip_nested:
            continue
        if isinstance(v, (dict, list)) and k not in ("top_states_by_enrolment",):
            continue
        out[k] = v
        if len(out) >= max_items:
            break

    # Compact top states
    if "top_states_by_enrolment" in evidence and isinstance(evidence["top_states_by_enrolment"], dict):
        tops = evidence["top_states_by_enrolment"]
        out["top_states"] = ", ".join(f"{s} ({_fmt_num(n)})" for s, n in list(tops.items())[:5])

    # Compact risk cells to short strings
    risks = evidence.get("top_risk_cells") or evidence.get("top_risk_districts") or []
    if isinstance(risks, list) and risks:
        bits = []
        for r in risks[:5]:
            if not isinstance(r, dict):
                continue
            bits.append(
                f"{r.get('state', '?')}/{r.get('district', '?')} "
                f"(risk={r.get('risk_score', '?')}; {r.get('reason', '')})"
            )
        if bits:
            out["top_flagged_cells"] = bits

    # Model bake-off one-liner
    cmp = evidence.get("model_comparison")
    if isinstance(cmp, list) and cmp:
        out["model_bakeoff"] = "; ".join(
            f"{r.get('model')}: sMAPE={r.get('smape_pct')}%, MAPE={r.get('mape_pct')}%"
            for r in cmp
            if isinstance(r, dict)
        )

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


def _auto_findings(evidence: Dict[str, Any]) -> List[str]:
    e = compact_evidence(evidence)
    bullets: List[str] = []

    if e.get("selected_model") is not None:
        smape = e.get("holdout_smape_pct")
        mape = e.get("holdout_mape_pct")
        err = f"sMAPE {_fmt_num(smape)}%" if smape is not None else (
            f"MAPE {_fmt_num(mape)}%" if mape is not None else "holdout metrics unavailable"
        )
        bullets.append(f"Selected forecast model is **{e['selected_model']}** ({err} on holdout).")

    if e.get("change_pct") is not None:
        try:
            ch = float(e["change_pct"])
            direction = "increase" if ch >= 0 else "decrease"
            bullets.append(
                f"Point forecast path shows about a **{_fmt_num(abs(ch))}%** {direction} "
                f"over {e.get('horizon_days', 'the')} days "
                f"(peak {_fmt_num(e.get('peak'))}, floor {_fmt_num(e.get('floor'))})."
            )
        except (TypeError, ValueError):
            pass

    if e.get("anomaly_count") is not None:
        n = e["anomaly_count"]
        if int(n) == 0:
            bullets.append("No state×district cells exceed the multi-feature anomaly threshold under current settings.")
        else:
            bullets.append(
                f"**{_fmt_num(n)}** state×district cells are flagged "
                f"(contamination={e.get('contamination', 'n/a')}, min volume={e.get('min_volume', 'n/a')})."
            )

    if e.get("bio_per_enrol") is not None:
        bullets.append(
            f"Update load dominates new enrolment: bio/enrol ≈ **{_fmt_num(e.get('bio_per_enrol'))}**, "
            f"demo/enrol ≈ **{_fmt_num(e.get('demo_per_enrol'))}** "
            f"(totals enrol {_fmt_num(e.get('total_enrolments'))}, bio {_fmt_num(e.get('biometric_updates'))})."
        )

    if e.get("open_issues") is not None:
        bullets.append(
            f"**{_fmt_num(e.get('open_issues'))}** residual name issues remain "
            f"({_fmt_num(e.get('high_conf_gt_0_9'))} with similarity > 0.9)."
        )

    if e.get("top_flagged_cells"):
        bullets.append(f"Highest-priority flags include: {e['top_flagged_cells'][0]}.")

    if not bullets:
        bullets.append("Computed metrics are listed under Evidence; no strong directional claim is warranted.")
    return bullets[:4]


def _auto_interpretation(evidence: Dict[str, Any]) -> str:
    e = compact_evidence(evidence)
    parts = []
    smape = e.get("holdout_smape_pct")
    if smape is not None:
        try:
            s = float(smape)
            if s < 20:
                parts.append("Holdout error is relatively contained, so the forecast is usable as a planning baseline with daily checks.")
            elif s < 40:
                parts.append("Holdout error is moderate: use the forecast for directional planning and wide staffing bands, not day-exact targets.")
            else:
                parts.append("Holdout error is high: treat the path as exploratory and prioritise monitoring actuals over acting on point forecasts.")
        except (TypeError, ValueError):
            pass
    if e.get("anomaly_count") and int(e.get("anomaly_count") or 0) > 0:
        parts.append(
            "Flagged cells deserve data-quality and operations review (ratios, volatility, or size vs state peers), "
            "not automatic enforcement actions."
        )
    if e.get("bio_per_enrol") is not None:
        try:
            if float(e["bio_per_enrol"]) > 5:
                parts.append("Biometric update volume far exceeds new enrolments, so centre capacity planning should weight update queues more heavily.")
        except (TypeError, ValueError):
            pass
    if not parts:
        parts.append(
            "These figures summarise observed operational counts under the stated method. "
            "Decisions should combine them with local centre knowledge and data-quality checks."
        )
    return " ".join(parts)


def _auto_limitations(evidence: Dict[str, Any]) -> List[str]:
    lim = [
        "Observational operational counts only — not a randomised or quasi-experimental design.",
        "No population or Aadhaar-centre capacity denominator; large volumes may reflect size, not intensity.",
    ]
    if evidence.get("holdout_smape_pct") is not None or evidence.get("selected_model"):
        lim.append("Forecast intervals use residual bootstrap; they are not calibrated conformal intervals.")
    if evidence.get("anomaly_count") is not None:
        lim.append("Anomaly scores are unsupervised; labels are not verified field outcomes.")
    if evidence.get("centroid_source") or True:
        lim.append("Geographic labels rely on rule-based name repair; residual miscodes may remain.")
    return lim[:4]


def format_full_insight(
    title: str,
    findings: List[str],
    interpretation: str,
    limitations: List[str],
    evidence: Dict[str, Any],
    method: str,
    source_note: str,
) -> str:
    find = "\n".join(f"- {b}" for b in findings)
    lim = "\n".join(f"- {b}" for b in limitations)
    return (
        f"### {title}\n\n"
        f"#### Finding\n{find}\n\n"
        f"#### Interpretation\n{interpretation}\n\n"
        f"#### Evidence (engine-computed)\n{evidence_markdown(evidence)}\n\n"
        f"#### Method\n{method}\n\n"
        f"#### Limitations\n{lim}\n\n"
        f"_{source_note}_"
    )


def deterministic_research_insight(
    title: str,
    evidence: Dict[str, Any],
    method: str,
    findings: Optional[List[str]] = None,
    limitations: Optional[List[str]] = None,
) -> str:
    findings = findings or _auto_findings(evidence)
    limitations = limitations or _auto_limitations(evidence)
    interpretation = _auto_interpretation(evidence)
    return format_full_insight(
        title,
        findings,
        interpretation,
        limitations,
        evidence,
        method,
        "Source: analytics engine (deterministic research draft)",
    )


def _extract_section(text: str, name: str) -> str:
    """Pull markdown section body by heading name (### or ####)."""
    # Double braces so f-string does not eat regex quantifiers
    pattern = rf"#{{2,4}}\s*{re.escape(name)}\s*\r?\n([\s\S]*?)(?=\r?\n#{{2,4}}\s|\Z)"
    m = re.search(pattern, text, flags=re.I)
    return m.group(1).strip() if m else ""


def _parse_llm_sections(text: str) -> Tuple[List[str], str, List[str]]:
    text = strip_model_artifacts(text)
    finding_body = _extract_section(text, "Finding")
    interp_body = _extract_section(text, "Interpretation") or _extract_section(text, "Analysis")
    lim_body = _extract_section(text, "Limitations") or _extract_section(text, "Limitation")

    def bullets(body: str) -> List[str]:
        if not body:
            return []
        lines = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^[-*•]\s+", "", line)
            line = re.sub(r"^\d+\.\s+", "", line)
            if line:
                lines.append(line)
        return lines

    findings = bullets(finding_body)
    limitations = bullets(lim_body)
    if not interp_body and finding_body and "\n\n" in finding_body:
        # sometimes models dump paragraph under Finding
        interp_body = finding_body
    interpretation = " ".join(interp_body.split()) if interp_body else ""
    return findings, interpretation, limitations


def research_insight(
    title: str,
    evidence: Dict[str, Any],
    method: str,
    findings: Optional[List[str]] = None,
    limitations: Optional[List[str]] = None,
    use_llm: bool = True,
    client: Optional[OllamaClient] = None,
    focus: Optional[str] = None,
) -> str:
    """
    Hybrid research write-up.
    Evidence is always from the engine; LLM only narrates Finding/Interpretation/Limitations.
    """
    base = deterministic_research_insight(title, evidence, method, findings, limitations)
    if not use_llm:
        return base

    client = client or get_ollama_client()
    status = client.status()
    if not status.available:
        return deterministic_research_insight(title, evidence, method, findings, limitations).replace(
            "deterministic research draft",
            f"engine draft · LLM offline ({status.error})",
        )

    compact = compact_evidence(evidence)
    focus_line = focus or "Highlight operational implications and data-quality follow-ups."
    user = (
        f"Title: {title}\n"
        f"Focus: {focus_line}\n"
        f"Method (for Limitations/Method awareness): {method}\n\n"
        f"Evidence summary (authoritative — do not contradict):\n"
        f"{json.dumps(compact, indent=2, default=str)}\n\n"
        "Write ### Finding, ### Interpretation, and ### Limitations now."
    )

    try:
        text = client.chat(
            [
                {"role": "system", "content": RESEARCH_SYSTEM},
                {"role": "user", "content": FEW_SHOT_USER},
                {"role": "assistant", "content": FEW_SHOT_ASSISTANT},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        llm_findings, llm_interp, llm_lim = _parse_llm_sections(text)

        final_findings = llm_findings or findings or _auto_findings(evidence)
        final_interp = llm_interp or _auto_interpretation(evidence)
        final_lim = llm_lim or limitations or _auto_limitations(evidence)

        # Guard: if LLM output is tiny/garbage, fall back
        if len(final_interp) < 40 and len(final_findings) < 2:
            return base + f"\n\n_LLM output incomplete; showing engine draft. Raw: {text[:200]}_"

        return format_full_insight(
            title,
            final_findings[:5],
            final_interp,
            final_lim[:4],
            evidence,
            method,
            f"Source: hybrid · narrative by `{status.model}` · numbers by analytics engine",
        )
    except Exception as e:
        return base + f"\n\n_LLM call failed ({e}); engine draft above._"
