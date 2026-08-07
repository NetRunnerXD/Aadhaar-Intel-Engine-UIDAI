# Aadhaar Intel Engine — Detailed Flowcharts

Research-grade operational analytics for **Aadhaar enrolment and update aggregates** (no Aadhaar numbers or biometrics). This document maps data flow, geo repair, analytics, forecasting, UI modules, governance, and LLM briefs as implemented in the codebase.

> **Disclaimer:** Isolation Forest scores and the risk radar are unsupervised outlier rankings (“look here”), not fraud labels. Forecasts are decision-band guides, not guarantees.

---

## 1. System at a glance

```mermaid
flowchart TB
    subgraph INPUT["📥 Inputs"]
        CSV["data/*.csv shards<br/>enrol · bio · demo"]
        REF["assets/reference/*<br/>aliases · PIN map · holidays · gold"]
        GEOJSON["assets/india_states.geojson"]
        GOVSTORE["output/governance_patches.json<br/>+ governance_audit.csv"]
    end

    subgraph ETL["⚙️ Ingest & marts"]
        DL["DataLoader<br/>src/data_manager.py"]
        BC["ETL build_cache<br/>src/etl/build_cache.py"]
        MARTS["data/processed/*.parquet<br/>fact_*_daily · dim_geo · agg_district"]
    end

    subgraph GEO["🗺️ Geography"]
        NORM["canonicalize state<br/>src/geo/normalize.py"]
        REPAIR["full_geo_repair<br/>src/geo/repair.py"]
        PIN["PIN prefix → state<br/>src/geo/pin_map.py"]
        CENT["resolve_centroid<br/>src/geo/centroids.py"]
        EVAL["evaluate_geo_cleaning<br/>src/geo/eval_cleaning.py"]
    end

    subgraph APP["🖥️ Streamlit app.py"]
        GOVAPPLY["apply_governance_changes"]
        FILT["apply_filters<br/>src/services/filters.py"]
        ENG["AnalyticsEngine<br/>src/ai_core.py"]
        NAV["Sidebar navigation<br/>5 modules"]
    end

    subgraph UI["📊 Modules"]
        DASH["Dashboard"]
        ANA["Analytics + Risk radar"]
        FC["Forecast"]
        MAP["Geospatial Intel"]
        GOVUI["Data Governance"]
    end

    subgraph AI["🤖 Research insights"]
        EV["evidence dict<br/>from engine"]
        DET["deterministic draft"]
        OLL["Ollama LLM<br/>optional prose only"]
        BRIEF["Finding / Interpretation<br/>Evidence / Method / Limitations"]
    end

    CSV --> DL
    REF --> REPAIR
    REF --> PIN
    REF --> EVAL
    GOVSTORE --> GOVAPPLY
    DL -->|cache valid| MARTS
    DL -->|cache miss / rebuild| BC
    BC --> MARTS
    MARTS --> DL
    DL --> NORM
    NORM --> REPAIR
    REPAIR --> PIN
    REPAIR --> EVAL
    DL --> GOVAPPLY
    GOVAPPLY --> FILT
    FILT --> ENG
    GEOJSON --> MAP
    CENT --> MAP
    ENG --> NAV
    NAV --> DASH & ANA & FC & MAP & GOVUI
    ENG --> EV --> DET
    DET --> OLL
    DET --> BRIEF
    OLL --> BRIEF
    BRIEF --> DASH & FC & GOVUI
```

---

## 2. Application startup & routing

