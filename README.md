# Disaster Relief Response Gap Tracker (DRRGT)

Track how long FEMA disaster aid takes to reach U.S. communities — and analyze whether delays are worse in lower-income or rural counties.

**Stack:** FastAPI · PostgreSQL · Redis · Celery · React (Vite + Tailwind) · Recharts · Docker · AWS · GitHub Actions

---

## Quick Start (Local)

```bash
git clone <your-fork> drrgt && cd drrgt
cp .env.example .env                    # optional: add CENSUS_API_KEY
docker compose up --build
```

Then, in a second terminal, seed the database with realistic synthetic data so every tab is populated:

```bash
docker compose exec api python -m app.etl.seed
```

Open:
- **Dashboard:** http://localhost:5173
- **API docs:** http://localhost:8000/docs
- **Health:**  http://localhost:8000/health

To run the real ETL against live FEMA + Census APIs:
```bash
docker compose exec api python -m app.etl.pipeline
```

## Architecture

```
┌────────────┐   daily    ┌──────────────┐    joins    ┌──────────────┐
│ FEMA OpenAPI│──────────▶│ Celery Worker│────────────▶│ PostgreSQL    │
│ Census ACS  │           │   + ETL      │             │ (RDS in prod) │
└────────────┘            └──────────────┘             └──────┬───────┘
                                                              │
                          ┌──────────────┐  cached (Redis) ┌──▼───────┐
                          │  React SPA   │ ◀──────────────▶│ FastAPI  │
                          │ (6 tabs)     │                 │          │
                          └──────────────┘                 └──────────┘
```

- **Ingestion** handles FEMA v2 pagination (`$top`/`$skip`), exponential backoff, and falls back to `data/sample/*.json` if APIs are unreachable — so the dashboard is always demoable.
- **ETL** cleans + joins datasets on county FIPS + disaster ID, computes `response_gap_days = first_disbursement_date − declaration_date`, income percentile rank, and a rural flag.
- **Metrics** are written to an indexed `metrics` table for fast aggregations.
- **API** exposes `/metrics`, `/counties`, `/correlations`, `/timeseries`, `/outliers`, `/insights` — all with Redis caching and filter/pagination.
- **Worker** (Celery Beat) runs the ETL daily at 06:00 UTC.

## Dashboard Tabs

| Tab | Description |
|---|---|
| **Map View** | State-level average response gap bar chart, red→green color scale (choropleth-ready) |
| **Inequality** | Scatter of median income vs response time with Pearson r |
| **Time Trends** | Line chart of average gap per year |
| **County Explorer** | Search counties by name, view income/population/rural stats |
| **Outliers** | Top-25 worst response gaps, color-coded |
| **Insights** | Auto-generated plain-English statistical takeaways |

Dark/light mode toggle in the header.

## Project Layout

```
drrgt/
├── backend/            # FastAPI + ETL + Celery
│   ├── app/
│   │   ├── main.py            # API endpoints with Redis caching
│   │   ├── core/              # config, database
│   │   ├── models/db.py       # SQLAlchemy models
│   │   ├── etl/               # ingest, pipeline, seed
│   │   ├── services/          # correlation + ML
│   │   └── worker/            # Celery app + schedule
│   ├── tests/                 # pytest smoke tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/           # React + Vite + Tailwind
├── data/sample/        # fallback JSON fixtures
├── infra/main.tf       # Terraform for AWS
├── .github/workflows/  # CI/CD
└── docker-compose.yml
```

## Running Tests

```bash
cd backend && pytest -q
```

## Deployment to AWS

1. **Provision infra:** `cd infra && terraform init && terraform apply -var db_password=...`
2. **Build + push API image** to the ECR repo output by Terraform.
3. **Create ECS Fargate services** for `api` and `worker` using the image; inject `DATABASE_URL` and `REDIS_URL` from Terraform outputs via Secrets Manager.
4. **Frontend:** `npm run build` → sync `frontend/dist` to an S3 bucket fronted by CloudFront.
5. **CI/CD:** `.github/workflows/ci.yml` builds and pushes images on every `main` push.

**Secrets:** Never commit `.env`. All keys (FEMA has no key; Census is optional; AWS creds) come from environment variables or AWS Secrets Manager in production.

## API Reference (excerpt)

| Endpoint | Query Params | Description |
|---|---|---|
| `GET /metrics` | `state`, `min_gap`, `limit`, `offset` | Join of metrics + counties |
| `GET /counties` | `search`, `state`, `limit` | County lookup |
| `GET /correlations` | — | Pearson r + rural/urban means |
| `GET /timeseries` | — | Yearly avg gap |
| `GET /outliers` | `top` | Worst N response gaps |
| `GET /insights` | — | Auto-generated narrative |

## Known Limitations / Extensions

- The current ETL uses `DisasterDeclarationsSummaries` as the primary FEMA endpoint. To capture more disbursement detail, extend `pipeline.run_pipeline()` to also ingest `PublicAssistanceFundedProjectsDetails` and `IndividualsAndHouseholdsProgramValidRegistrations`.
- The Map tab renders a state-level bar chart; to upgrade to a true county choropleth, import `us-atlas/counties-10m.json` and render with `react-simple-maps` keyed by FIPS.
- The rural flag is a population-based proxy; swap for USDA Rural-Urban Continuum Codes for accuracy.

## License

MIT — see `LICENSE`.
