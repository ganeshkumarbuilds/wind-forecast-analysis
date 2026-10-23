# WindScope

WindScope is a UK wind-generation forecast analysis dashboard for reviewing historical Elexon WINDFOR forecast publications in the context of explicitly supplied purchasing decision cutoffs and FUELHH actual wind generation.

> **Assessment status:** The application retrieves and validates records and selects eligible forecasts. It does **not** calculate real-data forecast accuracy. Accuracy metrics remain blocked because authoritative WINDFOR generation units and interval semantics, and an approved comparison method, have not been verified.

## Problem and intended users

Energy purchasers and analysts need to understand what wind-generation forecast information was available at a decision time and how it relates to delivered generation. WindScope is an assessment prototype for examining that question using only Elexon's FUELHH and WINDFOR datasets. The backend preserves forecast publication history and applies explicit cutoffs to avoid using forecasts published after the decision.

The January 2026 decision period is a **decision cohort**, not a delivery-date filter. A decision made on 31 January may concern a February delivery interval. The analysis request therefore keeps decision dates, forecast publication bounds, delivery-start bounds, and FUELHH settlement-date bounds separate.

## Implemented features

- Responsive React dashboard with API health state, date/time inputs, loading/error/empty states, selected forecast display, and data-quality counts.
- `GET /api/v1/health`, which reports that the API process is running; it does not assert Elexon availability.
- `POST /api/v1/analysis`, which retrieves FUELHH WIND and WINDFOR records, validates timestamped records, and applies explicit forecast publication cutoffs.
- UTC normalization for comparisons while retaining original WINDFOR timestamps for traceability.
- Rejection and duplicate reporting in backend data-processing services, and explicit ambiguous-selection reporting for conflicting forecast duplicates.
- A standalone metrics service for explicitly aligned, verified numeric observation pairs. The analysis API does not call it for Elexon records while comparability is unverified.
- Docker Compose configuration for a backend and a production-built frontend served by Nginx.

## Architecture and technology

- **Frontend:** React, TypeScript, Vite, Vitest, and React Testing Library. Production assets are served by unprivileged Nginx.
- **Backend:** Python, FastAPI, Pydantic, Uvicorn, HTTPX, Pandas, and pytest.
- **Upstream data:** Official Elexon BMRS FUELHH and WINDFOR stream endpoints. No database, credentials, or other data source is currently used.
- **Container routing:** Nginx proxies same-origin `/api/...` browser requests to the Compose backend service.

## Project structure

```text
.
├── API_INVESTIGATION.md          # Elexon API evidence and unresolved data questions
├── DOCKER.md                     # Container build/run operations and proxy details
├── README.md
├── compose.yaml                  # Backend and frontend services
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py               # FastAPI app, error handlers, router registration
│   │   ├── api/
│   │   │   ├── analysis.py       # Versioned analysis route
│   │   │   └── health.py         # Health route
│   │   ├── schemas/
│   │   │   ├── analysis.py       # Analysis request/response models
│   │   │   └── errors.py         # Structured API error response
│   │   └── services/
│   │       ├── elexon_client.py  # HTTPX access to the two Elexon datasets
│   │       ├── data_processing.py # Validation, UTC timestamps, quality reports
│   │       ├── forecast_selection.py # Latest eligible forecast selection
│   │       ├── analysis.py       # Retrieval and blocked-metrics orchestration
│   │       └── metrics.py        # Metrics for explicit aligned pairs only
│   └── tests/                    # Backend service and API tests
└── frontend/
    ├── Dockerfile
    ├── nginx.conf                # Production SPA serving and /api reverse proxy
    ├── package.json
    ├── package-lock.json
    └── src/
        ├── App.tsx               # Dashboard and request form
        ├── api.ts                # Health and analysis API client/types
        ├── styles.css
        └── *.test.*              # Frontend tests
```

## Prerequisites

- Docker Desktop with its Linux container engine and Docker Compose.
- For local development without containers: Python 3.14 (matches the current backend image), Node.js 20.19+ or 22.12+, and npm. These Node.js minimums satisfy the installed Vite 7 runtime requirement.

## Run with Docker Compose

Run these commands from the project root in PowerShell:

```powershell
docker compose config
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-WebRequest http://localhost:8080/ -UseBasicParsing
```

Open the dashboard at **http://localhost:8080**. The API health endpoint is available directly at **http://localhost:8000/api/v1/health**. To also verify the Nginx API proxy, request:

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/health
```

View logs and stop/remove the containers and Compose network:

```powershell
docker compose logs -f
docker compose down
```

Rebuild after source or configuration changes:

```powershell
docker compose up --build -d
```

More operational notes are in [DOCKER.md](./DOCKER.md).

## Local development

### Backend

In a PowerShell terminal from the project root:

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

The API runs at **http://localhost:8000**. Its health route is **http://localhost:8000/api/v1/health**.

### Frontend

In a second PowerShell terminal from the project root:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Vite prints the local dashboard URL (normally **http://localhost:5173**). Its `/api` development proxy forwards requests to `http://localhost:8000`.

## API

### `GET /api/v1/health`

Returns `{"status":"ok"}` when the FastAPI process responds. This is not a check of Elexon connectivity, data completeness, or forecast accuracy.

