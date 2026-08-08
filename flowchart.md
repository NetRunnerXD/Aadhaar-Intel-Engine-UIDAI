# Aadhaar Intel Engine — System Flowcharts

Research-grade operational analytics for **Aadhaar enrolment and update aggregates** (no Aadhaar numbers or biometrics). This document maps data flow, geo repair, analytics, forecasting, dual UIs (Streamlit + React), governance, and LLM briefs as implemented in the repository.

> **Disclaimer:** Isolation Forest scores and the risk radar are unsupervised outlier rankings (“look here”), not fraud labels. Forecasts are decision-band guides, not guarantees.

---

## 1. System at a glance

Two presentation layers share one Python analytics stack:

| Layer | Entry | Stack |
|-------|--------|--------|
| **Streamlit research UI** | `python main.py` or `streamlit run app.py` | Plotly, pydeck, Streamlit modules |
| **Professional web UI** | `python run_web.py` | React (Vite) + FastAPI + Recharts + deck.gl |

```mermaid
flowchart TB
    subgraph INPUT["Inputs"]
        CSV["data/*.csv shards<br/>enrol · bio · demo"]
        REF["assets/reference/*<br/>aliases · PIN map · holidays · gold"]
        GEOJSON["assets/india_states.geojson"]
        GOVSTORE["output/governance_patches.json<br/>+ governance_audit.csv"]
    end

    subgraph ETL["Ingest and marts"]
        DL["DataLoader<br/>src/data_manager.py"]
        BC["ETL build_cache<br/>src/etl/build_cache.py"]
        MARTS["data/processed/*.parquet<br/>fact_*_daily · dim_geo · agg_district"]
    end

    subgraph GEO["Geography"]
        NORM["canonicalize state<br/>src/geo/normalize.py"]
        REPAIR["full_geo_repair<br/>src/geo/repair.py"]
        PIN["PIN prefix → state<br/>src/geo/pin_map.py"]
        CENT["resolve_centroid<br/>src/geo/centroids.py"]
        EVAL["evaluate_geo_cleaning<br/>src/geo/eval_cleaning.py"]
    end

    subgraph CORE["Shared analytics core"]
        GOVAPPLY["governance patches<br/>src/services/governance_store.py"]
        FILT["state / date filters"]
        ENG["AnalyticsEngine<br/>src/ai_core.py"]
        FCST["ForecastBackend<br/>src/forecasting.py"]
        AI["research_insights + Ollama<br/>src/ai/*"]
    end

    subgraph ST["Streamlit UI"]
        STAPP["app.py"]
        STMOD["modules/<br/>dashboard · analytics · predict<br/>command · data_admin"]
    end

    subgraph WEB["React web UI"]
        RUN["run_web.py"]
        API["FastAPI web/api/main.py<br/>data_service.py"]
        SPA["React SPA web/frontend<br/>Dashboard · Analytics · Forecast<br/>Geospatial · Governance"]
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
    ENG --> FCST
    ENG --> AI
    GEOJSON --> STMOD
    GEOJSON --> API
    CENT --> STMOD
    CENT --> API

    ENG --> STAPP --> STMOD
    ENG --> API --> SPA
    AI --> STMOD
    AI --> SPA
    RUN --> API
    RUN --> SPA
```

---

## 2. Dual entry points and routing

### 2.1 Launch paths

```mermaid
flowchart TD
    U([User]) --> CHOICE{Which UI?}

    CHOICE -->|Research Streamlit| MAIN["python main.py"]
    MAIN --> GEOCHK["Download india_states.geojson<br/>if missing"]
    GEOCHK --> ST["streamlit run app.py"]

    CHOICE -->|Professional web| WEB["python run_web.py"]
    WEB --> NPM{"Node/npm available?"}
    NPM -->|yes| BUILD["npm install + npm run build<br/>web/frontend → dist/"]
    NPM -->|no + dist exists| REUSE[Reuse existing dist]
    BUILD --> UV["uvicorn web.api.main:app<br/>default :8787"]
    REUSE --> UV
    UV --> STATIC["Serve SPA + /api/*"]

    CHOICE -->|Dev split| DEVAPI["run_web.py --dev-api"]
    DEVAPI --> APIONLY[FastAPI only]
    CHOICE -->|Dev Vite| VITE["cd web/frontend && npm run dev"]
    VITE --> HMR[Vite HMR → proxy/API]
```