```mermaid
flowchart TD
    START([streamlit run app.py / main.py]) --> THEME[theme.setup_page]
    THEME --> CACHE["@st.cache_resource load_raw_data()"]
    CACHE --> LOADER["DataLoader.get_data()<br/>prefer_cache=True"]

    LOADER --> EMPTY{enrol/bio/demo<br/>all empty?}
    EMPTY -->|yes| ERR[Show error + load logs<br/>+ load_report JSON · stop]
    EMPTY -->|no| GOVINIT[data_admin.init_session_state<br/>load patches + audit]

    GOVINIT --> DIRTY{df_*_clean missing<br/>or data_dirty?}
    DIRTY -->|yes| APPLY["apply_governance_changes<br/>on raw enrol/demo/bio"]
    DIRTY -->|no| USE[Use session cleaned frames]
    APPLY --> USE

    USE --> SIDE[navigation.render_sidebar<br/>state · date · module radio]
    SIDE --> FILT["apply_filters → f_enrol, f_demo, f_bio"]
    FILT --> ENG[AnalyticsEngine f_*]
    ENG --> ANOM[engine.get_anomalies default]
    ANOM --> STATUS[Sidebar research status<br/>data as-of · source · LLM · quality]

    STATUS --> ROUTE{view}

    ROUTE -->|Dashboard| D[dashboard.render_dashboard]
    ROUTE -->|Analytics| A[analytics.render_tab]
    ROUTE -->|Forecast| P[predict.render_tab]
    ROUTE -->|Geospatial Intel| C[command.render_tab + GeoJSON]
    ROUTE -->|Data Governance| G["data_admin.render_tab<br/>dim_geo if no pincode on daily"]
```

**Key files**

| Step | Module |
|------|--------|
| Entry | `app.py`, `main.py` |
| Load | `src/data_manager.py` → `DataLoader` |
| Filters | `src/services/filters.py` |
| Engine | `src/ai_core.py` → `AnalyticsEngine` |
| Nav | `src/components/navigation.py` |

---

## 3. Data load path (CSV ↔ Parquet marts)

```mermaid
flowchart TD
    GET["DataLoader.get_data()"] --> PREF{prefer_cache<br/>and cache valid?}

    PREF -->|yes| LM["load_marts()<br/>fact_enrol/bio/demo_daily<br/>dim_geo · agg_district · manifest"]
    LM --> SRC1[source = cache]
    SRC1 --> OUT[Return daily frames + logs + report]

    PREF -->|no| MARTS_ONLY{MARTS_ONLY<br/>env?}
    MARTS_ONLY -->|yes| FAIL[Empty frames + warning<br/>cannot rebuild from CSV]
    MARTS_ONLY -->|no| CSV[Scan DATA_DIR CSVs]

    CSV --> CLASS["_classify columns<br/>bio_age* → bio<br/>demo_age* → demo<br/>age_0_5 / age_18_* → enrol"]
    CLASS --> READ[Read & standardize<br/>dates · geo · numerics]
    READ --> Q[Quarantine bad rows<br/>invalid date / pincode range]
    Q --> DEDUP[Collapse NATURAL_KEY duplicates<br/>sum metrics]
    DEDUP --> CANON[apply_state_canonicalization]
    CANON --> GEOREP[full_geo_repair]
    GEOREP --> OPT[_optimize dtypes<br/>category state/district]
    OPT --> AUTO{AUTO_BUILD_CACHE?}
    AUTO -->|yes| BUILD["build_marts_from_frames<br/>write_marts + fingerprint"]
    BUILD --> OUT2[Return frames source=csv→cache]
    AUTO -->|no| OUT2B[Return frames source=csv]

    OUT --> EVALO["Optional geo_eval on gold set<br/>+ rule pack in load_report"]
    OUT2 --> EVALO
```

### Processed marts (`data/processed/`)

| Artifact | Grain / role |
|----------|----------------|
| `fact_enrol_daily.parquet` | date × state × district enrolment volumes + age bands |
| `fact_bio_daily.parquet` | date × state × district biometric updates |
| `fact_demo_daily.parquet` | date × state × district demographic updates |
| `dim_geo.parquet` | state × district × sample pincodes (governance / PIN scans) |
| `agg_district.parquet` | district-level enrolment rollups |
| `manifest.json` | source fingerprint, row counts, build metadata |

### Offline rebuild

```text
python -m src.etl.build_cache
# or scripts/refresh_marts.ps1
```

