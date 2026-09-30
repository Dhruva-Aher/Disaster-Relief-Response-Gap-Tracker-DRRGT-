# Decisions — DRRGT

Related: [METRICS.md](./METRICS.md)

**Cross-verify (2026-09-30):** Metric definition + **10** tests Grade **A**. Row-count marketing Grade **D** (no archive). Placeholder screenshots already removed from README.

---

## D1 — One auditable primary metric

| | |
|--|--|
| **Context** | Disaster-aid disparity debates need a crisp quantity. |
| **Decision** | Optimize product around **response gap days** (declaration → first obligation). |
| **Why** | Journalists can challenge the formula; peers can recompute. |
| **Evidence** | ETL transform; METRICS C1 |
| **Status** | DECIDED · IMPLEMENTED |

---

## D2 — Peer-adjusted comparisons, not raw national rank alone

| | |
|--|--|
| **Context** | Rural tiny counties vs urban metros are not comparable raw. |
| **Decision** | Peer set = rural/urban match + pop/income ±25%. |
| **Why** | Reduces false “worst county” headlines. |
| **Evidence** | Methodology in README |
| **Status** | DECIDED · IMPLEMENTED |

---

## D3 — Celery ETL + precomputed aggregates for report APIs

| | |
|--|--|
| **Context** | Ad-hoc scans of raw FEMA pulls are slow. |
| **Decision** | Upsert raw facts; SQL aggregates for quintiles/trends; API serves cached reports. |
| **Tradeoffs** | Stale until ETL runs; clearer operability. |
| **Evidence** | Celery worker + FastAPI |
| **Status** | DECIDED · IMPLEMENTED |

---

## D4 — Never claim unverified row counts

| | |
|--|--|
| **Context** | Profile previously said “810K+ FEMA records” without export artifact. |
| **Decision** | Drop exact counts from resume/profile; allow “OpenFEMA-scale ingest” as design language only. |
| **Evidence** | `docs/METRICS.md` C8 |
| **Status** | DECIDED · VERIFIED (absence of evidence) |

---

## D5 — Local Compose is the demo until a live URL exists

| | |
|--|--|
| **Decision** | No homepage URL until a stable public deploy is verified. |
| **Status** | DECIDED |