### 2.2 Streamlit startup (`app.py`)

```mermaid
flowchart TD
    START([streamlit run app.py]) --> THEME[theme.setup_page]
    THEME --> CACHE["@st.cache_resource load_raw_data()"]
    CACHE --> LOADER["DataLoader.get_data()<br/>prefer_cache=True"]

    LOADER --> EMPTY{enrol/bio/demo<br/>all empty?}
    EMPTY -->|yes| ERR[Show error + load logs<br/>+ load_report · stop]
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
    ROUTE -->|Data Governance| G[data_admin.render_tab]
```

### 2.3 React + FastAPI request path

```mermaid
flowchart TD
    BOOT([run_web.py / uvicorn]) --> STARTUP["startup: data_service.ensure_loaded()"]
    STARTUP --> DL[DataLoader.get_data]
    DL --> PATCH["Apply governance_store patches<br/>to in-memory enrol/demo/bio"]
    PATCH --> READY[Thread-safe _cache ready]

    SPA[React App.jsx] --> META["GET /api/meta"]
    SPA --> FILTUI[Sidebar: states · date range]
    FILTUI --> PAGES[Routes]

    PAGES -->|/| DASH["GET /api/dashboard"]
    PAGES -->|/analytics| ANA["GET /api/analytics"]
    PAGES -->|/forecast| FC["GET /api/forecast"]
    PAGES -->|/map| MAP["GET /api/map + /api/geojson"]
    PAGES -->|/governance| GOV["/api/governance/*"]

    DASH & ANA & FC & MAP --> ENG["data_service.engine_for<br/>→ AnalyticsEngine"]
    GOV --> GSTORE[governance_store + data_admin scans]
    SPA --> INS["/api/insights/* → generate_*_insight"]
    INS --> ENG
```

**Key files**

| Step | Module |
|------|--------|
| Streamlit entry | `app.py`, launcher `main.py` |
| Web launcher | `run_web.py` |
| Load | `src/data_manager.py` → `DataLoader` |
| Web cache / filters | `web/api/data_service.py` |
| REST API | `web/api/main.py` |
| Engine | `src/ai_core.py` → `AnalyticsEngine` |
| Streamlit nav | `src/components/navigation.py` |
| React shell | `web/frontend/src/App.jsx` |

---

## 3. FastAPI surface (web UI)

```mermaid
flowchart LR
    subgraph Meta["Meta"]
        H["GET /api/health"]
        M["GET /api/meta"]
        R["POST /api/reload"]
    end

    subgraph AnalyticsAPI["Analytics"]
        D["GET /api/dashboard"]
        A["GET /api/analytics"]
        AE["GET /api/analytics/export/{kind}"]
        F["GET /api/forecast"]
        FE["GET /api/forecast/export"]
    end

    subgraph MapAPI["Geospatial"]
        MP["GET /api/map"]
        MX["GET /api/map/export/{kind}"]
        GJ["GET /api/geojson"]
    end

    subgraph GovAPI["Governance"]
        G["GET /api/governance"]
        GS["GET /api/governance/scan"]
        GA["POST /api/governance/apply"]
        GR["POST /api/governance/revert"]
        GP["export-pack / import-pack / export-audit"]
    end

    subgraph InsightAPI["AI briefs"]
        ID["GET /api/insights/dashboard"]
        IF["GET /api/insights/forecast"]
        IG["GET /api/insights/governance"]
    end

    SPA[React pages] --> Meta & AnalyticsAPI & MapAPI & GovAPI & InsightAPI
```