```mermaid
flowchart LR
    A[list_csv_files] --> B[source_fingerprint]
    B --> C[DataLoader CSV path]
    C --> D[_to_daily aggregates]
    D --> E[_build_dim_geo]
    D --> F[_build_agg_district]
    E --> G[write parquet + manifest]
    F --> G
```

---

## 4. Geography repair pipeline

Order is fixed in `full_geo_repair()`:

```mermaid
flowchart TD
    IN[Raw/normalized frame<br/>state · district · pincode] --> S1

    subgraph S1["① District typed as state"]
        DAS["repair_misfiled_states<br/>district_as_state.json<br/>+ corpus district→state"]
    end

    S1 --> S2
    subgraph S2["② District name aliases"]
        AL["apply_district_aliases<br/>district_aliases.json"]
    end

    S2 --> S3
    subgraph S3["③ AP → Telangana boundary"]
        TS["apply_telangana_boundary_fix<br/>telangana_districts.json"]
    end

    S3 --> S4
    subgraph S4["④ PIN prefix fallback"]
        PF["apply_pin_prefix_state_fallback<br/>pin_prefix_states.json<br/>only if state still non-official"]
    end

    S4 --> OUT[Repaired frame + stats]
    OUT --> STATS["district_as_state · district_aliases<br/>ap_to_telangana · pin_prefix_fallback"]

    REF1[(state_aliases.json<br/>official_states.json)] -.-> CANON[canonicalize_state]
    CANON -.-> IN
    GOLD[(eval_geo_gold.json<br/>rules_manifest.json)] -.-> EV[evaluate_geo_cleaning]
    EV -.-> REPORT[load_report.geo_eval]
```

### Centroid resolution (maps only)

```mermaid
flowchart LR
    R[state, district] --> K[geo_key]
    K --> D{district centroid<br/>in district_centroids.json?}
    D -->|yes| CD[source=district]
    D -->|no| ST{STATE_CENTROIDS<br/>or alias?}
    ST -->|yes| CS[source=state + mild jitter]
    ST -->|no| DF[default India center + jitter<br/>source=default]
```

---

## 5. Session governance (human overrides)

```mermaid
flowchart TD
    INIT[init_session_state] --> LOAD["load_store governance_patches.json<br/>load_audit_log CSV"]
    LOAD --> SS[session: patches · audit · data_dirty]

    UI[Data Governance UI] --> SCAN{Scan type}
    SCAN -->|State names| FS[find_state_discrepancies]
    SCAN -->|District names| FD[find_district_discrepancies<br/>PIN heuristics via dim_geo]
    FS --> FIX[User batch fixes]
    FD --> FIX
    FIX --> LOG[batch_log_changes]
    LOG --> SAVE[persist_governance<br/>patches + audit]
    SAVE --> DIRTY[data_dirty = True]
    DIRTY --> RELOAD[Next app cycle re-applies patches]

    APPLY["apply_governance_changes(df)"] --> MAP[Map old→new from patches]
    MAP --> OUT[Cleaned operational frames]

    IO[Import / Export pack] --> PACK[JSON pack of patches + audit]
```

**Durability:** patches live under `output/`; they re-apply on every load so marts + human fixes stay aligned without re-editing CSVs.

---

## 6. AnalyticsEngine — core services

```mermaid
flowchart TB
    subgraph IN["Filtered frames"]
        E[df_enrol]
        B[df_bio]
        D[df_demo]
    end

    ENG[AnalyticsEngine]

    E --> ENG
    B --> ENG
    D --> ENG

    ENG --> MS[get_market_share]
    ENG --> COR[get_correlation<br/>enrol vs bio vs demo by cell]
    ENG --> FM[_district_feature_matrix]
    ENG --> AN[get_anomalies IsolationForest]
    ENG --> FC[forecast_trends / compare / select]
    ENG --> INS[generate_*_insight<br/>dashboard · forecast · governance]

    FM --> AN
    AN --> RR[State risk radar aggregation<br/>in analytics module]
```

### 6.1 District feature matrix → Isolation Forest

