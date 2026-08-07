# Professional Web UI

Clean React + FastAPI presentation of the **same** analytics engine as Streamlit.

## Run (recommended)

From repo root:

```bash
python run_web.py
```

Opens http://127.0.0.1:8787

## Stack

| Layer | Tech |
|-------|------|
| UI | React 18, Vite, Recharts, Leaflet, React Router |
| API | FastAPI (Python) |
| Engine | `src.ai_core.AnalyticsEngine`, marts, geo, governance |

Streamlit remains available via `streamlit run app.py`.