| React page | Primary APIs | Visualization |
|------------|--------------|---------------|
| `Dashboard.jsx` | `/api/dashboard`, insights | Recharts + `AiPanel` |
| `Analytics.jsx` | `/api/analytics`, exports | Recharts (area, bar, pie, radar, scatter) |
| `Forecast.jsx` | `/api/forecast`, insights, export | Recharts composed + bake-off table |
| `Geospatial.jsx` | `/api/map`, `/api/geojson`, exports | deck.gl + MapLibre (Positron) |
| `Governance.jsx` | governance CRUD + insight | Issue cards, audit table, pack I/O |

Shared React components: `KpiCard`, `AiPanel`, `MarkdownBlock`, `api.js`.

---

## 4. Data load path (CSV ↔ Parquet marts)

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
    CLASS --> READ[Read and standardize<br/>dates · geo · numerics]
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
| `manifest.json` | source fingerprint, row counts, schema version, build metadata |

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

## 5. Geography repair pipeline

Order is fixed in `full_geo_repair()`:

```mermaid
flowchart TD
    IN[Raw/normalized frame<br/>state · district · pincode] --> S1

    subgraph S1["1 District typed as state"]
        DAS["repair_misfiled_states<br/>district_as_state.json<br/>+ corpus district→state"]
    end

    S1 --> S2
    subgraph S2["2 District name aliases"]
        AL["apply_district_aliases<br/>district_aliases.json"]
    end

    S2 --> S3
    subgraph S3["3 AP → Telangana boundary"]
        TS["apply_telangana_boundary_fix<br/>telangana_districts.json"]
    end

    S3 --> S4
    subgraph S4["4 PIN prefix fallback"]
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

Shared by Streamlit `command.py` and FastAPI `_map_frame` via `resolve_centroid`:

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

## 6. Session / durable governance

```mermaid
flowchart TD
    INIT[init / ensure_loaded] --> LOAD["governance_store.load_store<br/>patches + deletions + audit"]
    LOAD --> APPLY["Apply state/district renames<br/>and deletions to frames"]

    UI[Governance UI<br/>Streamlit or React] --> SCAN{Scan type}
    SCAN -->|State names| FS[find_state_discrepancies]
    SCAN -->|District names| FD[find_district_discrepancies<br/>PIN heuristics via dim_geo]
    FS --> FIX[User batch: Merge / Delete / Ignore]
    FD --> FIX
    FIX --> LOG[audit log append]
    LOG --> SAVE[persist patches JSON + audit CSV]
    SAVE --> RELOAD["Streamlit: data_dirty<br/>Web: POST /api/reload or re-scan"]

    IO[Import / Export pack] --> PACK[JSON pack of patches + audit]
```

**Durability:** patches live under `output/`; they re-apply on every load so marts + human fixes stay aligned without re-editing CSVs.

---

## 7. AnalyticsEngine — core services

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
    AN --> RR[State risk radar aggregation<br/>Analytics UI / API]
```

### 7.1 District feature matrix → Isolation Forest

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

### 7.2 State risk radar (Analytics)

```mermaid
flowchart LR
    AN[Flagged district cells] --> AGG["groupby state:<br/>max_risk · mean_risk<br/>flags · flagged_volume"]
    AGG --> SORT[Sort by flagged_volume DESC]
    SORT --> TOP[Top 10 states]
    TOP --> POLAR["Radar chart<br/>max / mean risk"]
    POLAR --> UI[Streamlit Plotly or React Recharts]
```

---

## 8. Forecasting flow

Candidates (config `FORECAST_CANDIDATES`): **MovingAverage**, **Drift**, **Ensemble**, **SeasonalNaive**.