```mermaid
flowchart TD
    EN[Enrol daily by state×district] --> FEAT

    subgraph FEAT["Features per cell"]
        V[volume · log_volume]
        CV[day-to-day CV / volatility]
        BR[bio_ratio]
        DR[demo_ratio]
        WG[wow_growth]
        AD[active_days]
        VS[volume_vs_state_median]
    end

    FEAT --> FILT[min_volume filter]
    FILT --> SCALE[StandardScaler]
    SCALE --> ISO["IsolationForest<br/>contamination · n_estimators=200<br/>random_state fixed"]
    ISO --> LAB[labels −1 outlier / 1 inlier]
    ISO --> SCORE[decision_function → risk_raw]
    SCORE --> NORM[normalize → risk_score 10–100<br/>only for outliers]
    LAB --> REASON[Top |z| feature → reason text]
    NORM --> NOTES[investigation_notes]
    REASON --> OUT[Flagged rows sorted by risk_score]
    NOTES --> OUT
```

**Not fraud detection** — multi-feature peer outliers only.

### 6.2 State risk radar (Analytics UI)

```mermaid
flowchart LR
    AN[Flagged district cells] --> AGG["groupby state:<br/>max_risk · mean_risk<br/>flags · flagged_volume"]
    AGG --> SORT[Sort by flagged_volume DESC]
    SORT --> TOP[Top 10 states]
    TOP --> POLAR["Scatterpolar plot<br/>r = max/mean risk<br/>θ labels = State + vol compact"]
    POLAR --> UI[Full-width white-themed chart]
```

Implementation: `src/modules/analytics.py` → `_state_risk_summary` → `render_state_risk_radar`.

---

## 7. Forecasting flow

```mermaid
flowchart TD
    DAILY["_daily_series national or by state"] --> CAL["complete_daily_calendar<br/>fill missing days with 0"]
    CAL --> MODE{model_type}

    MODE -->|Auto| CMP["ForecastBackend.compare_models<br/>rolling_origin_cv"]
    MODE -->|named| PICK[Named model from registry]

    subgraph CANDIDATES["Registry candidates (sklearn-only)"]
        SN[SeasonalNaive lag-7]
        MA[MovingAverage + DOW shape]
        DR[Drift damped]
        SEA[Seasonal]
        LIN[Linear Ridge t]
        SH[SeasonalHoliday]
        RL[RidgeLags recursive]
        HGB[HistGB recursive]
        ENS[Ensemble median]
    end

    CMP --> CANDIDATES
    CANDIDATES --> MET["Metrics: MASE · sMAPE · MAPE · RMSE · nRMSE · bias"]
    MET --> SEL["select_model: best primary metric (default MASE)<br/>must beat SeasonalNaive AND MovingAverage"]
    SEL --> PICK

    PICK --> PRED[Predict horizon H days]
    PRED --> BT[single_holdout backtest meta]
    PRED --> CI["split conformal |residual| quantile"]
    BT --> META[_last_forecast_meta]
    CI --> FRAME[forecast DataFrame]
    META --> UI[Forecast module + dashboard KPI]
    FRAME --> UI
```

### Decision bands (config)

| Band | MASE (primary) | sMAPE (fallback) | Meaning |
|------|----------------|------------------|---------|
| tight | &lt; 0.85 | &lt; 20% | finer short-horizon planning |
| directional | &lt; 1.15 | &lt; 40% | direction only |
| exploratory | ≥ 1.15 | ≥ 40% | research / monitor actuals |

---

## 8. Module-level UI flows

### 8.1 Dashboard

```mermaid
flowchart TD
    IN[engine + filtered frames] --> KPI[KPI row<br/>enrol · bio · demo · anomalies · forecast Δ · sMAPE]
    KPI --> AGE[Age mix chart]
    KPI --> AN[Anomaly section bar/table]
    KPI --> BRIEF[AI research brief<br/>evidence-locked]
    KPI --> LOGS[Recent load logs]
```

### 8.2 Analytics

