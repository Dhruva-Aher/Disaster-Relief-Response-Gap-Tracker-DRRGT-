# Disaster Relief Response Gap Tracker (DRRGT)

**Public-data ETL + analytics** · Data / Backend · FastAPI · React · PostgreSQL · Redis

Joins **OpenFEMA** disaster aid with **Census** demographics to compute an auditable **response gap** (days from declaration → first obligation) and surface county/state/outlier reports — for researchers and journalists, not invented SLA theater.

[![CI](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/actions/workflows/ci.yml/badge.svg)](https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT-/actions/workflows/ci.yml)

| | |
|--|--|
| **Focus** | ETL correctness · response-gap metric · peer comparisons |
| **Stack** | FastAPI · Celery · PostgreSQL · Redis · React · Docker |
| **Proof** | **10** backend pytest cases · Compose stack · CI |

---

## Highlights

- **Correctness** — Single primary metric: `response_gap_days = obligation_date − declaration_date`, joined on FIPS; peer counties matched on rural/urban + population/income bands (±25%).
- **Pipeline** — Celery ETL: Census demographics + paginated OpenFEMA declarations/PA projects with backoff → upsert → SQL aggregates (quintiles, trends).
- **API** — FastAPI report endpoints with cached aggregates for county / state / outlier views + CSV export.
- **Verification** — **10** pytest cases (`test_api`, `test_pipeline`); CI on `main`.

---

## Architecture

| Component | Responsibility |
|-----------|----------------|
| **Celery ETL** | Extract OpenFEMA + Census; transform; upsert |
| **PostgreSQL** | Normalized facts + analytical aggregates |
| **Redis** | Celery broker / cache |
| **FastAPI** | Report APIs |
| **React** | Interactive reports + CSV |

```text
OpenFEMA + Census → Celery ETL → Postgres
                                   ↓
                         FastAPI reports → React
```

### Metric definitions

| Name | Definition |
|------|------------|
| **Response gap** | Days from disaster declaration to first PA obligation |
| **Peer county** | Same rural/urban class; population ±25%; median income ±25% |
| **Consistently underserved** | Multiple events with gap **> 90** days |

---

## Quick start

```bash
git clone https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT- drrgt
cd drrgt
cp .env.example .env   # optional CENSUS_API_KEY
docker compose up --build -d
# API :8000 · UI :5173 — first boot runs migrations + initial ETL
```

Tests: `cd backend && pip install -r requirements.txt && pytest tests/ -v`

---

## Evidence notes

| Phrase | Status |
|--------|--------|
| “Millions of FEMA rows” | Design capacity of OpenFEMA-scale ingest — cite a **counted** export in docs before pitching an exact row count on a resume |
| **~3,200** counties | FIPS universe used in upsert design (`pipeline.py`) |
| Placeholder report PNGs | Removed from README — run Compose and capture real screenshots before adding assets |

Do not claim AWS/Terraform production SLAs unless the deploy docs and live URL are current.

---

## For interview depth

| Doc | Use |
|-----|-----|
| [docs/METRICS.md](docs/METRICS.md) | Claim ↔ evidence (cross-verified 2026-09-30) |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Context → Decision → Why → Evidence |