```mermaid
flowchart TD
    DAILY["_daily_series national or by state"] --> CAL["complete_daily_calendar<br/>fill missing days with 0"]
    CAL --> MODE{model_type}

    MODE -->|Auto| CMP["ForecastBackend.compare_models<br/>rolling_origin_cv"]
    MODE -->|named| PICK[Named model from registry]

    subgraph CANDIDATES["Bake-off registry"]
        MA[MovingAverage + DOW shape]
        DR[Drift damped]
        ENS[Ensemble median]
        SN[SeasonalNaive lag-7]
    end

    CMP --> CANDIDATES
    CANDIDATES --> MET["Metrics: MASE · sMAPE · MAPE · RMSE · nRMSE · bias"]
    MET --> SEL["select_model: best primary metric default MASE<br/>must beat SeasonalNaive AND MovingAverage"]
    SEL --> PICK

    PICK --> PRED[Predict horizon H days]
    PRED --> BT[single_holdout backtest meta]
    PRED --> CI["split conformal |residual| quantile"]
    BT --> META[_last_forecast_meta]
    CI --> FRAME[forecast DataFrame date · predicted · lower · upper]
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

## 9. Module-level UI flows

### 9.1 Dashboard

```mermaid
flowchart TD
    IN[engine + filtered frames] --> KPI[KPI strip<br/>enrol · bio · demo · risk cells · forecast Δ]
    KPI --> MIX[Age mix + workload pie]
    KPI --> AN[Anomaly bar + investigation table]
    KPI --> OUT[30-day outlook + peak/floor]
    KPI --> BRIEF[AiPanel research brief]
    KPI --> LOGS[Collapsible system logs]
```

### 9.2 Analytics

```mermaid
flowchart TD
    IN[engine.df_enrol] --> KPI[Volume / states / districts / rows]
    KPI --> GROW[Growth trajectory + top regional drivers]
    KPI --> OPS[Ops mix pie + low-volume watchlist]
    KPI --> RISK[Risk radar · contamination · min_volume]
    RISK --> IF[get_anomalies force=True]
    IF --> STATE[State radar top 10 by flagged volume]
    IF --> DIST[District scatter + investigation notes]
    IF --> EXP[CSV export pack regional/trends/risk/ops]
```

### 9.3 Forecast

```mermaid
flowchart TD
    IN[engine + f_enrol] --> CTRL[Horizon · model · shock % · series scope]
    CTRL --> RUN[forecast_trends + compare_models]
    RUN --> CHART[History + path + conformal band]
    RUN --> BAKE[Model bake-off table]
    RUN --> RES[Resource planning KPIs]
    RUN --> BRIEF[AiPanel forecast brief]
    RUN --> CSV[Export forecast CSV]
```

### 9.4 Geospatial Intel (Streamlit pydeck ⟷ React deck.gl)

Both UIs share the same preparation logic (centroids, log/linear scale, intensity bands, GeoJSON borders, Carto Positron basemap):

```mermaid
flowchart TD
    IN[f_enrol] --> AGG["Aggregate district grain<br/>resolve_centroid + jitter"]
    AGG --> SCALE["Apply scale linear/log<br/>color · radius m · elevation"]
    SCALE --> MODE{viz mode}
    MODE -->|Intensity 2D| SC[ScatterplotLayer]
    MODE -->|Heatmap| HM[HeatmapLayer]
    MODE -->|3D| COL[ColumnLayer]
    SC & HM & COL --> DECK["Deck + MapLibre/Positron"]
    GEOJSON[GeoJsonLayer state borders] --> DECK
    DECK --> LEG[Intensity scale Low/Med/High]
    DECK --> EXP[Export CSV full / top20 / top10]
```

| Concern | Streamlit | React |
|---------|-----------|-------|
| Entry | `src/modules/command.py` | `GET /api/map` + `Geospatial.jsx` |
| Layers | pydeck | deck.gl 9 + react-map-gl/maplibre |
| Depth default | Top 5 Priority | `top5` |
| HTML export | pydeck `to_html` | not exposed |

### 9.5 Data Governance

```mermaid
flowchart TD
    TAB[Fix / Audit / Import-Export] --> T1[Scan states or districts]
    TAB --> T2[Audit filter · revert · export]
    TAB --> T3[Pack JSON import / export]
    T1 --> ACT[Merge / Delete / Ignore per row]
    ACT --> COMMIT[Commit page · Auto-fix high · Merge all]
    COMMIT --> STORE[Persist patches + audit]
    TAB --> BRIEF[AiPanel governance insight]
