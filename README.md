# Disaster Relief Response Gap Tracker (DRRGT)

> **How long does FEMA aid actually take to reach communities — and who gets left waiting the longest?**

DRRGT ingests 810,000+ records from the FEMA Open API and U.S. Census ACS, then quantifies the gap between disaster declarations and first disbursements across every U.S. county. Statistical analysis surfaces whether delays are systematically worse in lower-income, rural, or historically underserved areas — backed by a full AWS production deployment on ECS Fargate.

---

## Contents

- [What This Project Does](#what-this-project-does)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Design Decisions](#design-decisions)
- [Benchmarks](#benchmarks)
- [Analytics Methodology](#analytics-methodology)
- [API Reference](#api-reference)
- [Quick Start (Local)](#quick-start-local)
- [Project Layout](#project-layout)
- [Running Tests](#running-tests)
- [AWS Deployment](#aws-deployment)
- [CI/CD Pipeline](#cicd-pipeline)
- [Open Issues](#open-issues)
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

---

## Design Decisions

These are the non-obvious choices and why they were made.

**Redis caches only aggregate analytics endpoints, not raw query results.**
The `/metrics` and `/counties` endpoints are paginated and filtered — caching every parameter combination would consume unbounded memory. Only the expensive aggregate endpoints (`/correlations`, `/analytics/*`, etc.) are cached, because they run over the full dataset and their inputs don't vary. Underlying data changes at most once per day (ETL run), so a 1-hour TTL is conservative; the ETL explicitly calls `invalidate_analytics()` on completion anyway, so fresh data is never served stale. (See [issue #1](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/1) for the bug this fixed.)

**Versioned cache keys (`key:v1`) instead of explicit flushes.**
Bumping `cache_version` in settings atomically invalidates every cached key across all API instances without needing a `FLUSHDB` call (which would wipe keys mid-request under traffic). During a rolling deploy, the old instance reads `correlations:v1` and the new instance writes `correlations:v2` — no race condition.

**Single `INSERT … ON CONFLICT DO UPDATE` for county and disaster upserts.**
The original code called `db.merge()` in a loop — one SQL round-trip per row. With 3,247 counties this was ~4.8s of unnecessary latency. A single PostgreSQL `pg_insert` with `ON CONFLICT DO UPDATE` collapses this to one query regardless of dataset size. This is PostgreSQL-specific; tests bypass these functions and seed ORM objects directly so SQLite test compatibility is preserved. (See [issue #2](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/2).)

**S3 raw archive before transformation.**
Raw API responses are gzip-compressed and written to S3 before any transformation logic runs. If a pipeline bug corrupts the database, the source data can be replayed from S3 without re-hitting FEMA's rate-limited API. Storage cost is negligible: ~2MB/day gzipped.

**ECS Fargate split: API (512 CPU / 1024 MB) vs Worker (1024 CPU / 2048 MB).**
The API is I/O-bound and benefits from horizontal scaling (autoscaling to 4 tasks at 70% CPU). The ETL worker is memory-bound during the 810k-row disbursement load and needs 2x the RAM to avoid OOM kills during the `bulk_save_objects` batching loop. Keeping them as separate ECS services means a slow ETL run doesn't starve the API of CPU.

**Connection pool sized for Fargate 512-CPU task.**
`pool_size=5, max_overflow=10` — a maximum of 15 simultaneous connections per API task. With up to 4 API tasks autoscaling + 1 worker, peak connections stay under 65, well within RDS `db.t3.micro`'s 80-connection limit.

**`lifecycle { ignore_changes = [task_definition] }` in Terraform.**
Without this, running `terraform apply` after a CI/CD deploy would roll back the task definition to the last Terraform-managed revision, reverting the image to the placeholder. This flag tells Terraform to manage infrastructure (security groups, IAM, networking) but leave the running task definition alone.

---

## Benchmarks

Measured on a 2022 MacBook Pro (M2) running Docker Desktop with the ETL targeting sample data, and on ECS Fargate (512 CPU / 1024 MB) against a live RDS instance.

### ETL pipeline (full run, live FEMA + Census APIs)

| Stage | Duration | Notes |
|---|---|---|
| Census ACS fetch | ~3s | Single page, 3,247 county rows |
| FEMA declarations fetch | ~45s | Paginated, ~65k records |
| FEMA PA projects fetch | ~11 min | 810k+ records, 1,000-row pages |
| `upsert_counties` | 0.31s | Single `INSERT ON CONFLICT`, was 4.8s before [#2](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/2) |
| `upsert_disasters` | 0.38s | Single `INSERT ON CONFLICT`, was 6.1s before [#2](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/2) |
| `upsert_disbursements` | ~2.1 min | 5,000-row flush batches, ~480k valid rows |
| `compute_metrics` | ~4s | Single GROUP BY query + bulk insert |
| **Total** | **~15 min** | Network I/O dominates (FEMA pagination) |

### API latency (ECS Fargate, measured via `X-Response-Time-Ms` response header)

| Endpoint | Cold (cache miss) | Warm (Redis hit) | Improvement |
|---|---|---|---|
| `GET /correlations` | ~820ms | ~14ms | −98% |
| `GET /analytics/quintiles` | ~340ms | ~11ms | −97% |
| `GET /analytics/underserved` | ~290ms | ~12ms | −96% |
| `GET /analytics/model` | ~110ms | ~12ms | −89% |
| `GET /metrics?limit=100` | ~28ms | — (not cached) | index-covered |
| `GET /health/deep` | ~8ms | — | DB + Redis ping |

Cold latency is dominated by pandas operations over the full joined dataset (~480k rows). All aggregate endpoints warm up on first request after an ETL run and stay fast for the rest of the day.

---

## Analytics Methodology

### Why not just Pearson r?

The initial correlation between median household income and response gap was r ≈ 0.16 — statistically weak and potentially misleading. Four issues were identified and addressed (tracked in [issue #3](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/3)):

1. **Right-skewed income distribution** — raw Pearson amplifies the influence of the ~200 counties above $90k household income. Fix: log-transform income before computing Pearson.
2. **Multi-year PA infrastructure outliers** — some FEMA Public Assistance projects span multiple years, producing gaps >730 days that aren't comparable to direct disaster aid. Fix: filter to `response_gap_days ∈ [0, 730]` and winsorize at [2nd, 98th] percentile.
3. **Disaster type as dominant confounder** — hurricanes trigger rapid federal mobilisation regardless of county income. Pooling hurricane and severe storm records suppresses the income signal for the latter. Fix: `disaster_type_analysis` stratifies by `incident_type`.
4. **Regional office effects** — some FEMA regional offices process paperwork faster regardless of local demographics. Fix: Ridge regression includes region dummies; `regional_equity_analysis` surfaces this directly.

### Methods used

| Endpoint | Method | What it measures |
|---|---|---|
| `GET /correlations` | Spearman ρ + log-Pearson r + Mann-Whitney U | Overall income↔gap relationship |
| `GET /analytics/quintiles` | `pd.qcut` into 5 income buckets | Distributional shape — not just one number |
| `GET /analytics/disaster-types` | GROUP BY incident_type | Disaster type as confounder |
| `GET /analytics/regional` | Weighted avg by FEMA region 1–10 | Regional office processing speed |
| `GET /analytics/underserved` | Composite z-score | Triple-disadvantaged counties |
| `GET /analytics/trends` | `PERCENTILE_CONT` year-by-year | Whether the gap is improving over time |
| `GET /analytics/model` | Ridge(α=1.0) on log(gap) | Multivariable decomposition |

**Why Ridge over OLS?** Income and region dummies are mildly collinear — wealthier counties cluster in certain FEMA regions. Ridge shrinkage prevents coefficient inflation without the sparsity of Lasso (all predictors are conceptually relevant). Alpha=1.0 chosen by eyeballing the regularisation path; a proper CV grid search is tracked in [issue #6](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/6).

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

### Example requests

```bash
# Spearman correlation with rural/urban Mann-Whitney test
curl http://localhost:8000/correlations | jq .
# {
#   "n": 48321,
#   "spearman_r": -0.1847,
#   "p_value": 0.000001,
#   "rural_mean_gap": 94.3,
#   "urban_mean_gap": 71.8,
#   "mann_whitney_p": 0.000034
# }

# Income quintile breakdown — does Q1 wait longer than Q5?
curl http://localhost:8000/analytics/quintiles | jq '.[] | {quintile, median_gap_days}'
# {"quintile": "Q1 (lowest)", "median_gap_days": 102.4}
# {"quintile": "Q5 (highest)", "median_gap_days": 68.1}

# Top 10 most underserved counties by composite score
curl "http://localhost:8000/analytics/underserved?top=10" | jq '.[] | {county_name, state, underserved_score}'

# Metrics for Texas counties with gap > 60 days, paginated
curl "http://localhost:8000/metrics?state=TX&min_gap=60&limit=50&offset=0"

# Deep health check (what the ALB uses)
curl http://localhost:8000/health/deep
# {"status": "ok", "checks": {"db": "ok", "redis": "ok"}}
```

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

The API falls back to `data/sample/*.json` fixtures automatically when live APIs are unreachable, so the dashboard is always demoable without credentials.

---

## Project Layout

```
drrgt/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, all endpoints, timing middleware
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic settings (env vars + pool sizing)
│   │   │   ├── database.py      # SQLAlchemy engine + connection pool
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
│   │       ├── celery_app.py    # Celery config (acks_late, retry, prefetch)
│   │       └── tasks.py         # Scheduled ETL task (daily 06:00 UTC)
│   ├── tests/                   # pytest — SQLite in-memory, no live infra needed
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                    # React + Vite + Tailwind + Recharts
├── data/sample/                 # Fallback JSON fixtures (always demoable)
├── infra/
│   └── main.tf                  # Full AWS stack: ECS, RDS, Redis, S3, ECR, ALB, CloudWatch, SNS
├── .github/
│   └── workflows/ci.yml         # Test → build → push SHA tag → ECS rolling deploy
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

Tests use SQLite in-memory — no Docker or live APIs required. The PostgreSQL-specific `INSERT ON CONFLICT` upsert functions are intentionally bypassed; ORM objects are seeded directly. All six tests cover the full pipeline: ingest → upsert → compute metrics → analytics functions.

---

## AWS Deployment

### Infrastructure (one-time)

```bash
cd infra
terraform init
terraform apply \
  -var db_password=<strong-password> \
  -var alert_email=you@example.com   # optional — skip to create SNS topic without email sub
```

Terraform provisions:
- **ECS Fargate** — two services: `api` (512 CPU / 1024 MB) and `worker` (1024 CPU / 2048 MB)
- **ALB** — HTTP listener, target group health-checked on `/health/deep`, 30s deregistration drain
- **RDS PostgreSQL 16** — `db.t3.micro`, encrypted at rest
- **ElastiCache Redis 7** — `cache.t3.micro`
- **S3** — raw data landing zone with SSE-AES256; objects move to STANDARD_IA at 30 days, expire at 365
- **ECR** — lifecycle keeps last 10 images
- **CloudWatch** — log groups (14-day retention), metric filters on ETL errors and API 5xx, three alarms wired to SNS
- **App autoscaling** — API service scales 1→4 tasks at 70% average CPU

```bash
terraform output   # alb_dns_name, ecr_repository_url, alerts_topic_arn, etc.
```

### Secrets

Inject `DATABASE_URL`, `REDIS_URL`, and `CENSUS_API_KEY` as ECS task environment variables or pull from AWS Secrets Manager in the task definition. Never commit `.env` files.

---

## CI/CD Pipeline

`.github/workflows/ci.yml` runs on every push to `main`:

1. **Test** — `pytest` against SQLite (no external services needed)
2. **Frontend build** — `npm run build` to catch JS compilation errors early
3. **Deploy** (main branch only):
   - Authenticate to ECR via `aws-actions/amazon-ecr-login`
   - `docker build` and push tagged with the commit SHA (e.g. `drrgt-api:abc1234f`)
   - For each service (API, Worker): fetch current task definition JSON → replace container image → register new task definition revision → `aws ecs update-service --force-new-deployment`
   - `aws ecs wait services-stable` — CI job doesn't pass until the API service reports healthy

The ECS services have `lifecycle { ignore_changes = [task_definition] }` in Terraform so `terraform apply` never undoes a CI-deployed image revision.

**Required GitHub secrets:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `ECR_REGISTRY`, `ECS_CLUSTER`, `ECS_SERVICE_API`, `ECS_SERVICE_WORKER`, `TASK_DEF_API`, `TASK_DEF_WORKER`.

---

## Open Issues

| # | Title | Type |
|---|---|---|
| [#4](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/4) | Upgrade map tab from state bar chart to county-level choropleth | enhancement |
| [#5](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/5) | Replace population-threshold rural flag with USDA RUCC codes | enhancement |
| [#6](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/6) | Cache Ridge model coefficients post-ETL to eliminate per-request refit | performance |
| [#7](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/7) | Ingest Individual Assistance data for household-level gap analysis | enhancement |

---

## Known Limitations

- **`temporal_trends`** uses `PERCENTILE_CONT` which is PostgreSQL-only and not covered by the SQLite unit tests.
- **`/analytics/model`** refits Ridge on every cache miss (~110ms). Tracked in [#6](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/6).
- **FEMA PA data** covers infrastructure and public facilities. Individual household assistance data is a separate endpoint not yet ingested — tracked in [#7](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/issues/7).
- ETL runtime (~15 min) is dominated by FEMA API pagination. Adding a `$filter` to limit to the last 10 years would cut this significantly at the cost of historical coverage.

---

## License

MIT — see `LICENSE`.
