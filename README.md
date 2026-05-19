# Disaster Relief Response Gap Tracker (DRRGT)

> **How long does FEMA aid actually take to reach communities — and who gets left waiting the longest?**

DRRGT ingests 810,000+ records from the FEMA Open API and U.S. Census ACS, then quantifies the gap between disaster declarations and first disbursements across every U.S. county. Statistical analysis surfaces whether delays are systematically worse in lower-income, rural, or historically underserved areas — and a full AWS production deployment puts the findings online 24/7.

---

## Contents

- [What This Project Does](#what-this-project-does)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Analytics Methodology](#analytics-methodology)
- [API Reference](#api-reference)
- [Quick Start (Local)](#quick-start-local)
- [Project Layout](#project-layout)
- [Running Tests](#running-tests)
- [AWS Deployment](#aws-deployment)
- [CI/CD Pipeline](#cicd-pipeline)
- [Known Limitations](#known-limitations)

---

## What This Project Does

**Core metric:** `response_gap_days = first_disbursement_date − declaration_date` per county per disaster. Across 3,200+ counties and hundreds of declared disasters, this reveals which communities wait weeks vs. months for federal relief.

**Why it matters:** A 30-day gap in a low-income rural county has a very different impact than the same gap in a high-income urban one. DRRGT makes that disparity quantifiable.

**Key findings the system surfaces:**
- Spearman ρ between median household income and response gap (log-transformed, winsorized at [2nd, 98th] percentile to remove multi-year infrastructure outliers)
- Mann-Whitney U test comparing rural vs. urban gap distributions
- Income quintile breakdown: whether the bottom 20% of counties by income wait disproportionately longer
- Disaster-type stratification: hurricane response vs. severe storm response shows very different baseline gaps
- FEMA region equity: some regional offices process paperwork faster regardless of county demographics
- Composite underserved score: `0.50×z(gap) + 0.30×z(−income) + 0.20×rural` to surface triple-disadvantaged counties
- Ridge regression on log(gap) controlling for income, rurality, and all 10 FEMA administrative regions

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API** | FastAPI, Python 3.12 |
| **Database** | PostgreSQL 16 (Amazon RDS in production) |
| **Cache** | Redis 7 (Amazon ElastiCache) |
| **Task Queue** | Celery 5 + Celery Beat |
| **Analytics** | pandas, NumPy, SciPy, scikit-learn |
| **Frontend** | React, Vite, Tailwind CSS, Recharts |
| **Infrastructure** | Terraform, AWS ECS Fargate, ALB, S3, ECR, CloudWatch |
| **CI/CD** | GitHub Actions |
| **Observability** | Structured JSON logging → CloudWatch Logs Insights |

---

## Architecture

```
┌──────────────────┐  paginated   ┌─────────────────────┐   S3 raw archive
│  FEMA Open API   │─────────────▶│                     │──────────────────▶ s3://raw-bucket/
│  Census ACS 2022 │              │   Celery Worker     │                    fema/<endpoint>/
└──────────────────┘              │   ETL Pipeline      │                    YYYY-MM-DD/raw.json.gz
                                  │                     │
                                  │  upsert counties    │
                                  │  upsert disasters   │   ┌──────────────────────┐
                                  │  load disbursements │──▶│  PostgreSQL (RDS)    │
                                  │  compute metrics    │   │                      │
                                  └─────────────────────┘   │  counties            │
                                         │                   │  disasters           │
                                  cache invalidation         │  disbursements       │
                                         │                   │  metrics             │
                                         ▼                   └──────────┬───────────┘
                                  ┌─────────────┐                       │
                                  │    Redis    │◀──────────────────────┤
                                  │ (versioned) │    cache get/set      │
                                  └─────────────┘                       │
                                         ▲                   ┌──────────▼───────────┐
                                         │                   │    FastAPI           │
                                  ┌──────┴──────┐            │                      │
                                  │  React SPA  │◀───────────│  /correlations       │
                                  │  (6 tabs)   │   JSON     │  /analytics/*        │
                                  └─────────────┘            │  /metrics            │
                                                             │  /health/deep        │
                                                             └──────────────────────┘
                                                                        ▲
                                                             ┌──────────┴───────────┐
                                                             │  ALB (port 80/443)   │
                                                             │  /health/deep probe  │
                                                             └──────────────────────┘
```

**Ingestion** handles FEMA v2 API pagination (`$top`/`$skip`) with exponential backoff and 3 retries. Every successful API response is gzip-compressed and written to S3 before transformation — so if the pipeline logic has a bug, raw data can be reprocessed without re-hitting rate-limited APIs.

**ETL optimisations:** `upsert_counties` and `upsert_disasters` use a single PostgreSQL `INSERT … ON CONFLICT DO UPDATE` (cutting ~3,200 round-trips down to 1). Disbursements are cleared and reloaded per run with 5,000-row flush batches. All four tables have composite indexes tuned to the analytics queries.

**Caching:** All analytics endpoints are cached in Redis with versioned keys (`key:v1`). Bumping `cache_version` in settings invalidates everything without a manual flush. The ETL worker calls `invalidate_analytics()` at the end of each run so the next HTTP request recomputes from fresh data.

**Observability:** Every log line is JSON-formatted with a `ctx_` field convention compatible with CloudWatch Logs Insights. Three CloudWatch alarms (ETL error spike, API p99 latency, API 5xx rate) fire to an SNS topic — subscribe an email address via `var.alert_email` in Terraform.

---

## Analytics Methodology

### Why not just Pearson r?

The initial correlation between median household income and response gap was r ≈ 0.16 — statistically weak and potentially misleading. Four issues were identified and addressed:

1. **Right-skewed income distribution** — raw Pearson on income amplifies the influence of the top 1% of counties. Fix: log-transform income before computing Pearson.
2. **Multi-year PA infrastructure outliers** — some FEMA Public Assistance projects span multiple years, producing gaps >730 days that aren't comparable to direct aid. Fix: filter to `response_gap_days ∈ [0, 730]` and winsorize at [2nd, 98th] percentile.
3. **Disaster type as dominant confounder** — hurricanes trigger federal mobilisation regardless of county income. Without stratifying, the income signal is suppressed. Fix: `disaster_type_analysis` endpoint stratifies by `incident_type`.
4. **State-level effects** — some FEMA regional offices are faster regardless of local demographics. Fix: Ridge regression includes region dummies; `regional_equity_analysis` surfaces region-level averages.

### Endpoints and methods

| Endpoint | Method | What it measures |
|---|---|---|
| `GET /correlations` | Spearman ρ + log-Pearson r + Mann-Whitney U | Overall income↔gap relationship |
| `GET /analytics/quintiles` | `pd.qcut` into 5 income buckets | Distributional shape (not just one number) |
| `GET /analytics/disaster-types` | GROUP BY incident_type | Disaster type as confounder |
| `GET /analytics/regional` | Weighted avg by FEMA region 1–10 | Regional office effects |
| `GET /analytics/underserved` | Composite z-score | Triple-disadvantaged counties |
| `GET /analytics/trends` | `PERCENTILE_CONT` year-by-year | Whether the gap is improving over time |
| `GET /analytics/model` | Ridge(α=1.0) on log(gap) | Multivariable decomposition |

---

## API Reference

Base URL: `http://localhost:8000` (local) or the ALB DNS from `terraform output alb_dns_name`.

### Core endpoints

| Method | Endpoint | Params | Description |
|---|---|---|---|
| `GET` | `/health` | — | Shallow liveness probe |
| `GET` | `/health/deep` | — | DB + Redis readiness (used by ALB) |
| `GET` | `/metrics` | `state`, `min_gap`, `limit`, `offset` | Joined metrics + county data, paginated |
| `GET` | `/counties` | `search`, `state`, `limit` | County lookup and search |
| `GET` | `/correlations` | — | Spearman ρ, Pearson r, Mann-Whitney U |
| `GET` | `/timeseries` | — | Yearly average response gap |
| `GET` | `/outliers` | `top` | Worst N response gaps |
| `GET` | `/insights` | — | Auto-generated narrative summary |

### Analytics endpoints

| Method | Endpoint | Params | Description |
|---|---|---|---|
| `GET` | `/analytics/quintiles` | — | Median gap per income quintile |
| `GET` | `/analytics/disaster-types` | — | Gap by FEMA incident type |
| `GET` | `/analytics/regional` | — | Gap and income by FEMA region 1–10 |
| `GET` | `/analytics/underserved` | `top` (default 25) | Composite underserved score ranking |
| `GET` | `/analytics/trends` | — | Year-over-year median gap, rural vs urban |
| `GET` | `/analytics/model` | — | Ridge regression coefficients and R² |

Full interactive docs at `/docs` (Swagger UI) and `/redoc`.

---

## Quick Start (Local)

**Prerequisites:** Docker and Docker Compose.

```bash
# 1. Clone and configure
git clone https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT- drrgt
cd drrgt
cp .env.example .env        # optionally add CENSUS_API_KEY

# 2. Start all services (API, worker, Postgres, Redis)
docker compose up --build

# 3. Seed the database (in a second terminal)
docker compose exec api python -m app.etl.seed
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:5173 |
| API docs (Swagger) | http://localhost:8000/docs |
| Shallow health | http://localhost:8000/health |
| Deep health | http://localhost:8000/health/deep |

To run the full ETL against live FEMA and Census APIs:

```bash
docker compose exec api python -m app.etl.pipeline
```

The API falls back to `data/sample/*.json` fixtures automatically when live APIs are unreachable, so the dashboard is always demoable.

---

## Project Layout

```
drrgt/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, all endpoints, timing middleware
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic settings (env vars)
│   │   │   ├── database.py      # SQLAlchemy engine + session (connection pool)
│   │   │   └── logging.py       # JSON formatter for CloudWatch Logs Insights
│   │   ├── models/db.py         # SQLAlchemy ORM models + composite indexes
│   │   ├── etl/
│   │   │   ├── ingest.py        # FEMA + Census API clients, S3 archival
│   │   │   ├── pipeline.py      # Upsert → compute → cache-invalidate
│   │   │   └── seed.py          # Local dev seed data
│   │   ├── services/
│   │   │   ├── analysis.py      # All statistical and ML functions
│   │   │   └── cache.py         # Redis helpers with versioned keys
│   │   └── worker/
│   │       ├── celery_app.py    # Celery config (acks_late, retry)
│   │       └── tasks.py         # Scheduled ETL task
│   ├── tests/                   # pytest — SQLite-based, no live infra needed
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                    # React + Vite + Tailwind + Recharts
├── data/sample/                 # Fallback JSON fixtures
├── infra/
│   └── main.tf                  # Full AWS stack: ECS, RDS, Redis, S3, ECR, ALB, CloudWatch
├── .github/
│   └── workflows/ci.yml         # Test → build → push → ECS rolling deploy
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## Running Tests

```bash
cd backend
pytest -q
```

Tests use SQLite in-memory — no Docker or live APIs required. The PostgreSQL-specific `INSERT ON CONFLICT` upsert functions are intentionally bypassed in tests; ORM objects are inserted directly.

---

## AWS Deployment

### Infrastructure (one-time)

```bash
cd infra
terraform init
terraform apply \
  -var db_password=<strong-password> \
  -var alert_email=you@example.com   # optional — leave empty to skip SNS email sub
```

Terraform provisions:
- **ECS Fargate** — two services: `api` (512 CPU / 1024 MB) and `worker` (1024 CPU / 2048 MB)
- **ALB** — HTTP listener, target group health-checked on `/health/deep` with 30-second deregistration drain
- **RDS PostgreSQL 16** — `db.t3.micro`, encrypted at rest
- **ElastiCache Redis 7** — `cache.t3.micro`
- **S3** — raw data landing zone with SSE-AES256; objects transition to STANDARD_IA at 30 days and expire at 365 days
- **ECR** — lifecycle policy keeps the last 10 images
- **CloudWatch** — log groups (14-day retention), metric filters (ETL errors, API 5xx), three alarms wired to SNS
- **App autoscaling** — ECS API service scales 1→4 tasks at 70% average CPU

```bash
# View all outputs
terraform output
```

### Secrets

Inject `DATABASE_URL`, `REDIS_URL`, and `CENSUS_API_KEY` as ECS task environment variables or via AWS Secrets Manager. Never commit `.env` files.

---

## CI/CD Pipeline

`.github/workflows/ci.yml` runs on every push to `main`:

1. **Test** — `pytest` against SQLite (no external services)
2. **Frontend build** — `npm run build` to catch JS compilation errors
3. **Deploy** (main branch only):
   - Authenticate to ECR
   - `docker build` and push with the commit SHA as the image tag
   - For each service (API, Worker): fetch current task definition → patch the container image → register new revision → `aws ecs update-service`
   - `aws ecs wait services-stable` confirms the API service is healthy before the job exits

The ECS services use `lifecycle { ignore_changes = [task_definition] }` in Terraform so `terraform apply` never rolls back a CI-deployed image.

**Required GitHub secrets:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `ECR_REGISTRY`, `ECS_CLUSTER`, `ECS_SERVICE_API`, `ECS_SERVICE_WORKER`, `TASK_DEF_API`, `TASK_DEF_WORKER`.

---

## Known Limitations

- **Map tab** renders a state-level bar chart. A true county-level choropleth would require `us-atlas/counties-10m.json` rendered with `react-simple-maps` keyed by FIPS.
- **Rural flag** is a population-based proxy (< 50,000). USDA Rural-Urban Continuum Codes (RUCC) would be more accurate.
- **`temporal_trends`** uses `PERCENTILE_CONT` which is PostgreSQL-only and is not covered by the SQLite unit tests.
- **`/analytics/model`** recomputes the Ridge regression on every cache miss (~100ms). A background job that persists the fitted model would be faster at scale.
- FEMA `PublicAssistanceFundedProjectsDetails` covers infrastructure aid. Individual Assistance (`IndividualsAndHouseholdsProgramValidRegistrations`) would give a fuller picture of household-level delays.

---

## License

MIT — see `LICENSE`.