```

---

## 10. LLM research brief path

```mermaid
flowchart TD
    CALL["generate_*_insight / research_insight"] --> EV[Build structured evidence dict<br/>numbers · top rows · metrics only from engine]
    EV --> DET[deterministic_research_insight<br/>Finding · Interpretation · Limitations]
    DET --> OLL{Ollama available?}
    OLL -->|no| OUT1[Engine draft only]
    OLL -->|yes| PROMPT[Prompt: prose around evidence<br/>do not invent numbers]
    PROMPT --> LLM["OllamaClient.generate<br/>OLLAMA_HOST · OLLAMA_MODEL"]
    LLM --> PARSE[Parse sections or fallback]
    PARSE --> STRIP[strip_model_artifacts]
    STRIP --> OUT2[Full markdown brief<br/>Evidence block always engine-sourced]
    OUT1 --> UI[Streamlit expander or React AiPanel]
    OUT2 --> UI
```

**Invariant:** statistics never originate in the LLM; they are injected as evidence.

Defaults: `OLLAMA_HOST=http://127.0.0.1:11434`, `OLLAMA_MODEL=qwen2.5:latest`.

---

## 11. End-to-end sequences

### 11.1 Streamlit happy path

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

    U->>App: Open Streamlit
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
    UI-->>U: plots / map / radar
```

### 11.2 React web happy path

```mermaid
sequenceDiagram
    participant U as User
    participant SPA as React SPA
    participant API as FastAPI
    participant DS as data_service
    participant Eng as AnalyticsEngine
    participant LLM as Ollama optional

    U->>SPA: Open :8787
    SPA->>API: GET /api/meta
    API->>DS: ensure_loaded
    DS-->>API: states · dates · LLM status · load_report
    API-->>SPA: meta

    U->>SPA: Filters + open Dashboard
    SPA->>API: GET /api/dashboard?states&start&end&…
    API->>DS: filter_frames + engine_for
    DS->>Eng: KPIs · anomalies · forecast slice
    Eng-->>API: JSON payload
    API-->>SPA: kpis · charts · logs
    SPA-->>U: Recharts dashboard

    U->>SPA: Generate AI insight
    SPA->>API: GET /api/insights/dashboard
    API->>Eng: generate_dashboard_insight
    Eng->>LLM: optional prose
    LLM-->>Eng: markdown
    Eng-->>SPA: markdown
    SPA-->>U: AiPanel

    U->>SPA: Geospatial map
    SPA->>API: GET /api/map + /api/geojson
    API-->>SPA: points · colors · elevations · borders
    SPA-->>U: deck.gl map
```

---

## 12. Repository map

```text
Aadhaar-Intel-Engine-UIDAI/
├── main.py                         # Streamlit launcher + GeoJSON download
├── app.py                          # Streamlit application & routing
├── run_web.py                      # React UI launcher (build + uvicorn)
├── flowchart.md                    # This document
├── requirements.txt
├── data/                           # CSV shards + processed/ marts
├── assets/
│   ├── india_states.geojson
│   └── reference/                  # Geo rules, holidays, gold eval
├── output/                         # Governance patches & audit
├── docs/                           # Paper builder + live captures
├── tests/                          # forecast · geo repair · pin/manifest
├── web/
│   ├── FEATURE_PARITY.md           # Streamlit ↔ React parity notes
│   ├── api/
│   │   ├── main.py                 # FastAPI routes
│   │   └── data_service.py         # Load cache, filters, engine_for
│   └── frontend/                   # React + Vite SPA
│       └── src/
│           ├── App.jsx             # Shell · sidebar · routes
│           ├── api.js
│           ├── components/         # KpiCard · AiPanel · MarkdownBlock
│           └── pages/              # Dashboard · Analytics · Forecast
│                                   # Geospatial · Governance
└── src/
    ├── config.py                   # Paths, anomaly & forecast knobs
    ├── data_manager.py             # DataLoader
    ├── ai_core.py                  # AnalyticsEngine
    ├── forecasting.py              # ForecastBackend
    ├── etl/build_cache.py          # Mart build CLI
    ├── geo/                        # normalize · repair · pin · centroids · eval
    ├── modules/                    # Streamlit: dashboard · analytics · predict
    │                               # command · data_admin
    ├── services/                   # filters · governance_store
    ├── ai/                         # ollama_client · research_insights
    ├── components/navigation.py
    └── utils/                      # theme · plots