```mermaid
flowchart TD
    IN[engine.df_enrol] --> KPI[Volume / states / districts KPIs]
    KPI --> GROW[Growth trajectory + top state drivers]
    KPI --> OPS[Workload donut + low-volume watchlist]
    KPI --> RISK[Risk radar controls<br/>contamination · min_volume]
    RISK --> IF[get_anomalies force=True]
    IF --> STATE[State radar top 10 by volume]
    IF --> DIST[District scatter + investigation notes]
    IF --> EXP[CSV export pack]
```

### 8.3 Forecast

```mermaid
flowchart TD
    IN[engine + f_enrol] --> CTRL[Horizon · model · Auto]
    CTRL --> RUN[forecast_trends]
    RUN --> CHART[History + path + band]
    RUN --> BAKE[Model bake-off table]
    RUN --> RES[Resource planning from forecast]
    RUN --> BRIEF[Forecast research brief]
```

### 8.4 Geospatial Intel

```mermaid
flowchart TD
    IN[f_enrol] --> AGG[_prepare_map_frame<br/>district grain + centroids]
    AGG --> SCALE[_apply_scale linear/log<br/>color · radius · elevation]
    SCALE --> MODE{viz mode}
    MODE -->|Intensity 2D| SC[ScatterplotLayer]
    MODE -->|Heatmap| HM[HeatmapLayer]
    MODE -->|3D| COL[ColumnLayer]
    SC & HM & COL --> DECK["pydeck Deck<br/>MAP_STYLE = Carto Positron white"]
    GEOJSON[GeoJsonLayer dark borders] --> DECK
    DECK --> EXP[Export CSV / HTML]
```

### 8.5 Data Governance

```mermaid
flowchart TD
    TAB[render_tab] --> T1[Repair scans]
    TAB --> T2[Audit log]
    TAB --> T3[Import / Export]
    T1 --> BRIEF[Governance insight optional LLM]
```

---

## 9. LLM research brief path

```mermaid
flowchart TD
    CALL["generate_*_insight / research_insight"] --> EV[Build structured evidence dict<br/>numbers · top rows · metrics only from engine]
    EV --> DET[deterministic_research_insight<br/>Finding · Interpretation · Limitations]
    DET --> OLL{Ollama available?}
    OLL -->|no| OUT1[Engine draft only]
    OLL -->|yes| PROMPT[Prompt: prose around evidence<br/>do not invent numbers]
    PROMPT --> LLM[OllamaClient.generate]
    LLM --> PARSE[Parse sections or fallback]
    PARSE --> STRIP[strip_model_artifacts]
    STRIP --> OUT2[Full markdown brief<br/>Evidence block always engine-sourced]
    OUT1 --> UI[Streamlit expander]
    OUT2 --> UI
```

**Invariant:** statistics never originate in the LLM; they are injected as evidence.

---

## 10. End-to-end “happy path” sequence

```mermaid
sequenceDiagram
    participant U as User
    participant App as app.py
    participant DL as DataLoader
    participant Marts as Parquet marts
    participant Geo as geo.repair
    participant Gov as governance_store
    participant Eng as AnalyticsEngine
    participant UI as Module UI
    participant LLM as Ollama optional

    U->>App: Open app
    App->>DL: get_data prefer_cache
    alt cache valid
        DL->>Marts: load fact_*_daily
        Marts-->>DL: frames
    else rebuild
        DL->>DL: CSV classify → clean → dedup
        DL->>Geo: full_geo_repair
        Geo-->>DL: repaired + stats
        DL->>Marts: write_marts optional
    end
    DL-->>App: enrol, bio, demo, report
    App->>Gov: load patches
    App->>App: apply_governance_changes
    U->>App: Set filters + module
    App->>Eng: AnalyticsEngine filtered frames
    Eng->>Eng: get_anomalies / forecast_trends
    App->>UI: render selected module
    UI->>Eng: request insight
    Eng->>LLM: optional prose
    LLM-->>Eng: text
    Eng-->>UI: brief + charts
    UI-->>U: white-themed plots / map / radar
```

---

## 11. Repository map (where code lives)

