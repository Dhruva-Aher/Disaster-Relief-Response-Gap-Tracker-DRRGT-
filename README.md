# 🚨 Disaster Relief Response Gap Tracker (DRRGT)

> **How long does FEMA aid actually take to reach communities — and who gets left waiting the longest?**

DRRGT ingests live data from the FEMA Open API and U.S. Census ACS, then surfaces the gap between disaster declarations and first disbursements across every U.S. county. It quantifies whether delays are worse in lower-income or rural areas, and presents findings through an interactive, six-tab dashboard.

---

## Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Quick Start (Local)](#quick-start-local)
- [Dashboard Tabs](#dashboard-tabs)
- [API Reference](#api-reference)
- [Project Layout](#project-layout)
- [Running Tests](#running-tests)
- [Deployment to AWS](#deployment-to-aws)
- [Known Limitations & Planned Extensions](#known-limitations--planned-extensions)
- [License](#license)

---

## Features

- **Response gap metric** — computes `response_gap_days = first_disbursement_date − declaration_date` per county per disaster
- **Equity analysis** — Pearson r correlation between median household income and response time
- **Rural vs. urban comparison** — flags rural counties and surfaces mean gap differences
- **Interactive dashboard** — six tabs covering maps, scatter plots, time trends, county search, outliers, and auto-generated insights
- **Always demoable** — falls back to bundled sample JSON fixtures when live APIs are unreachable
- **Daily refresh** — Celery Beat worker re-runs the ETL at 06:00 UTC automatically

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API** | FastAPI (Python) |
| **Database** | PostgreSQL (Amazon RDS in production) |
| **Cache** | Redis |
| **Task Queue** | Celery + Celery Beat |
| **Frontend** | React, Vite, Tailwind CSS, Recharts |
| **Infra** | Docker, AWS (ECS Fargate, S3, CloudFront, Secrets Manager), Terraform |
| **CI/CD** | GitHub Actions |

---

## Architecture

```
┌─────────────────┐  daily   ┌───────────────────┐   joins   ┌───────────────────┐
│  FEMA Open API  │─────────▶│   Celery Worker   │──────────▶│   PostgreSQL      │
│  Census ACS     │          │   + ETL Pipeline  │           │   (RDS in prod)   │
└─────────────────┘          └───────────────────┘           └────────┬──────────┘
                                                                       │
                             ┌───────────────────┐  Redis cache  ┌────▼──────────┐
                             │   React SPA       │◀─────────────▶│   FastAPI     │
                             │   (6 tabs)        │               │               │
                             └───────────────────┘               └───────────────┘
```

**Ingestion** handles FEMA v2 API pagination (`$top`/`$skip`) with exponential backoff, and falls back to `data/sample/*.json` if APIs are unreachable.

**ETL** cleans and joins datasets on county FIPS + disaster ID, then computes `response_gap_days`, income percentile rank, and a rural flag. Aggregated metrics are written to an indexed `metrics` table for fast queries.

**API** exposes six endpoints with Redis caching, filtering, and pagination.

**Worker** schedules the full ETL pipeline to run daily at 06:00 UTC via Celery Beat.

---

## Quick Start (Local)

**Prerequisites:** Docker and Docker Compose.

```bash
# 1. Clone and configure
git clone https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT- drrgt
cd drrgt
cp .env.example .env         # optionally add your CENSUS_API_KEY

# 2. Build and start all services
docker compose up --build

# 3. In a second terminal, seed the database
docker compose exec api python -m app.etl.seed
```

Then open:

| Service | URL |
|---|---|
| **Dashboard** | http://localhost:5173 |
| **API docs** (Swagger) | http://localhost:8000/docs |
| **Health check** | http://localhost:8000/health |

To run the real ETL against live FEMA and Census APIs instead of seed data:

```bash
docker compose exec api python -m app.etl.pipeline
```

---

## Dashboard Tabs

| Tab | What It Shows |
|---|---|
| **Map View** | State-level average response gap bar chart with a red→green color scale (choropleth-ready) |
| **Inequality** | Scatter plot of median household income vs. response time, annotated with Pearson r |
| **Time Trends** | Line chart of average response gap per year |
| **County Explorer** | Searchable county table with income, population, and rural stats |
| **Outliers** | Top-25 worst response gaps, color-coded by severity |
| **Insights** | Auto-generated plain-English statistical takeaways |

A dark/light mode toggle is available in the header.

---

## API Reference

Base URL: `http://localhost:8000`

| Method | Endpoint | Query Params | Description |
|---|---|---|---|
| `GET` | `/metrics` | `state`, `min_gap`, `limit`, `offset` | Joined metrics + county data |
| `GET` | `/counties` | `search`, `state`, `limit` | County search and lookup |
| `GET` | `/correlations` | — | Pearson r, rural mean, urban mean |
| `GET` | `/timeseries` | — | Yearly average response gap |
| `GET` | `/outliers` | `top` | Worst N response gaps |
| `GET` | `/insights` | — | Auto-generated narrative summary |

Full interactive docs are available at `/docs` (Swagger UI) and `/redoc`.

---

## Project Layout

```
drrgt/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app and API endpoints
│   │   ├── core/              # Config and database session
│   │   ├── models/db.py       # SQLAlchemy ORM models
│   │   ├── etl/               # ingest.py, pipeline.py, seed.py
│   │   ├── services/          # Correlation analysis and ML helpers
│   │   └── worker/            # Celery app and beat schedule
│   ├── tests/                 # pytest smoke tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                  # React + Vite + Tailwind
├── data/sample/               # Fallback JSON fixtures
├── infra/
│   └── main.tf                # Terraform for AWS provisioning
├── .github/workflows/         # CI/CD pipeline (ci.yml)
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

---

## Deployment to AWS

### 1. Provision infrastructure

```bash
cd infra
terraform init
terraform apply -var db_password=<your-password>
```

This creates an RDS PostgreSQL instance, an ElastiCache Redis cluster, an ECR registry, and networking resources.

### 2. Build and push the API image

```bash
# Authenticate to ECR (use the repo URL from Terraform outputs)
aws ecr get-login-password | docker login --username AWS --password-stdin <ecr-url>

docker build -t drrgt-api ./backend
docker tag drrgt-api:latest <ecr-url>/drrgt-api:latest
docker push <ecr-url>/drrgt-api:latest
```

### 3. Deploy ECS Fargate services

Create two Fargate services — one for `api` and one for `worker` — using the pushed image. Inject `DATABASE_URL` and `REDIS_URL` from Terraform outputs via AWS Secrets Manager.

### 4. Deploy the frontend

```bash
cd frontend
npm run build
aws s3 sync dist/ s3://<your-bucket> --delete
```

Serve the bucket through a CloudFront distribution for HTTPS and CDN caching.

### 5. CI/CD

`.github/workflows/ci.yml` automatically builds and pushes a new API image on every push to `main`.

> **Security note:** Never commit `.env` or any credentials. All secrets (Census API key, AWS credentials) must come from environment variables or AWS Secrets Manager in production.

---

## Known Limitations & Planned Extensions

**Current limitations:**

- ETL uses `DisasterDeclarationsSummaries` as the primary FEMA endpoint. For more granular disbursement data, `pipeline.run_pipeline()` can be extended to also ingest `PublicAssistanceFundedProjectsDetails` and `IndividualsAndHouseholdsProgramValidRegistrations`.
- The **Map tab** renders a state-level bar chart. To upgrade to a true county-level choropleth, import `us-atlas/counties-10m.json` and render with `react-simple-maps` keyed by FIPS code.
- The **rural flag** is a population-based proxy. Replacing it with USDA Rural-Urban Continuum Codes (RUCC) would yield more accurate classification.

**Potential extensions:**

- Add a demographics breakdown tab (age, race/ethnicity) alongside income
- Expose a public API with rate limiting for researchers and journalists
- Integrate ML anomaly detection to flag unusual delay spikes in real time

---

## License

MIT — see `LICENSE`.