```

---

## 13. Data contracts (operational grain)

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
    Enrol --> Nat["Forecast grain:<br/>national or state daily y"]
    Cell --> Risk[Anomaly + risk radar + map]
    Nat --> Fcst[Model bake-off + bands]
```

**Daily marts** drop pincode (aggregated). **dim_geo** keeps sample pincodes for governance PIN heuristics.

Natural key on raw CSV grain: `date · state · district · pincode` (`NATURAL_KEY`).

---

## 14. Configuration touchpoints

| Concern | Config / assets |
|---------|-----------------|
| Data paths | `src/config.py` → `DATA_DIR`, `PROCESSED_DIR`, `MARTS_ONLY`, `AUTO_BUILD_CACHE` |
| Cache schema | `CACHE_SCHEMA_VERSION`, `GEO_RULE_PACK_VERSION` |
| Anomaly defaults | `ANOMALY_CONTAMINATION`, `ANOMALY_MIN_VOLUME` |
| Forecast | `FORECAST_CANDIDATES`, holdout/rolling knobs, `FORECAST_PRIMARY_METRIC`, conformal α |
| Holidays | `assets/reference/india_holidays.json` |
| Geo rules | official_states, aliases, district_*, pin_prefix, telangana, rules_manifest |
| LLM | `OLLAMA_HOST`, `OLLAMA_MODEL` |
| Map basemap | Carto Positron (Streamlit `command.MAP_STYLE` / React `MAP_STYLE`) |
| Plot chrome | Streamlit: `src/utils/plots.py`; React: Recharts + CSS |

---

## 15. Refresh and paper asset loop

```mermaid
flowchart LR
    CODE[Code / data change] --> MART[python -m src.etl.build_cache]
    MART --> APP[streamlit run app.py<br/>and/or python run_web.py]
    APP --> CAP[python docs/capture_live_assets.py<br/>charts + UI screenshots]
    CAP --> PAPER[python docs/build_symposium_paper.py]
    PAPER --> DOCX[docs/*_NSEFCCIC2026_Paper.docx/pdf]
```

---

## 16. Quick mental model

```text
CSV shards
   ↓  classify · validate · dedup
State canonicalize + full_geo_repair (+ optional gold eval)
   ↓
Parquet daily marts  ← fingerprint cache
   ↓
Human governance patches (durable under output/)
   ↓
┌──────────────────────┬──────────────────────┐
│ Streamlit app.py     │ FastAPI data_service │
│ session filters      │ query filters        │
└──────────┬───────────┴──────────┬───────────┘
           ↓                      ↓
              AnalyticsEngine
   ├─ Isolation Forest → district flags → state risk radar
   ├─ Forecast bake-off (MA / Drift / Ensemble / SeasonalNaive)
   │     → Auto select vs baselines → conformal band
   ├─ Correlation / market share / KPIs
   └─ Evidence → deterministic brief → optional Ollama prose
           ↓                      ↓
   Streamlit modules         React pages (parity)
   dashboard · analytics     Dashboard · Analytics
   predict · command         Forecast · Geospatial
   data_admin                Governance
```

---

## 17. Feature parity note

React web UI is maintained at feature parity with Streamlit modules (see `web/FEATURE_PARITY.md`). Intentional gaps:

- Map HTML export (`pydeck.to_html`) is Streamlit-only
- Visual chrome differs (custom React CSS vs Streamlit theme)

Core data, anomalies, forecast bake-off, governance store, and LLM evidence path are shared.

---

*Updated for the dual Streamlit + React/FastAPI architecture. Keep this file in sync when pipeline stages, API routes, or module boundaries change.*
