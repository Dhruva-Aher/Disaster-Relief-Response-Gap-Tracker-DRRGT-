# Metrics & Claims — DRRGT

**Cross-verified:** 2026-09-30

| ID | Claim (exact) | Grade | Evidence |
|----|---------------|-------|----------|
| C1 | Primary metric `response_gap_days = obligation_date − declaration_date` | A | ETL `pipeline.py` |
| C2 | Join OpenFEMA PA projects to Census counties via FIPS | A | `pipeline.py` FIPS construction |
| C3 | Peer counties: same rural/urban; population ±25%; income ±25% | A | README methodology + code peers logic |
| C4 | Upsert designed for **~3,200** county FIPS universe | A | Comment/design in `pipeline.py` |
| C5 | **10** backend pytest cases | A | `backend/tests/` count 2026-09-30 |
| C6 | CI present | A | `.github/workflows/ci.yml` |
| C7 | Compose stack: Postgres, Redis, FastAPI, Celery, React | A | `docker-compose.yml` |
| C8 | “Millions of FEMA rows” / “810K+ records” | D / **dropped** | Sample JSON under `data/sample/` is tiny (~60 lines). No counted production export in-repo. Do not pitch exact row counts. |
| C9 | Live public demo URL | D | None set on GitHub homepage |

## Non-claims

| Phrase | Why |
|--------|-----|
| AWS/Terraform production SLA | Not verified as live portfolio deploy this pass |
| Exact national correlation coefficient as resume Y | Need archived query output |

## Re-verify

```bash
docker compose up --build -d
cd backend && pytest tests/ -v
```
