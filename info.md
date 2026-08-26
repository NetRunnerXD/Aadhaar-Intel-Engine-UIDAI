# Aadhaar Intel Engine — Comprehensive Technical Architecture & Mathematical Foundations

> **System Version**: 2.0.0 · **Cache Schema Version**: 4 · **Geo Rule Pack**: 1.1.0  
> **Platform Purpose**: Production-grade operational intelligence, outlier diagnostics, multi-model volume forecasting, and spatial analytics built entirely on UIDAI aggregate count data (strict zero PII / no Aadhaar numbers).

---

## Table of Contents

1. [System Architecture & Runtime Overview](#1-system-architecture--runtime-overview)
2. [Datasets & Raw Schemas](#2-datasets--raw-schemas)
3. [Deduplication & Ingestion Pipeline](#3-deduplication--ingestion-pipeline)
4. [Geographic Repair & Canonicalization Engine](#4-geographic-repair--canonicalization-engine)
5. [Parquet Mart Generation & Cache Subsystem](#5-parquet-mart-generation--cache-subsystem)
6. [Parquet Mart Schemas & Storage Design](#6-parquet-mart-schemas--storage-design)
7. [Mathematical Formulations & Statistical Foundations](#7-mathematical-formulations--statistical-foundations)
   - [7.1 Forecast Error Metrics & Derivations](#71-forecast-error-metrics--derivations)
   - [7.2 Time Series & Machine Learning Forecast Models](#72-time-series--machine-learning-forecast-models)
   - [7.3 Rolling-Origin Cross Validation & Baseline Gating](#73-rolling-origin-cross-validation--baseline-gating)
   - [7.4 Conformal Prediction Intervals](#74-conformal-prediction-intervals)
   - [7.5 Unsupervised Anomaly Detection & Isolation Forests](#75-unsupervised-anomaly-detection--isolation-forests)
   - [7.6 Spatial Geometry, Scaling & Jitter Mathematics](#76-spatial-geometry-scaling--jitter-mathematics)
   - [7.7 Governance Fuzzy Matching & Sequence Matcher Ratios](#77-governance-fuzzy-matching--sequence-matcher-ratios)
8. [Backend Engine Deep Dive](#8-backend-engine-deep-dive)
9. [Frontend Applications](#9-frontend-applications)
   - [9.1 Streamlit Analytics Console](#91-streamlit-analytics-console)
   - [9.2 React 18 + FastAPI Modern Operator App](#92-react-18--fastapi-modern-operator-app)
10. [Modules Breakdown](#10-modules-breakdown)
11. [AI & Local LLM Integration](#11-ai--local-llm-integration)
12. [Data Governance & Durable Patching](#12-data-governance--durable-patching)
13. [Reference Knowledge Assets & Rule Packs](#13-reference-knowledge-assets--rule-packs)
14. [Configuration Matrix & Runtime Parameters](#14-configuration-matrix--runtime-parameters)
15. [Verification, Quality Assurance & Deployment](#15-verification-quality-assurance--deployment)

---

## 1. System Architecture & Runtime Overview

The platform uses a **dual-interface, shared analytics core** design. Both client runtimes (Streamlit and React/FastAPI) delegate statistical and data-loading routines to the exact same backend engine classes (`AnalyticsEngine`, `DataLoader`, `ForecastBackend`), guaranteeing absolute metric parity.

```
                                  ┌───────────────────────────────────────────────────────────┐
                                  │                  Raw CSV Shard Ingestion                  │
                                  │   Enrolment (3 shards) · Bio (4 shards) · Demo (5 shards) │
                                  │                 (~4.94 Million Total Rows)                │
                                  └─────────────────────────────┬─────────────────────────────┘
                                                                │
                                                                ▼
                                  ┌───────────────────────────────────────────────────────────┐
                                  │              ETL & Parquet Mart Generation                │
                                  │               (src/etl/build_cache.py)                    │
                                  │  - SHA-256 Fingerprinting  - 5-Stage Geo Normalization    │
                                  │  - Quarantine Rejections   - Natural Key Deduplication    │
                                  └─────────────────────────────┬─────────────────────────────┘
                                                                │
                                                                ▼
                                  ┌───────────────────────────────────────────────────────────┐
                                  │                 Processed Parquet Marts                   │
                                  │                    (data/processed/)                      │
                                  │  - fact_enrol_daily.parquet   - fact_bio_daily.parquet    │
                                  │  - fact_demo_daily.parquet    - agg_district.parquet      │
                                  │  - dim_geo.parquet            - manifest.json             │
                                  └─────────────────────────────┬─────────────────────────────┘
                                                                │
                                                                ▼
                                  ┌───────────────────────────────────────────────────────────┐
                                  │                   Unified Engine Layer                    │
                                  │                                                           │
                                  │   DataLoader (src/data_manager.py)                        │
                                  │   AnalyticsEngine (src/ai_core.py)                        │
                                  │   ForecastBackend (src/forecasting.py)                    │
                                  │   GeoRepair / Centroids (src/geo/*)                       │
                                  │   GovernanceStore (src/services/governance_store.py)      │
                                  └─────────────────────────────┬─────────────────────────────┘
                                                                │
                                    ┌───────────────────────────┴───────────────────────────┐
                                    ▼                                                       ▼
      ┌──────────────────────────────────────────────────────────┐   ┌──────────────────────────────────────────────┐
      │               Streamlit Research Console                 │   │          FastAPI + React Modern App          │
      │                  (app.py / Port 8501)                    │   │        (web/api/main.py / Port 8787)         │
      ├──────────────────────────────────────────────────────────┤   ├──────────────────────────────────────────────┤
      │ • Interactive Filter Sidebar with Dynamic Date Bounds    │   │ • FastAPI REST API with Pydantic Validation  │
      │ • Plotly Charting with Polished Contrast Theme           │   │ • React 18 SPA (Vite + React Router)         │
      │ • 3D Column & Heatmap Pydeck Layers                      │   │ • Deck.gl / MapLibre GL Vector Basemaps      │
      │ • Human-in-the-Loop Governance Triage Console            │   │ • Recharts Responsive Composed Charts        │
      └──────────────────────────────────────────────────────────┘   └──────────────────────────────────────────────┘
```

---

## 2. Datasets & Raw Schemas

The engine ingests raw transaction activity published by UIDAI as multi-shard CSV files without individual identity details.

### 2.1 Enrolment Shards (`api_data_aadhar_enrolment_*.csv`)
* **Files**: `api_data_aadhar_enrolment_1.csv`, `api_data_aadhar_enrolment_2.csv`, `api_data_aadhar_enrolment_3.csv`
* **Raw Row Count**: 1,006,029 rows
* **Header Row**:
  ```csv
  date,state,district,pincode,age_0_5,age_5_17,age_18_greater
  ```
* **Column Definitions**:
  - `date` (*string, DD-MM-YYYY*): Calendar date of record generation.
  - `state` (*string*): Unsanitized state/UT label (frequently contains spelling noise or city names).
  - `district` (*string*): District name string.
  - `pincode` (*numeric/string*): 6-digit postal index number.
  - `age_0_5` (*integer $\ge 0$*): Total new enrolments for infants/children aged 0–5 years.
  - `age_5_17` (*integer $\ge 0$*): Total new enrolments for school-age youth aged 5–17 years.
  - `age_18_greater` (*integer $\ge 0$*): Total new adult enrolments (18+ years).

### 2.2 Biometric Update Shards (`api_data_aadhar_biometric_*.csv`)
* **Files**: `api_data_aadhar_biometric_1.csv` through `api_data_aadhar_biometric_4.csv`
* **Raw Row Count**: 1,861,108 rows
* **Header Row**:
  ```csv
  date,state,district,pincode,bio_age_5_17,bio_age_17_
  ```
* **Column Definitions**:
  - `date`, `state`, `district`, `pincode`: Natural geographic/temporal coordinates.
  - `bio_age_5_17` (*integer $\ge 0$*): Mandatory Biometric Updates (MBU) for children (fingerprints/iris captured at ages 5 & 15).
  - `bio_age_17_` (*integer $\ge 0$*): Biometric updates/recaptures for individuals 17+ years.

### 2.3 Demographic Update Shards (`api_data_aadhar_demographic_*.csv`)
* **Files**: `api_data_aadhar_demographic_1.csv` through `api_data_aadhar_demographic_5.csv`
* **Raw Row Count**: 2,071,700 rows
* **Header Row**:
  ```csv
  date,state,district,pincode,demo_age_5_17,demo_age_17_
  ```
* **Column Definitions**:
  - `date`, `state`, `district`, `pincode`: Geographic/temporal coordinates.
  - `demo_age_5_17` (*integer $\ge 0$*): Name, address, date of birth, or mobile changes for ages 5–17.
  - `demo_age_17_` (*integer $\ge 0$*): Demographic updates for adults 17+.

---

## 3. Deduplication & Ingestion Pipeline

### 3.1 The Ingestion Problem
Because UIDAI data is sourced across distributed network nodes and multiple pipeline extractions:
1. Multiple batch jobs emit overlapping records for identical `(date, state, district, pincode)` tuples.
2. Inconsistent column capitalization (`State`, `STATE`, `state`) and trailing whitespaces exist across shards.
3. Dates are represented in localized DD-MM-YYYY format.
4. Duplicate keys do not represent erroneous row repetitions to discard blindly; they represent additive partial sub-counts recorded by different registrars/enrolment stations.

### 3.2 Deduplication Algorithm
The engine identifies the natural key:
$$\text{Natural Key} = \langle \text{date}, \text{state}, \text{district}, \text{pincode} \rangle$$

The pipeline executes in `src/data_manager.py` within `DataLoader._dedup_aggregate()`:

```python
def _dedup_aggregate(self, df: pd.DataFrame, value_cols: List[str], kind: str) -> pd.DataFrame:
    key = [c for c in NATURAL_KEY if c in df.columns]
    if len(key) < 4:
        return df
    before = len(df)
    agg = df.groupby(key, as_index=False, observed=True)[value_cols].sum()
    collapsed = before - len(agg)
    return agg
```

### 3.3 Quarantine Gate
Before aggregation, data passes through `_quarantine_invalid()`:
1. **Date Validation**: `pd.to_datetime(df['date'], dayfirst=True, errors='coerce')` — rows with NaT dates are dropped.
2. **Pincode Range Gate**: Valid PINs must satisfy $100000 \le \text{pincode} \le 999999$.
3. **Official State Whitelist**: State must exist in `official_states.json` (36 official States/UTs). Numeric strings (e.g., `"100000"`) or unresolvable strings are quarantined.

### 3.4 Ingestion & Dedup Verification Matrix (from Manifest)

| Metric | Enrolment Mart | Biometric Mart | Demographic Mart | Total / Combined |
| :--- | :--- | :--- | :--- | :--- |
| **Raw Input Rows** | 1,006,029 | 1,861,108 | 2,071,700 | **4,938,837** |
| **Quarantined Rows** | 22 | 0 | 2 | **24** |
| **Collapsed Duplicate Keys** | 40,027 | 169,725 | 528,394 | **738,146** |
| **Clean Pin-Grain Rows** | 965,980 | 1,691,383 | 1,543,304 | **4,200,667** |
| **Daily Mart Grain Rows** | **63,474** | **74,485** | **80,328** | **218,287** |

---

## 4. Geographic Repair & Canonicalization Engine

Raw administrative names contain systemic historical, orthographic, and structural errors. The geo engine (`src/geo/repair.py`, `src/geo/normalize.py`) resolves these in a deterministic 5-stage pipeline.

```
Raw Geo Input (State, District, Pincode)
     │
     ▼
[ Stage 1: State Name Canonicalization ] ────► Matches state_aliases.json (e.g., 'Orissa' → 'Odisha')
     │
     ▼
[ Stage 2: District-as-State Repair ] ──────► Corrects city names in state column (e.g., State='Jaipur' → State='Rajasthan')
     │
     ▼
[ Stage 3: District Alias Normalization ] ──► Standardizes spelling (e.g., 'Bangalore' → 'Bengaluru Urban')
     │
     ▼
[ Stage 4: AP ➔ Telangana Reassignment ] ───► Moves pre-bifurcation districts (e.g., Hyderabad in AP → Telangana)
     │
     ▼
[ Stage 5: PIN Prefix Fallback ] ───────────► Infers state from first 2 digits of Pincode if state still invalid
     │
     ▼
Clean Canonical Geography (State, District, Pincode)
```

### Stage 1: State Canonicalization (`src/geo/normalize.py`)
Applies 27 rule mappings from `assets/reference/state_aliases.json`.
* `"orissa"` $\to$ `"Odisha"`
* `"pondicherry"` $\to$ `"Puducherry"`
* `"west bangal"`, `"west bengli"`, `"west bengal."` $\to$ `"West Bengal"`
* `"jammu and kashmir"` $\to$ `"Jammu & Kashmir"`
* `"the dadra and nagar haveli and daman and diu"` $\to$ `"Dadra & Nagar Haveli And Daman & Diu"`
* `"nct of delhi"` $\to$ `"Delhi"`
* `"uttaranchal"` $\to$ `"Uttarakhand"`

### Stage 2: District-As-State Inversion Repair
Certain data generation systems misplaced the district/city token into the `state` field. Seed rules in `district_as_state.json` repair these:
* State `"Jaipur"` $\to$ State `"Rajasthan"`, District `"Jaipur"`
* State `"Nagpur"` $\to$ State `"Maharashtra"`, District `"Nagpur"`
* State `"Darbhanga"` $\to$ State `"Bihar"`, District `"Darbhanga"`
* State `"Balanagar"` $\to$ State `"Telangana"`, District `"Balanagar"`
* State `"Puttenahalli"` $\to$ State `"Karnataka"`, District `"Bengaluru Urban"`
* State `"Raja Annamalai Puram"` $\to$ State `"Tamil Nadu"`, District `"Chennai"`
* State `"Madanapalle"` $\to$ State `"Andhra Pradesh"`, District `"Madanapalle"`

### Stage 3: District Alias Normalization
Applies 42 canonical name mappings from `assets/reference/district_aliases.json` across 205,657 matching records:
* `{"bangalore", "bengaluru", "bangalore urban"} \to \text{"Bengaluru Urban"}`
* `{"gurgaon", "gurugram"} \to \text{"Gurugram"}`
* `{"bombay"} \to \text{"Mumbai"}`
* `{"calcutta"} \to \text{"Kolkata"}`
* `{"madras"} \to \text{"Chennai"}`
* `{"cuddapah", "kadapa", "y. s. r"} \to \text{"Y.S.R."}`
* `{"k.v. rangareddy", "rangareddi"} \to \text{"Ranga Reddy"}`
* `{"spsr nellore", "nellore"} \to \text{"Sri Potti Sriramulu Nellore"}`

### Stage 4: Andhra Pradesh $\to$ Telangana Boundary Reassignment
Following the Andhra Pradesh Reorganisation Act, 2014, Telangana was formed. Legacy UIDAI systems tagged Telangana districts under Andhra Pradesh. Using `assets/reference/telangana_districts.json` (43 district tokens), the pipeline reassigns 92,491 records:
$$\text{If } \text{state} = \text{"Andhra Pradesh"} \land \text{district} \in \text{Telangana\_Districts} \implies \text{state} \leftarrow \text{"Telangana"}$$

### Stage 5: PIN Prefix Heuristic Fallback
When a state remains unrecognized, the first 2 digits of the 6-digit Indian PIN code map to postal circles via `assets/reference/pin_prefix_states.json` (65 prefixes covering circles `11` through `85`):
$$\text{prefix} = \lfloor \text{pincode} / 10000 \rfloor \implies \text{state} \leftarrow \text{CircleMap}(\text{prefix})$$

### 4.1 Evaluation Against Gold Standard (`eval_geo_gold.json`)
The cleaning engine is evaluated against synthetic gold-standard unit cases covering all corruption classes. The pipeline achieves **100% accuracy** ($\ge 90\%$ SLA threshold) on both state and district resolution.

---

## 5. Parquet Mart Generation & Cache Subsystem

The ETL system (`src/etl/build_cache.py`) converts raw, distributed CSV data into high-performance, compressed columnar Parquet files.

### 5.1 Deterministic Source Fingerprinting
To avoid expensive re-parsing of multi-gigabyte files while detecting any modification, the cache computes a SHA-256 hash across file metadata without reading full disk contents:

$$\text{Fingerprint} = \text{SHA256}\left( \text{CACHE\_SCHEMA\_VERSION} \,\|\, \bigoplus_{f \in \text{CSVs}} \big( \text{name}(f) \,\|\, \text{size}(f) \,\|\, \text{mtime\_ns}(f) \big) \right)$$

```python
def source_fingerprint(data_dir: Path) -> str:
    h = hashlib.sha256()
    h.update(str(CACHE_SCHEMA_VERSION).encode())
    for path in list_csv_files(data_dir):
        st = path.stat()
        h.update(path.name.encode("utf-8"))
        h.update(str(st.st_size).encode())
        h.update(str(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))).encode())
    return h.hexdigest()
```

### 5.2 Cache Invalidation Conditions
A cache hit occurs only if:
1. All 5 `.parquet` marts and `manifest.json` exist in `data/processed/`.
2. `manifest.json["schema_version"] == CACHE_SCHEMA_VERSION` (currently `4`).
3. `manifest.json["source_fingerprint"] == current_source_fingerprint(data_dir)`.

If any condition fails, the ETL engine rebuilds all marts automatically unless `MARTS_ONLY=1` is enforced.

---

## 6. Parquet Mart Schemas & Storage Design

Parquet marts downcast all 64-bit numeric types to compact 32-bit representations and encode recurring state and district strings as native Arrow dictionary-encoded categories.

```
data/processed/
├── fact_enrol_daily.parquet    (63,474 rows  | Daily Enrolment by District)
├── fact_bio_daily.parquet      (74,485 rows  | Daily Biometric Updates by District)
├── fact_demo_daily.parquet     (80,328 rows  | Daily Demographic Updates by District)
├── agg_district.parquet        (953 rows     | Lifetime Summary by District)
├── dim_geo.parquet             (30,162 rows  | Complete Distinct Hierarchy)
└── manifest.json               (Metadata, SHA-256 Fingerprint & Load Report)
```

### 6.1 `fact_enrol_daily.parquet`
* **Grain**: $\text{date} \times \text{state} \times \text{district}$
* **Rows**: 63,474

| Field Name | Storage Type | Logical Meaning | Derivation / Notes |
| :--- | :--- | :--- | :--- |
| `date` | `timestamp[ns]` | Transaction Date | `pd.to_datetime(errors='coerce')` |
| `state` | `category` (dict) | Canonical State / UT | Whitelisted against official states |
| `district` | `category` (dict) | Canonical District | Title-cased and alias-mapped |
| `age_0_5` | `int32` | Infant / Child Enrolments | $\sum$ raw `age_0_5` |
| `age_5_17` | `int32` | School-age Enrolments | $\sum$ raw `age_5_17` |
| `age_18_greater` | `int32` | Adult Enrolments | $\sum$ raw `age_18_greater` |
| `adult_enrolments`| `int32` | Adult Volume Alias | Equal to `age_18_greater` |
| `total_enrolments`| `int32` | Daily Total Enrolments | `age_0_5` + `age_5_17` + `age_18_greater` |

### 6.2 `fact_bio_daily.parquet`
* **Grain**: $\text{date} \times \text{state} \times \text{district}$
* **Rows**: 74,485

| Field Name | Storage Type | Logical Meaning | Derivation / Notes |
| :--- | :--- | :--- | :--- |
| `date` | `timestamp[ns]` | Transaction Date | Daily calendar date |
| `state` | `category` | Canonical State / UT | Whitelisted |
| `district` | `category` | Canonical District | Canonicalized |
| `bio_age_5_17` | `int32` | Child MBU Count | $\sum$ raw `bio_age_5_17` |
| `bio_age_17_` | `int32` | Adult Biometric Updates| $\sum$ raw `bio_age_17_` |
| `bio_stress` | `int32` | Total Biometric Load | `bio_age_5_17` + `bio_age_17_` |

### 6.3 `fact_demo_daily.parquet`
* **Grain**: $\text{date} \times \text{state} \times \text{district}$
* **Rows**: 80,328

| Field Name | Storage Type | Logical Meaning | Derivation / Notes |
| :--- | :--- | :--- | :--- |
| `date` | `timestamp[ns]` | Transaction Date | Daily calendar date |
| `state` | `category` | Canonical State / UT | Whitelisted |
| `district` | `category` | Canonical District | Canonicalized |
| `demo_age_5_17` | `int32` | Youth Demographic Updates | $\sum$ raw `demo_age_5_17` |
| `demo_age_17_` | `int32` | Adult Demographic Updates | $\sum$ raw `demo_age_17_` |
| `update_volume` | `int32` | Total Demographic Load | `demo_age_5_17` + `demo_age_17_` |

### 6.4 `agg_district.parquet`
* **Grain**: $\text{state} \times \text{district}$
* **Rows**: 953 distinct district entities

| Field Name | Storage Type | Logical Meaning |
| :--- | :--- | :--- |
| `state` | `category` | Canonical State |
| `district` | `category` | Canonical District |
| `total_enrolments` | `int64` | Lifetime aggregate enrolment volume |
| `adult_enrolments` | `int64` | Lifetime aggregate adult volume (18+) |
| `age_0_5` | `int64` | Lifetime infant volume (0–5) |
| `age_5_17` | `int64` | Lifetime youth volume (5–17) |
| `age_18_greater` | `int64` | Lifetime adult volume (18+) |

### 6.5 `dim_geo.parquet`
* **Grain**: $\text{state} \times \text{district} \times \text{pincode}$
* **Rows**: 30,162 distinct geographic coordinate nodes across India

| Field Name | Storage Type | Logical Meaning |
| :--- | :--- | :--- |
| `state` | `string` | Canonical State |
| `district` | `string` | Canonical District |
| `pincode` | `int32` | Validated 6-Digit PIN |

---

## 7. Mathematical Formulations & Statistical Foundations

### 7.1 Forecast Error Metrics & Derivations

Let $y_t$ represent the true actual volume at time step $t$, and $\hat{y}_t$ represent the model's point forecast over a validation horizon $t \in \{1, \dots, h\}$.

```
                           Forecast Evaluation Framework
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                                                                             │
 │    Scale-Dependent               Percentage-Based          Scale-Free       │
 │   ┌───────────────┐             ┌────────────────┐     ┌────────────────┐   │
 │   │ RMSE  /  Bias │             │  MAPE / sMAPE  │     │      MASE      │   │
 │   └───────┬───────┘             └───────┬────────┘     └────────┬───────┘   │
 │           │                             │                       │           │
 │           ▼                             ▼                       ▼           │
 │   Raw volumetric error          Symmetric relative      Normalized against  │
 │   in number of people           accuracy percentage     Seasonal Naive      │
 │                                                                             │
 └─────────────────────────────────────────────────────────────────────────────┘
```

#### 1. Mean Absolute Scaled Error (MASE) — *Primary Ranking Metric*
MASE scales the forecast error against the in-sample Mean Absolute Error of a seasonal naive persistence baseline ($m=7$ for weekly cadence):

$$\text{MASE} = \frac{\frac{1}{h} \sum_{t=1}^{h} \left| y_t - \hat{y}_t \right|}{\frac{1}{T - m} \sum_{t=m+1}^{T} \left| y_t - y_{t-m} \right|}$$

* **Mathematical Properties**:
  - Independent of data scale (enables valid comparison between high-volume states like UP and low-volume UTs like Ladakh).
  - Defined whenever the time series is non-constant.
  - $\text{MASE} < 1.0 \implies$ Model outperforms the 7-day seasonal persistence naive baseline.
  - $\text{MASE} = 1.0 \implies$ Model is mathematically identical to repeating last week's values.
  - $\text{MASE} > 1.0 \implies$ Model performs worse than the simple baseline.

#### 2. Symmetric Mean Absolute Percentage Error (sMAPE)
$$\text{sMAPE} = \frac{100\%}{h} \sum_{t=1}^{h} \frac{2 \left| y_t - \hat{y}_t \right|}{\left| y_t \right| + \left| \hat{y}_t \right| + \epsilon}$$
* Constant $\epsilon = 10^{-9}$ prevents division by zero.
* Unlike standard MAPE, sMAPE treats over-forecasting and under-forecasting symmetrically and bounds individual errors strictly in $[0\%, 200\%]$.

#### 3. Root Mean Squared Error (RMSE) & Normalized RMSE (nRMSE)
$$\text{RMSE} = \sqrt{\frac{1}{h} \sum_{t=1}^{h} (y_t - \hat{y}_t)^2}, \qquad \text{nRMSE} = \frac{\text{RMSE}}{\frac{1}{h}\sum_{t=1}^{h} y_t + \epsilon}$$

#### 4. Mean Forecast Bias
$$\text{Bias} = \frac{1}{h} \sum_{t=1}^{h} (\hat{y}_t - y_t)$$
* $\text{Bias} > 0 \implies$ Systematic over-prediction (excess capacity risk).
* $\text{Bias} < 0 \implies$ Systematic under-prediction (queue overflow risk).

---

### 7.2 Time Series & Machine Learning Forecast Models

Let history vector be $\mathbf{y}_{1:T} = [y_1, y_2, \dots, y_T]^T$. Horizon step is $k \in \{1, \dots, H\}$.

```
                               Forecast Model Families
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                                                                                  │
 │    Statistical / Heuristic          Supervised / Feature-Driven      Ensemble    │
 │   ┌───────────────────────┐        ┌────────────────────────────┐  ┌──────────┐  │
 │   │ • SeasonalNaive       │        │ • Linear / Ridge (t)       │  │ • Median │  │
 │   │ • MovingAverage (DOW) │        │ • SeasonalHoliday          │  │   Voting │  │
 │   │ • Drift (Damped)      │        │ • RidgeLags (13 Features)  │  │          │  │
 │   │ • Seasonal            │        │ • HistGradientBoosting     │  └──────────┘  │
 │   └───────────────────────┘        └────────────────────────────┘                │
 └──────────────────────────────────────────────────────────────────────────────────┘
```

#### 1. SeasonalNaive Model
Repeats the value observed exactly 7 days prior:
$$\hat{y}_{T+k} = y_{T+k - 7 \cdot \lceil k/7 \rceil}$$

#### 2. MovingAverage (DOW-Adjusted)
Extracts local baseline level $\bar{L}$ from the most recent 7 days, modulated by Day-Of-Week factors $\gamma_d$ computed over the prior 28 days ($N_{28} = 28$):
$$\bar{L} = \frac{1}{7} \sum_{i=0}^{6} y_{T-i}$$
$$\gamma_d = \frac{\frac{1}{|\mathcal{T}_d|} \sum_{t \in \mathcal{T}_d} y_t}{\frac{1}{28}\sum_{i=0}^{27} y_{T-i}}, \quad \mathcal{T}_d = \{ t \in [T-27, T] \mid \text{DOW}(t) = d \}$$
$$\hat{y}_{T+k} = \bar{L} \cdot \gamma_{\text{DOW}(T+k)}$$

#### 3. Damped Drift Model
Extrapolates linear trajectory from origin $y_1$ to current $y_T$, damping the slope $S$ to prevent runaway explosion:
$$S_{\text{raw}} = \frac{y_T - y_1}{T - 1}, \quad \bar{\mu} = \frac{1}{T}\sum_{t=1}^T y_t$$
$$S = \text{clip}\left(S_{\text{raw}}, -0.05\bar{\mu}, +0.05\bar{\mu}\right)$$
$$\hat{y}_{T+k} = \max\left(0, y_T + S \cdot k\right)$$

#### 4. Seasonal Model (Exponential Decomposition)
Decomposes series into 14-day smoothed level, global DOW seasonal coefficients, and a dampened trend multiplier from half-split ratio:
$$R_{\text{trend}} = \frac{\sum_{t=\lfloor T/2 \rfloor + 1}^T y_t}{\sum_{t=1}^{\lfloor T/2 \rfloor} y_t + \epsilon}, \qquad \hat{y}_{T+k} = \bar{L}_{14} \cdot \gamma_{\text{global, DOW}(T+k)} \cdot \left(R_{\text{trend}}\right)^{\frac{k}{2T}}$$

#### 5. Linear / Ridge Regression
Minimizes regularized $L_2$ loss on normalized time index $t$:
$$\min_{\mathbf{w}} \sum_{t=1}^T \left( y_t - (w_0 + w_1 t) \right)^2 + \alpha \|\mathbf{w}\|_2^2, \quad \alpha = 2.0$$

#### 6. SeasonalHoliday Model
Expands regression features with cyclically-encoded harmonic Day-Of-Week components and calendar holiday flags from `assets/reference/india_holidays.json`:
$$\mathbf{x}_t = \left[ t, \; \sin\left(\frac{2\pi \cdot \text{DOW}_t}{7}\right), \; \cos\left(\frac{2\pi \cdot \text{DOW}_t}{7}\right), \; \mathbb{I}_{\text{weekend}}(t), \; \mathbb{I}_{\text{holiday}}(t) \right]^T$$
$$\hat{y}_t = \mathbf{w}^T \mathbf{x}_t + w_0$$

#### 7. RidgeLags Model (Autoregressive ML)
Constructs a 13-dimensional supervised feature vector:
$$\mathbf{x}_t = \begin{bmatrix}
y_{t-1}, \; y_{t-7}, \; y_{t-14}, \; y_{t-28}, \\
\text{mean}(y_{t-6:t}), \; \text{mean}(y_{t-13:t}), \; \text{std}(y_{t-6:t}), \; \text{std}(y_{t-13:t}), \\
\sin\left(\frac{2\pi \cdot \text{DOW}_t}{7}\right), \; \cos\left(\frac{2\pi \cdot \text{DOW}_t}{7}\right), \; \sin\left(\frac{2\pi \cdot \text{Month}_t}{12}\right), \; \cos\left(\frac{2\pi \cdot \text{Month}_t}{12}\right), \\
\mathbb{I}_{\text{weekend}}(t), \; \mathbb{I}_{\text{holiday}}(t), \; t
\end{bmatrix}^T$$
* **Multi-step recursive inference**: When predicting step $k > 1$, missing lag values $y_{T+k-1}$ are dynamically substituted with model predictions from prior steps $\hat{y}_{T+k-1}$.

#### 8. HistGradientBoosting (HistGB)
Fits an ensemble of gradient-boosted decision trees using histogram binning over the 13 feature dimensions:
$$\hat{y}_t = \sum_{m=1}^{M} \eta f_m(\mathbf{x}_t), \quad M=120, \; \text{max\_depth}=4, \; \eta=0.06$$

#### 9. Ensemble Median Model
Combines predictions of all distinct non-ensemble candidate models:
$$\hat{y}_{T+k} = \text{median}\left( \hat{y}_{T+k}^{(\text{SeasonalNaive})}, \; \hat{y}_{T+k}^{(\text{MovingAverage})}, \; \hat{y}_{T+k}^{(\text{Drift})}, \; \dots \right)$$

---

### 7.3 Rolling-Origin Cross Validation & Baseline Gating

Model selection does not rely on a single static train/test split. It evaluates candidates across 4 rolling-origin temporal splits with a 14-day horizon and 7-day origin stride.

```
 Temporal Rolling-Origin Cross-Validation (4 Folds, 14-Day Horizon, 7-Day Step)
 ─────────────────────────────────────────────────────────────────────────────
 Fold 1: [========= Train Segment 1 =========] [== Holdout 1 ==]
 Fold 2: [============ Train Segment 2 ============] [== Holdout 2 ==]
 Fold 3: [=============== Train Segment 3 ===============] [== Holdout 3 ==]
 Fold 4: [================== Train Segment 4 ==================] [== Holdout 4 ==]
                                                                ▲
                                                           Origin Shifts
                                                           7 Days / Fold
```

#### The Beat-Baseline Gate
To prevent selecting overly complex ML models that overfit noise without providing actionable accuracy improvements, non-baseline models must satisfy:

$$\text{MASE}(M) \le \min\left( \text{MASE}(\text{SeasonalNaive}), \; \text{MASE}(\text{MovingAverage}) \right) - \epsilon_{\text{beat}}$$
$$\epsilon_{\text{beat}} = 0.0$$

If no ML candidate beats both baselines on cross-validated MASE, the engine automatically selects the best baseline.

---

### 7.4 Conformal Prediction Intervals

Rather than assuming Gaussian distributed residuals $\epsilon_t \sim \mathcal{N}(0, \sigma^2)$, the engine constructs non-parametric split-conformal prediction bands:

```
                            Split-Conformal Calibration
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                                                                             │
 │   1. Split Time Series: Train Set (Early History) + Calibration Set (Holdout)│
 │   2. Fit Selected Model on Train Set                                        │
 │   3. Compute Calibration Residuals:  r_i = | y_i - ŷ_i |                    │
 │   4. Compute Quantile Index:        q_idx = ceil( (n + 1) * (1 - α) ) / n   │
 │   5. Extract q_hat = Quantile( {r_i}, q_idx )                               │
 │                                                                             │
 │   Resulting 90% Conformal Band: [ max(0, ŷ_t - q_hat),  ŷ_t + q_hat ]       │
 │                                                                             │
 └─────────────────────────────────────────────────────────────────────────────┘
```

1. **Residual Calibration**: On calibration holdout of length $n$:
   $$r_i = \left| y_i - \hat{y}_i \right|, \quad i \in \{1, \dots, n\}$$
2. **Conformal Quantile Formulation** ($\alpha = 0.10 \implies 90\%$ Coverage):
   $$\hat{q} = \text{Quantile}\left( \{r_i\}_{i=1}^n, \; \frac{\lceil (n+1)(1-\alpha) \rceil}{n} \right)$$
3. **Forecast Envelope Generation**:
   $$\text{Lower}_{T+k} = \max\left(0, \; \hat{y}_{T+k} - \hat{q}\right), \qquad \text{Upper}_{T+k} = \hat{y}_{T+k} + \hat{q}$$

---

### 7.5 Unsupervised Anomaly Detection & Isolation Forests

District-level outlier detection executes across a composite key unit:
$$\text{Unit of Analysis} = \langle \text{State}, \text{District} \rangle$$

```
                           Feature Matrix Construction
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                                                                             │
 │   1. Log Volume:           ln(1 + total_volume)                             │
 │   2. Volatility (CV):      std(daily_volume) / (mean(daily_volume) + 1)     │
 │   3. Biometric Ratio:      bio_updates / (total_volume + 1)                 │
 │   4. Demographic Ratio:    demo_updates / (total_volume + 1)                │
 │   5. WoW Growth:           (mean_recent - mean_prior) / (mean_prior + 1)    │
 │   6. Active Footprint:     count(active_reporting_days)                     │
 │   7. State Peer Context:   total_volume / (median(state_volume) + 1)        │
 │                                                                             │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
                             StandardScaler Normalization
                                        │
                                        ▼
                           Isolation Forest (200 Trees)
                                        │
                                        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                                                                             │
 │   Anomaly Score s(x) ──► Invert & Min-Max Normalize ──► Risk Score [10, 100] │
 │   Z-Score Analysis   ──► Identify Max |z_j|         ──► Assign Top Driver   │
 │                                                                             │
 └─────────────────────────────────────────────────────────────────────────────┘
```

#### Feature Vector Formulation
For each district $j$, the feature vector $\mathbf{x}_j \in \mathbb{R}^7$ is defined by:
1. $\mathbf{x}_{j, 1} = \ln(1 + V_j)$ (Log total volume)
2. $\mathbf{x}_{j, 2} = \frac{\sigma_{\text{daily}, j}}{\mu_{\text{daily}, j} + 1}$ (Coefficient of Variation / day-to-day volatility)
3. $\mathbf{x}_{j, 3} = \frac{\text{BioUpdates}_j}{V_j + 1}$ (Biometric update ratio)
4. $\mathbf{x}_{j, 4} = \frac{\text{DemoUpdates}_j}{V_j + 1}$ (Demographic update ratio)
5. $\mathbf{x}_{j, 5} = \frac{\mu_{\text{recent 30d}, j} - \mu_{\text{prior 30d}, j}}{\mu_{\text{prior 30d}, j} + 1}$ (30-day velocity / WoW trend)
6. $\mathbf{x}_{j, 6} = \text{Count}(\text{Active Days}_j)$ (Operational continuity)
7. $\mathbf{x}_{j, 7} = \frac{V_j}{\text{Median}_{k \in \text{State}(j)}(V_k) + 1}$ (Volume vs state peer median)

#### Isolation Forest Score & Normalized Risk Metric
An ensemble of $B = 200$ isolation trees partitions standardized features $\mathbf{Z} = \text{StandardScaler}(\mathbf{X})$.
Let $h(\mathbf{z})$ be path length to isolate $\mathbf{z}$, and $c(n)$ be average path length of unsuccessful searches in a Binary Search Tree:
$$c(n) = 2\left(\ln(n - 1) + 0.5772156649\right) - \frac{2(n-1)}{n}$$
$$\text{Score}(\mathbf{z}) = 2^{-\frac{\mathbb{E}[h(\mathbf{z})]}{c(n)}}$$

Raw decision function values $\delta_j = \text{decision\_function}(\mathbf{z}_j)$ yield normalized risk scores:
$$\text{RiskScore}_j = \begin{cases}
\text{round}\left( \frac{-\delta_j - \min(-\boldsymbol{\delta})}{\max(-\boldsymbol{\delta}) - \min(-\boldsymbol{\delta}) + 10^{-9}} \times 90 + 10 \right), & \text{if flagged } (\delta_j < 0) \\
0, & \text{otherwise}
\end{cases}$$

#### Driver Attribution via Z-Score Decomposition
For every flagged outlier, the root driver is identified by finding the feature maximizing absolute standardized divergence:
$$k^* = \arg\max_{k \in \{1,\dots,7\}} \left| z_{j, k} \right|$$

---

### 7.6 Spatial Geometry, Scaling & Jitter Mathematics

District coordinates $(\text{lat}_j, \text{lon}_j)$ are retrieved from `assets/reference/district_centroids.json`. If unavailable, the engine falls back to state centroid coordinates with deterministic hash-based spatial jitter to avoid point superposition:

$$\text{hash\_val}(d, a) = \left| \text{Hash}\big(\text{str}(d) \,\|\, a\big) \right| \pmod{10000}$$
$$\text{jitter}(d, a) = \left( \frac{\text{hash\_val}(d, a)}{10000} \right) \cdot 0.30 - 0.15 \quad (\pm 0.15^\circ \text{ bounding circle})$$
$$\text{lat}_j = \text{lat}_{\text{state}} + \text{jitter}(\text{district}_j, 0), \qquad \text{lon}_j = \text{lon}_{\text{state}} + \text{jitter}(\text{district}_j, 1)$$

#### Volumetric 3D Elevation & Intensity Color Cut-Points
* **Logarithmic Normalized Elevation**:
  $$\text{norm}_j = \frac{\ln(1 + V_j) - \ln(1 + V_{\min})}{\ln(1 + V_{\max}) - \ln(1 + V_{\min}) + 0.1}, \qquad \text{Elevation}_j = \text{norm}_j \times 200{,}000\text{m}$$
* **Intensity Bands**:
  $$\text{Ratio}_j = \frac{V_j - V_{\min}}{V_{\max} - V_{\min} + 1}$$
  $$\text{Color}_j = \begin{cases}
  \text{Sky Blue } [14, 165, 233, 170], & \text{Ratio}_j < 0.10 \quad (\text{Low}) \\
  \text{Amber } [245, 158, 11, 190], & 0.10 \le \text{Ratio}_j < 0.30 \quad (\text{Medium}) \\
  \text{Deep Red } [220, 38, 38, 210], & \text{Ratio}_j \ge 0.30 \quad (\text{High})
  \end{cases}$$

---

### 7.7 Governance Fuzzy Matching & Sequence Matcher Ratios

To surface typographical corruptions and name anomalies, the governance engine executes Gestalt pattern matching (Ratcliff/Obershelp algorithm):

$$\text{Ratio}(s_1, s_2) = \frac{2 \cdot |\mathcal{K}_{\text{matching}}|}{|s_1| + |s_2|}$$

Where $|\mathcal{K}_{\text{matching}}|$ is the number of matching characters in matching substrings.
* **State Cutoff**: $0.40$ (lower threshold to capture severe truncations).
* **District Cutoff**: $0.85$ (strict threshold to avoid false-positive district collisions).
* **PIN Overlap Validation**: When pincode data exists, candidate district merges are validated by checking if the suspect district and target district share common pincodes:
  $$\text{PIN\_Overlap}(d_{\text{suspect}}, d_{\text{target}}) = \mathbb{I}\left( \text{PINs}(d_{\text{suspect}}) \cap \text{PINs}(d_{\text{target}}) \neq \emptyset \right)$$

---

## 8. Backend Engine Deep Dive

### 8.1 `DataLoader` (`src/data_manager.py`)
Responsible for reading raw CSVs or Parquet caches, applying cleaning, and building analytics frames.
* **Contract**: `get_data() -> Tuple[df_enrol, df_demo, df_bio, logs]`
* **Downcasting Routine**: Automatically converts floating columns to `float32` and integers to downsized integer representations, reducing RAM footprint by ~65%.

### 8.2 `AnalyticsEngine` (`src/ai_core.py`)
Encapsulates all analytical logic:
* `get_market_share()`: District-level volume breakdowns.
* `get_correlation()`: Multi-stream workload matrix (Enrolments vs Biometric vs Demographic).
* `get_anomalies(contamination, min_volume)`: Isolation Forest execution with caching to avoid re-training when parameters are unchanged.
* `forecast_trends(horizon, model_type, growth_factor, state)`: Forecast execution with rolling-origin CV bake-off and conformal bounds.
* `generate_*_insight()`: LLM-backed or deterministic markdown report generation.

### 8.3 `ForecastBackend` (`src/forecasting.py`)
A self-contained, 807-line forecasting engine:
* Enforces continuous calendar dates via `complete_daily_calendar()` (filling unobserved dates with $0$ to prevent distorting weekly seasonality).
* Implements the 9 candidate models, rolling CV, baseline gating, and split-conformal calibration.

---

## 9. Frontend Applications

### 9.1 Streamlit Analytics Console (`app.py`)
* **Target Audience**: Data scientists, researchers, and administrators performing deep exploratory investigations.
* **Theme**: Custom dark console (`src/utils/theme.py`) with Plotly contrast themes (`src/utils/plots.py`).
* **Navigation**: 5 full-featured views with sidebar state filters, date range bounds, and data quality inspector drawers.

```
 Streamlit App Navigation Structure
 ┌──────────────────────────────────────────────────────────┐
 │ Sidebar: State Multi-Select, Date Range, Quality Drawer │
 ├──────────────────────────────────────────────────────────┤
 │ Tab 1: Dashboard      ───► KPIs, Mixes, Risk Cells, Outlook
 │ Tab 2: Analytics      ───► Growth, Radar, Scatter, Watchlist
 │ Tab 3: Forecast       ───► Model Bake-Off, Point & Conformal
 │ Tab 4: Geospatial     ───► 2D / Heatmap / 3D Volumetric Maps
 │ Tab 5: Data Admin     ───► Discrepancy Scanners & Governance
 └──────────────────────────────────────────────────────────┘
```

### 9.2 React 18 + FastAPI Modern Operator App (`web/`)
* **Target Audience**: Field operations, regional directors, and executive dashboards.
* **Tech Stack**:
  - **Backend**: FastAPI (`web/api/main.py`) with full CORS support, streaming CSV exports, and Pydantic request models.
  - **Frontend**: React 18 + Vite SPA (`web/frontend/`).
  - **Visualizations**: Recharts (`AreaChart`, `BarChart`, `PieChart`, `RadarChart`, `ScatterChart`, `ComposedChart`) with PNG export capabilities.
  - **Geospatial**: Deck.gl vector layers with Carto Positron basemap (zero API key dependency).
  - **Icons**: Lucide-React.

---

## 10. Modules Breakdown

```
 Module Ecosystem Matrix
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                                                                             │
 │  src/modules/dashboard.py   ──► Executive KPIs, Age & Workload Mixes,       │
 │                                 Anomaly Bar Charts, 30-Day Outlook          │
 │                                                                             │
 │  src/modules/analytics.py   ──► Time Series Growth, State Polar Radars,     │
 │                                 District Anomaly Scatter, Watchlist         │
 │                                                                             │
 │  src/modules/predict.py     ──► Rolling-CV Model Comparison, Parameterized  │
 │                                 Forecast Curves, Staffing Requirements      │
 │                                                                             │
 │  src/modules/command.py     ──► 2D Scatter, Density Heatmaps, 3D Columns,   │
 │                                 Intensity Legend, View Depth Control        │
 │                                                                             │
 │  src/modules/data_admin.py  ──► String Distance Scanners, Human-in-the-Loop│
 │                                 Merge/Delete Actions, Durable Audits        │
 │                                                                             │
 └─────────────────────────────────────────────────────────────────────────────┘
```

1. **`dashboard.py`**:
   - Computes total national enrolments, adult enrolments, biometric updates, and demographic volume.
   - Age breakdown (0–5, 5–17, 18+) and operational workload mix (New vs Bio vs Demo).
   - Top-10 risk cells with Isolation Forest score visualizers.
   - Point forecast and P10–P90 conformal uncertainty envelope.

2. **`analytics.py`**:
   - National daily enrolment volume growth trajectory with zoomable area plots.
   - Polar risk radar plotting state-level max risk, mean risk, and flagged volume.
   - Low-volume district watchlist highlighting coverage blind spots.
   - One-click export for regional, trend, risk, and operational CSV packs.

3. **`predict.py`**:
   - Model bake-off table displaying cross-validated MASE, sMAPE, RMSE, and Bias across all candidates.
   - Interactive policy simulation via growth factor adjustment.
   - Operational resource planning calculator:
     $$\text{Operators Required} = \left\lceil \frac{\text{Peak Forecast Daily Volume}}{40 \text{ enrolments/operator/day}} \right\rceil$$

4. **`command.py`**:
   - Geospatial command center with 3 view modes: 2D Intensity, Density Heatmap, and 3D Volumetric Columns.
   - Configurable depth: "Top 5 Priority per State" vs "Show All Districts".
   - Scale options: Logarithmic (balanced dynamic range) vs Linear (true scale).

5. **`data_admin.py`**:
   - Discrepancy scanner for state and district anomalies.
   - Interactive merge, delete, and ignore workflows with durable persistence.

---

## 11. AI & Local LLM Integration

The engine features dual-mode operational narrative generation (`src/ai/ollama_client.py`, `src/ai/research_insights.py`).

```
                              Insight Generation Architecture
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                                                                             │
 │                         Structured Engine Evidence                          │
 │       (KPI metrics, anomaly drivers, bake-off scores, decision bands)       │
 │                                      │                                      │
 │                                      ▼                                      │
 │                     Ollama Health Probe (GET /api/tags)                     │
 │                                      │                                      │
 │                     ┌────────────────┴────────────────┐                     │
 │                     ▼                                 ▼                     │
 │             [ LLM Connected ]                [ LLM Offline ]                │
 │                     │                                 │                     │
 │                     ▼                                 ▼                     │
 │         Local Ollama HTTP Call            Deterministic Rule-Based          │
 │         Model: qwen2.5:latest             Statistical Template Engine       │
 │         Strip Chain-of-Thought Tags       (Zero Network Dependency)         │
 │                     │                                 │                     │
 │                     └────────────────┬────────────────┘                     │
 │                                      │                                      │
 │                                      ▼                                      │
 │                     Rendered Markdown Operational Brief                     │
 │                                                                             │
 └─────────────────────────────────────────────────────────────────────────────┘
```

* **Local Ollama Integration**: Connects via HTTP to `http://127.0.0.1:11434` running `qwen2.5:latest` (or user-defined `OLLAMA_MODEL`).
* **Deterministic Fallback**: If Ollama is unavailable, the engine uses template-based statistical synthesis from raw engine metrics. No external cloud dependencies or API keys are required.
* **Noise Filter**: Automatically strips reasoning artifacts (`<think>...</think>`, markdown code delimiters) emitted by deep-thinking local LLMs.

---

## 12. Data Governance & Durable Patching

Administrative renames, spelling merges, and exclusions applied in the Governance UI persist durably in `output/` and are automatically hot-reloaded into memory across sessions.

```
 Data Governance Persistence & Reversion Loop
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                                                                             │
 │   1. Automated Fuzzy Scanner identifies spelling discrepancies              │
 │   2. Operator reviews match confidence & PIN overlap in UI                  │
 │   3. Action chosen: MERGE (rename) or DELETE (exclude)                      │
 │   4. Saved to output/governance_patches.json                                │
 │   5. Audit event appended to output/governance_audit.csv                    │
 │   6. DataLoader applies patches dynamically on next query                   │
 │   7. One-click Revert restores original state by Audit UUID                 │
 │                                                                             │
 └─────────────────────────────────────────────────────────────────────────────┘
```

### Storage Files
1. **`output/governance_patches.json`**:
   ```json
   {
     "state_patches": {},
     "district_patches": {
       "Bangalore": "Bengaluru Urban",
       "Gurgaon": "Gurugram"
     },
     "state_deletions": [],
     "district_deletions": []
   }
   ```
2. **`output/governance_audit.csv`**:
   Contains complete historical provenance with columns:
   ```csv
   ID,Timestamp,Scope,Action,Original,Target,User
   ```

---

## 13. Reference Knowledge Assets & Rule Packs

All static rule dictionaries live in `assets/reference/`:

| File Name | Entries | Purpose |
| :--- | :--- | :--- |
| `official_states.json` | 36 States/UTs | Authoritative whitelist of Indian States and Union Territories |
| `state_aliases.json` | 27 Mappings | Normalizes historical/noisy state spellings |
| `district_aliases.json` | 42 Mappings | Resolves major municipal spelling variations |
| `district_as_state.json` | 8 Seed Rules | Inverts misplaced district tokens in state fields |
| `telangana_districts.json` | 43 Districts | Reassigns pre-2014 bifurcated districts from AP to Telangana |
| `pin_prefix_states.json` | 65 Prefix Rules| Maps 2-digit PIN prefixes to postal circle States/UTs |
| `district_centroids.json` | 52 Centroids | WGS84 coordinates for major district administrative centers |
| `eval_geo_gold.json` | 19 Test Cases | Validation gold standard for cleaning evaluation |
| `rules_manifest.json` | Rule Pack Metadata| Tracks active rule pack version (`1.1.0`) and schema version (`4`) |
| `india_holidays.json` | ~30 Dates | National fixed and floating public holidays for forecasting features |

---

## 14. Configuration Matrix & Runtime Parameters

Central configuration is defined in `src/config.py`:

```python
# System Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = ROOT_DIR / "output"

# Versions & Fingerprints
CACHE_SCHEMA_VERSION = 4
GEO_RULE_PACK_VERSION = "1.1.0"

# Natural Keys
NATURAL_KEY = ["date", "state", "district", "pincode"]
DAILY_KEY = ["date", "state", "district"]

# Postal Validation Bounds
PINCODE_MIN = 100000
PINCODE_MAX = 999999

# Anomaly Defaults
ANOMALY_CONTAMINATION = 0.05
ANOMALY_MIN_VOLUME = 50

# Forecast Engine Parameters
FORECAST_RANDOM_SEED = 42
FORECAST_CANDIDATES = ("MovingAverage", "Drift", "Ensemble", "SeasonalNaive")
FORECAST_HOLDOUT_DAYS = 14
FORECAST_ROLLING_FOLDS = 4
FORECAST_ROLLING_STEP = 7
FORECAST_MIN_TRAIN_DAYS = 40
FORECAST_MAX_HISTORY_DAYS = 400
FORECAST_PRIMARY_METRIC = "mase"
FORECAST_BEAT_BASELINE_EPS = 0.0
FORECAST_CONFORMAL_ALPHA = 0.10
FORECAST_FILL_MISSING_DAYS = True

# Operational Decision Thresholds
FORECAST_MASE_THRESHOLDS = {"tight": 0.85, "directional": 1.15}
FORECAST_SMAPE_THRESHOLDS = {"tight": 20.0, "directional": 40.0}
```

---

## 15. Verification, Quality Assurance & Deployment

### 15.1 Test Suite (`tests/`)
* **`test_forecast.py`**: Verifies metrics (MAPE, sMAPE, RMSE, MASE), continuous calendar filling, rolling-origin cross-validation folds, baseline gating logic, and conformal prediction coverage.
* **`test_geo_repair.py`**: Validates the 5-stage cleaning pipeline against `eval_geo_gold.json`, ensuring $\ge 90\%$ accuracy.
* **`test_pin_and_manifest.py`**: Tests SHA-256 fingerprint generation, cache invalidation, and PIN prefix mapping.

Run test suite:
```bash
python -m pytest tests/ -v
```

### 15.2 Production Launch Commands

```bash
# 1. Rebuild Parquet Marts Cache (Forced ETL)
python -m src.etl.build_cache --force

# 2. Launch Streamlit Analytics Console (Port 8501)
python main.py
# or: streamlit run app.py

# 3. Launch React 18 + FastAPI Production App (Port 8787)
python run_web.py

# 4. Run Headless / Marts-Only Mode (Zero CSV parsing)
set MARTS_ONLY=1
python run_web.py
```

### 15.3 Containerized Deployment (`Dockerfile`)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501 8787
CMD ["python", "main.py"]
```

---

*Authored by the Aadhaar Intel Engine Technical Team. All mathematical formulations, schemas, and pipeline architectures documented above reflect the active production codebase.*
