from pathlib import Path
import re

p = Path(r"D:\Project\Aadhaar-Intel-Engine-UIDAI\docs\build_symposium_paper.py")
t = p.read_text(encoding="utf-8")

replacements = [
    ("add_image(arch, 4.0)", "add_image(arch, 3.5)"),
    ("add_image(donut, 3.0)", "add_image(donut, 2.5)"),
    ("add_image(anom, 4.0)", "add_image(anom, 3.4)"),
    ("add_image(fc, 4.2)", "add_image(fc, 3.5)"),
    ("add_image(dash, 4.2)", "add_image(dash, 3.5)"),
    ("first_line=0.25", "first_line=0.15"),
    ("space_before=8, space_after=4, bold=True, size=10", "space_before=6, space_after=3, bold=True, size=10"),
    ("space_before=4, space_after=6, italic=True, size=8", "space_before=1, space_after=4, italic=True, size=8"),
]
for a, b in replacements:
    t = t.replace(a, b)

# drop placeholder figs 6-7 block
t = re.sub(
    r'placeholder_box\(\s*"Figs\. 6.*?\n\caption\("Figs\. 6–7\.[^"]*"\)\s*\n',
    "",
    t,
    flags=re.S,
)

# default body size 9 for normal paras that use size=10 in add_para calls for body - careful
# only change add_para size=10 for first_line paragraphs by reducing abstract via shorter text

# Shorten abstract block
abs_marker = '"Aadhaar is India’s foundational digital identity system;'
i = t.find(abs_marker)
if i < 0:
    abs_marker = '"Aadhaar is India'
    i = t.find(abs_marker)
j = t.find("KEYWORDS:", i)
# find end of add_para call - size=10 after abstract
k = t.find("size=10,\n    space_after=8,", i)
if i > 0 and k > i:
    short_abs = '''"Aadhaar is India’s foundational digital identity system. This paper presents the Aadhaar Intel Engine, "
    "a research analytics platform that ingests multi-million-row aggregate UIDAI-style CSV extracts, applies "
    "deterministic geographic normalisation and boundary repair, materialises daily Parquet marts, and serves "
    "interactive Streamlit intelligence. Analytics combine multi-feature Isolation Forest on (state, district) "
    "units with a holdout forecast bake-off (Seasonal, Linear Ridge, Moving-Average) selecting by sMAPE. Hybrid "
    "LLM briefs ground narrative on engine Evidence via Ollama (deterministic fallback offline). On ~4.94M rows "
    "(Mar–Dec 2025), marts reload in under a second; Moving Average often wins holdout (sMAPE ≈ 33% in "
    "representative runs). We discuss validity threats and frame results as correlational operational research, "
    "not causal fraud detection.",
'''
    # find opening quote of abstract after add_para(
    # replace from abs_marker through the closing before size=
    # locate start of string for abstract - go back to first quote of this arg
    # simpler: replace from i to the comma before size=
    m = t.rfind("add_para(", 0, i)
    # find the abstract string end: ",\n    size=10" pattern after i
    end = t.find(",\n    size=10,\n    space_after=8", i)
    if end > i:
        t = t[:i] + short_abs.rstrip() + t[end:]

# shorten intro 2nd para
t = t.replace(
    "This work addresses three recurring gaps in practice-oriented analytics prototypes: (i) messy geographic labels "
    "(districts written as states, Andhra Pradesh / Telangana boundary errors, orthographic aliases); "
    "(ii) non-reproducible “AI” forecasts that are stochastic decorations rather than evaluated models; and "
    "(iii) LLM narratives that invent numbers. We contribute a research-oriented platform, the Aadhaar Intel Engine, "
    "that couples a production-style data path (validate → repair → deduplicate → daily marts) with defensible "
    "analytics and hybrid, evidence-grounded insights.",
    "We address three gaps: (i) messy geographic labels; (ii) unevaluated decorative forecasts; "
    "(iii) ungrounded LLM narratives. The Aadhaar Intel Engine couples validate→repair→dedupe→daily marts "
    "with defensible analytics and hybrid evidence-grounded insights.",
)

t = t.replace(
    "The remainder of the paper is organised as follows. Section 2 reviews related work. Section 3 describes data, "
    "system architecture, and methods. Section 4 reports experimental results. Section 5 discusses limitations. "
    "Section 6 concludes.",
    "Section 2 reviews related work; Section 3 methods; Section 4 results; Section 5 limitations; Section 6 conclusion.",
)

# shorten related work
old_rel = (
    "Operational dashboards for public-sector data commonly emphasise descriptive KPIs and maps. Time-series "
    "forecasting for demand planning ranges from seasonal naïve baselines and exponential smoothing to "
    "machine-learning regressors; model selection by rolling or holdout error is standard practice in forecasting "
    "research [2], [3], [12]. Anomaly detection on multivariate operational features frequently uses Isolation Forest "
    "and related unsupervised methods [1], [6]. Data quality literature stresses master data management for place "
    "names and administrative boundaries [5], [7], [11]. Recent LLM tooling can summarise metrics, but without "
    "grounding it risks hallucination. Our system integrates these strands in a single reproducible pipeline aimed "
    "at Aadhaar-like aggregate extracts [4], [8], [9], [10]."
)
new_rel = (
    "Public-sector dashboards often stop at descriptive KPIs. Forecasting practice emphasises holdout or "
    "rolling evaluation of seasonal baselines and regressors [2], [3], [12]. Isolation Forest and related methods "
    "are common for multivariate operational anomalies [1], [6]. Place-name master data is central to data quality "
    "[5], [7], [11]. LLM summaries help only if grounded. We integrate these strands for Aadhaar-like aggregates "
    "[4], [8], [9], [10]."
)
t = t.replace(old_rel, new_rel)

p.write_text(t, encoding="utf-8")
print("shrunk builder")
