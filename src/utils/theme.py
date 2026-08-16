"""Dark research chrome for Streamlit — dense, high-contrast, no decorative UI."""
from __future__ import annotations

import base64
import html
from typing import Iterable, Optional

import streamlit as st

from src.config import ROOT_DIR

LOGO_PATH = ROOT_DIR / "web" / "frontend" / "public" / "logo.jpeg"

_ACCENT = {
    "blue": "#38bdf8",
    "green": "#34d399",
    "amber": "#fbbf24",
    "violet": "#a78bfa",
    "rose": "#fb7185",
    "slate": "#94a3b8",
}


def _esc(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def fmt_num(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    try:
        if isinstance(value, float) and not value.is_integer():
            return f"{value:,.1f}"
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _logo_data_uri() -> str:
    if not LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def setup_page():
    st.set_page_config(
        page_title="Aadhaar Intel",
        page_icon="🇮🇳",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_APP_CSS, unsafe_allow_html=True)


def page_header(title: str, badge: Optional[str] = None, subtitle: Optional[str] = None):
    badge_html = f'<span class="st-badge">{_esc(badge)}</span>' if badge else ""
    sub_html = f'<p class="st-page-sub">{_esc(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f"""
<div class="st-page-header">
  <div class="st-page-header__title">
    <h2>{_esc(title)}</h2>
    {badge_html}
  </div>
  {sub_html}
</div>
""",
        unsafe_allow_html=True,
    )


def status_pills(items: Iterable[tuple[str, str]]):
    chips = []
    for kind, label in items:
        chips.append(f'<span class="st-status st-status--{kind}">{_esc(label)}</span>')
    st.markdown(f'<div class="st-status-row">{"".join(chips)}</div>', unsafe_allow_html=True)


def render_topbar(*, states_label: str, range_label: str, llm_label: str, llm_ok: bool):
    llm_cls = "ok" if llm_ok else "warn"
    st.markdown(
        f"""
<div class="st-topbar">
  <div class="st-chips">
    <span class="st-chip">States: <strong>{_esc(states_label)}</strong></span>
    <span class="st-chip">Range: <strong>{_esc(range_label)}</strong></span>
    <span class="st-chip {llm_cls}">{_esc(llm_label)}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def kpi_card_html(
    *,
    label: str,
    value,
    delta: Optional[str] = None,
    accent: str = "blue",
    icon: Optional[str] = None,
    compact: bool = False,
    format_value: bool = True,
) -> str:
    del icon  # research layout: values first, no decorative icons
    color = _ACCENT.get(accent, _ACCENT["blue"])
    display = fmt_num(value) if format_value else (str(value) if value is not None else "—")
    delta_html = f'<div class="kpi-card__delta">{_esc(delta)}</div>' if delta else ""
    compact_cls = " kpi-card--compact" if compact else ""
    return f"""
<div class="kpi-card{compact_cls}" style="--kpi-accent:{color}">
  <span class="kpi-card__label">{_esc(label)}</span>
  <div class="kpi-card__value">{_esc(display)}</div>
  {delta_html}
</div>
"""


def kpi_row(items: list[dict], *, compact: bool = False):
    n = min(max(len(items), 1), 6)
    cards = "".join(
        kpi_card_html(
            label=item["label"],
            value=item.get("value"),
            delta=item.get("delta"),
            accent=item.get("accent", "blue"),
            compact=compact or item.get("compact", False),
            format_value=item.get("format", True),
        )
        for item in items
    )
    st.markdown(f'<div class="st-kpi-row st-kpi-row--{n}">{cards}</div>', unsafe_allow_html=True)


def section_title(title: str, extra: Optional[str] = None):
    extra_html = f'<span class="st-section-extra">{_esc(extra)}</span>' if extra else ""
    st.markdown(
        f'<div class="st-section-title"><h3>{_esc(title)}</h3>{extra_html}</div>',
        unsafe_allow_html=True,
    )


def brand_html() -> str:
    uri = _logo_data_uri()
    mark = (
        f'<img class="brand-mark" src="{uri}" alt="Aadhaar Intel logo" width="36" height="36" />'
        if uri
        else '<div class="brand-mark brand-mark--fallback">AI</div>'
    )
    return f"""
<div class="brand">
  {mark}
  <div class="brand-text">
    <h1>Aadhaar Intel</h1>
    <p>Research console</p>
  </div>
</div>
"""


def status_card_html(
    *,
    date_max: str,
    source: str,
    marts_only,
    enrol_n: int,
    bio_n: int,
    demo_n: int,
    llm_ok: bool,
    llm_label: str,
) -> str:
    llm_cls = "ok" if llm_ok else "warn"
    return f"""
<div class="status-card">
  <div>Data as of: <strong>{_esc(date_max)}</strong></div>
  <div>Source: <strong>{_esc(source)}</strong> · MARTS_ONLY={_esc(marts_only)}</div>
  <div>E {fmt_num(enrol_n)} · B {fmt_num(bio_n)} · D {fmt_num(demo_n)}</div>
  <div class="{llm_cls}">LLM: {_esc(llm_label)}</div>
</div>
"""


def ai_panel_header(has_content: bool = False):
    action = "Regenerate" if has_content else "Generate"
    st.markdown(
        f"""
<div class="ai-panel-head">
  <h3>AI analysis</h3>
  <span class="ai-panel-hint">{_esc(action)} from engine numbers only</span>
</div>
""",
        unsafe_allow_html=True,
    )


_APP_CSS = """
<style>
:root {
  --bg: #0b0f19;
  --bg-elevated: #151b2b;
  --sidebar: #080c14;
  --text: #e2e8f0;
  --text-muted: #94a3b8;
  --border: #1e293b;
  --accent: #38bdf8;
  --success: #34d399;
  --warning: #fbbf24;
  --danger: #f87171;
  --font: "Segoe UI", system-ui, sans-serif;
  --mono: ui-monospace, "Cascadia Mono", Consolas, monospace;
}

html, body, [data-testid="stAppViewContainer"], .stApp {
  background-color: var(--bg) !important;
  color: var(--text) !important;
  font-family: var(--font) !important;
}

[data-testid="stHeader"] {
  background: var(--bg) !important;
  border-bottom: 1px solid var(--border);
}
[data-testid="stDecoration"] { display: none; }
[data-testid="stToolbar"] { color: var(--text-muted); }

.block-container {
  padding-top: 0.85rem !important;
  padding-bottom: 2.2rem !important;
  max-width: 1600px !important;
}

h1, h2, h3, h4, h5, h6 {
  color: #f8fafc !important;
  font-family: var(--font) !important;
  font-weight: 600 !important;
}
p, label, span, li, .stMarkdown { color: #cbd5e1; }
.stCaption, [data-testid="stCaptionContainer"] { color: var(--text-muted) !important; }

[data-testid="stSidebar"] {
  background: var(--sidebar) !important;
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] > div:first-child { background: transparent !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span { color: #cbd5e1 !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #f8fafc !important; }

.brand {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.1rem 0 0.5rem;
}
.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
  border: 1px solid var(--border);
}
.brand-mark--fallback {
  display: grid;
  place-items: center;
  background: #0c4a6e;
  color: #e0f2fe;
  font-weight: 700;
  font-size: 0.75rem;
}
.brand-text h1 {
  margin: 0 !important;
  font-size: 1rem !important;
  font-weight: 650 !important;
  color: #f8fafc !important;
}
.brand-text p {
  margin: 0.08rem 0 0 !important;
  font-size: 0.72rem !important;
  color: var(--text-muted) !important;
}

.sidebar-kicker {
  margin: 0.55rem 0 0.25rem !important;
  font-size: 0.7rem !important;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted) !important;
  font-weight: 650 !important;
}

[data-testid="stSidebar"] [data-testid="stRadio"] > div {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
  background: transparent !important;
  border: 1px solid transparent !important;
  border-radius: 4px !important;
  padding: 0.4rem 0.55rem !important;
  font-weight: 500 !important;
  color: #cbd5e1 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
  background: #151b2b !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
  background: #0c4a6e !important;
  color: #e0f2fe !important;
  border-color: #0369a1 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) span {
  color: #e0f2fe !important;
}

.status-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.65rem 0.7rem;
  font-size: 0.75rem;
  color: #94a3b8;
  line-height: 1.5;
  margin: 0.4rem 0 0.55rem;
}
.status-card strong { color: #e2e8f0; }
.status-card .ok { color: var(--success); font-weight: 600; }
.status-card .warn { color: var(--warning); font-weight: 600; }

.st-topbar { margin: 0 0 0.65rem; }
.st-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
.st-chip {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.2rem 0.55rem;
  font-size: 0.78rem;
  color: #94a3b8;
}
.st-chip.ok { color: var(--success); }
.st-chip.warn { color: var(--warning); }
.st-chip strong { color: #e2e8f0; }

.st-page-header { margin: 0 0 0.55rem; }
.st-page-header__title { display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; }
.st-page-header h2 {
  margin: 0 !important;
  font-size: 1.35rem !important;
  font-weight: 650 !important;
  color: #f8fafc !important;
}
.st-page-sub {
  margin: 0.2rem 0 0 !important;
  color: var(--text-muted) !important;
  font-size: 0.85rem !important;
}
.st-badge {
  display: inline-flex;
  padding: 0.12rem 0.45rem;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 650;
  background: #0c4a6e;
  color: #e0f2fe;
  border: 1px solid #0369a1;
}

.st-status-row { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0 0 0.65rem; }
.st-status {
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  font-size: 0.75rem;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: #94a3b8;
}
.st-status--ok { color: var(--success); border-color: #065f46; }
.st-status--warn { color: var(--warning); border-color: #854d0e; }
.st-status--info { color: var(--accent); border-color: #0369a1; }

.st-kpi-row {
  display: grid;
  gap: 0.55rem;
  margin: 0 0 0.85rem;
}
.st-kpi-row--3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.st-kpi-row--4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.st-kpi-row--5 { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.st-kpi-row--6 { grid-template-columns: repeat(6, minmax(0, 1fr)); }

.kpi-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-left: 3px solid var(--kpi-accent, var(--accent));
  border-radius: 4px;
  padding: 0.55rem 0.7rem 0.6rem;
}
.kpi-card__label {
  display: block;
  font-size: 0.7rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.kpi-card__value {
  font-size: 1.35rem;
  font-weight: 700;
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  color: #f8fafc;
  line-height: 1.25;
  word-break: break-word;
}
.kpi-card__delta { font-size: 0.75rem; color: var(--text-muted); }
.kpi-card--compact { padding: 0.4rem 0.55rem; }
.kpi-card--compact .kpi-card__value { font-size: 1.05rem; }

.st-section-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.6rem;
  margin: 0.65rem 0 0.4rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.25rem;
}
.st-section-title h3 {
  margin: 0 !important;
  font-size: 0.98rem !important;
  color: #f8fafc !important;
}
.st-section-extra { font-size: 0.78rem; color: var(--text-muted); }

.ai-panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin: 0 0 0.35rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid var(--border);
}
.ai-panel-head h3 {
  margin: 0 !important;
  font-size: 0.98rem !important;
}
.ai-panel-hint { font-size: 0.75rem; color: var(--text-muted); }

.stButton > button {
  border-radius: 4px !important;
  font-weight: 600 !important;
  font-family: var(--font) !important;
  padding: 0.35rem 0.75rem !important;
}
.stButton > button[kind="primary"],
[data-testid="stBaseButton-primary"] {
  background: #0369a1 !important;
  color: #f0f9ff !important;
  border: 1px solid #0284c7 !important;
}
.stButton > button[kind="secondary"] {
  background: var(--bg-elevated) !important;
  color: #e2e8f0 !important;
  border: 1px solid var(--border) !important;
}

.stTabs [data-baseweb="tab-list"] { gap: 2px; }
.stTabs [data-baseweb="tab"] {
  background: #151b2b !important;
  color: #94a3b8 !important;
  border-radius: 4px 4px 0 0 !important;
  border: 1px solid var(--border) !important;
  border-bottom: none !important;
  font-weight: 500 !important;
}
.stTabs [aria-selected="true"] {
  background: var(--bg) !important;
  color: var(--accent) !important;
  border-top: 2px solid var(--accent) !important;
}

[data-testid="stMetric"] {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.55rem 0.7rem;
}
[data-testid="stMetricValue"] {
  color: var(--accent) !important;
  font-family: var(--mono) !important;
}
[data-testid="stMetricLabel"] { color: var(--text-muted) !important; }

[data-testid="stDataFrame"] {
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-elevated);
}

[data-testid="stPlotlyChart"],
[data-testid="stDeckGlJsonChart"] {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.25rem;
}

[data-testid="stExpander"] {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px !important;
}

.stDownloadButton > button {
  background: var(--bg-elevated) !important;
  color: #e2e8f0 !important;
  border: 1px solid var(--border) !important;
  border-radius: 4px !important;
}

[data-testid="stSidebar"] .stButton > button[kind="primary"] { width: 100%; }

/* Inputs on dark chrome */
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea,
[data-baseweb="select"] > div,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input {
  background-color: #0f172a !important;
  color: #e2e8f0 !important;
  border-color: #334155 !important;
}

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent); }

@media (max-width: 1200px) {
  .st-kpi-row--6, .st-kpi-row--5 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .st-kpi-row--4, .st-kpi-row--3 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .st-kpi-row--6, .st-kpi-row--5, .st-kpi-row--4, .st-kpi-row--3 { grid-template-columns: 1fr; }
}
</style>
"""