```text
Aadhaar-Intel-Engine-UIDAI/
├── app.py / main.py              # Streamlit entry & routing
├── data/                         # CSV shards + processed marts
├── assets/reference/             # Geo rule packs, holidays, gold eval
├── output/                       # Governance patches & audit
├── docs/                         # Paper builder + live captures
├── tests/                        # forecast · geo repair · pin/manifest
└── src/
    ├── config.py                 # Paths, anomaly & forecast knobs
    ├── data_manager.py           # DataLoader
    ├── ai_core.py                # AnalyticsEngine
    ├── forecasting.py            # ForecastBackend
    ├── etl/build_cache.py        # Mart build CLI
    ├── geo/                      # normalize · repair · pin · centroids · eval
    ├── modules/                  # dashboard · analytics · predict · command · data_admin
    ├── services/                 # filters · governance_store
    ├── ai/                       # ollama_client · research_insights
    ├── components/navigation.py
    └── utils/                    # theme · plots white theme
```

---

## 12. Data contracts (operational grain)

```mermaid
flowchart LR
    subgraph Enrol["Enrolment"]
        E1[date]
        E2[state · district]
        E3[age bands]
        E4[adult_enrolments · total_enrolments]
    end

    subgraph Bio["Biometric updates"]
        B1[date · state · district]
        B2[bio_age_* · bio_stress]
    end

    subgraph Demo["Demographic updates"]
        D1[date · state · district]
        D2[demo_age_* · update_volume]
    end

    Enrol --> Cell["Analytics grain:<br/>state × district"]
    Bio --> Cell
    Demo --> Cell
    Enrol --> Nat["Forecast grain:<br/>national daily y"]
    Cell --> Risk[Anomaly + risk radar]
    Nat --> Fcst[Model bake-off + bands]
```

**Daily marts** drop pincode (aggregated). **dim_geo** keeps sample pincodes for governance PIN heuristics.

---

## 13. Configuration touchpoints

| Concern | Config / assets |
|---------|-----------------|
| Data paths | `src/config.py` → `DATA_DIR`, `PROCESSED_DIR`, `MARTS_ONLY`, `AUTO_BUILD_CACHE` |
| Anomaly defaults | `ANOMALY_CONTAMINATION`, `ANOMALY_MIN_VOLUME` |
| Forecast | `FORECAST_CANDIDATES`, `FORECAST_HOLDOUT_DAYS`, `FORECAST_RANDOM_SEED` |
| Holidays | `assets/reference/india_holidays.json` |
| Geo rules | `official_states`, `state_aliases`, `district_*`, `pin_prefix_states`, `telangana_districts`, `rules_manifest` |
| Map basemap | `command.MAP_STYLE` Carto Positron (light/white) |
| Plot chrome | `src/utils/plots.py` white Plotly theme |

---

## 14. Refresh & paper asset loop (research)

```mermaid
flowchart LR
    CODE[Code / data change] --> MART[python -m src.etl.build_cache]
    MART --> APP[streamlit run app.py]
    APP --> CAP[python docs/capture_live_assets.py<br/>charts + UI screenshots]
    CAP --> PAPER[python docs/build_symposium_paper.py]
    PAPER --> DOCX[docs/*_NSEFCCIC2026_Paper.docx/pdf]
```

---

## 15. Quick mental model

```text
CSV shards
   ↓  classify · validate · dedup
State canonicalize + full_geo_repair (+ optional gold eval)
   ↓
Parquet daily marts  ← fingerprint cache
   ↓
Human governance patches (durable)
   ↓
Global filters (state / date)
   ↓
AnalyticsEngine
   ├─ Isolation Forest → district flags → state risk radar (by volume)
   ├─ Forecast bake-off → Auto select vs MA → conformal band
   ├─ Correlation / market share / KPIs
   └─ Evidence → deterministic brief → optional Ollama prose
   ↓
Streamlit modules (Dashboard · Analytics · Forecast · White map · Governance)
```

---

*Generated for the Aadhaar Intel Engine repository. Keep this file updated when pipeline stages or module boundaries change.*