### `POST /api/v1/analysis`

Accepts a JSON body with the following fields. Date values use `YYYY-MM-DD`; timestamp values must include a timezone offset (UTC `Z` is recommended).

| Field | Type | Meaning |
| --- | --- | --- |
| `decision_period_start` | date | Start of decision-date cohort; constrained to January 2026 |
| `decision_period_end` | date | End of decision-date cohort; constrained to January 2026 |
| `decision_cutoffs` | non-empty array | Explicit decision contexts, each containing `decision_date` (date within the period) and timezone-aware `cutoff` |
| `delivery_start_from` | timezone-aware timestamp | Inclusive lower bound for delivery interval starts |
| `delivery_start_to` | timezone-aware timestamp | Exclusive upper bound for delivery interval starts; must be later than `delivery_start_from` |
| `delivery_settlement_date_from` | date | Lower bound of FUELHH settlement-date query |
| `delivery_settlement_date_to` | date | Upper bound of FUELHH settlement-date query; must not be before the lower bound |
| `forecast_publish_from` | timezone-aware timestamp | Lower bound for WINDFOR publication query |
| `forecast_publish_to` | timezone-aware timestamp | Upper bound for WINDFOR publication query; must not be before the lower bound |

Example request:

```json
{
  "decision_period_start": "2026-01-01",
  "decision_period_end": "2026-01-31",
  "decision_cutoffs": [
    {
      "decision_date": "2026-01-31",
      "cutoff": "2026-01-31T22:00:00Z"
    }
  ],
  "delivery_start_from": "2026-02-01T00:00:00Z",
  "delivery_start_to": "2026-02-02T00:00:00Z",
  "delivery_settlement_date_from": "2026-02-01",
  "delivery_settlement_date_to": "2026-02-01",
  "forecast_publish_from": "2026-01-01T00:00:00Z",
  "forecast_publish_to": "2026-02-01T00:00:00Z"
}
```

The cutoff above is an example request value, **not** a verified business rule. The request provides one cutoff context; the service does not infer cutoff times for every day in the decision period.

The response has `status: "metrics_blocked"`, `metrics_status: "comparability_unverified"`, and `metrics: null`. It includes `metrics_block_reason`, `missing_verification_requirements`, `data_quality` counts, and `selected_forecasts`. A forecast selection includes the decision date, delivery interval, original and normalized publication/delivery timestamps, selection cutoff, status, rationale, eligible-record count, and duplicate information. API errors use a structured `code` and `message`; validation errors may also include `details`. See the Pydantic models in `backend/app/schemas/analysis.py`.

The analysis service selects only forecasts with a publication timestamp **strictly earlier than** the supplied cutoff; a record published exactly at the cutoff is excluded. The January decision period is independent of delivery dates, so February delivery intervals can be selected for January decisions when included in the explicit delivery and actual-settlement ranges.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `FRONTEND_PORT` | `8080` | Host port for the dashboard container |
| `BACKEND_PORT` | `8000` | Host port for direct API access |
| `VITE_API_BASE_URL` | Empty | Optional Vite build-time absolute API base URL. Leave blank for the local Vite proxy or production same-origin Nginx `/api/` proxy. This value becomes public frontend configuration and must not contain secrets. |

Compose port variables can be set in the shell or a local root `.env` file; do not commit private `.env` files. A frontend `.env.example` is provided. The backend currently has no application-level environment variables or Elexon credentials.

## Tests and checks

Run from the project root:

```powershell
Set-Location backend
python -m pytest
python -m pip check

Set-Location ..\frontend
npm ci
npm test
npm run build

Set-Location ..
docker compose config
```

Most recently verified in the development environment: backend **106 passed**, `pip check` **no broken requirements**, frontend **5 passed**, frontend production build **passed**, and `docker compose config` **passed**. These are local verification results, not a claim about a deployed environment.

## Limitations and unresolved questions

- **No real-data forecast accuracy is calculated or displayed.** Metrics remain blocked pending authoritative verification of WINDFOR units, the meaning and duration represented by its `startTime`/`generation`, and approval of a comparison grain and alignment method with FUELHH.
- FUELHH is documented by Elexon as average MW over 30 minutes. The inspected WINDFOR schema identifies `generation` as a nullable integer but does not establish its unit or interval semantics. See [API_INVESTIGATION.md](./API_INVESTIGATION.md).
- Elexon has not established the applicable purchasing decision cutoff for this assignment. Callers must supply explicit timezone-aware cutoff values; the example above is illustrative only.
- Historical WINDFOR retrieval is filtered by publication time, not delivery start time. API retrieval failures, incomplete historical coverage, rate limiting, and lack of persistent caching remain operational considerations.
- The app does not align/resample/aggregate forecast and actual intervals and does not claim that they are directly comparable.
- There is no public deployment yet. **Deployment URL: not available (not deployed).**
- No `LICENSE` file is present. Choose and add a license before publication if you intend to grant reuse permissions; do not assume a public GitHub repository automatically grants rights to reuse the project.

## AI-tools disclosure

GitHub Copilot and ChatGPT were used as AI-assisted development tools during this project. Their suggestions were reviewed against the implementation, documentation, and test results. The tools are not project authors or sources of verified Elexon data.
