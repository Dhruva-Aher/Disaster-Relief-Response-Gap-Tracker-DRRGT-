"""
ETL pipeline: Census → FEMA declarations → FEMA PA projects → metrics.

Key optimisations over the original
------------------------------------
upsert_counties / upsert_disasters:
  Replaced db.merge() loop (N round-trips) with a single PostgreSQL
  INSERT ... ON CONFLICT DO UPDATE. For 3,200 counties this cuts the
  upsert from ~3,200 queries to 1.

  NOTE: pg_insert is PostgreSQL-specific. Tests bypass these functions and
  add ORM objects directly, so SQLite compatibility is not needed here.

upsert_disbursements:
  Kept bulk_save_objects with 5,000-row flush batches — disbursements are
  cleared and reloaded on every run (idempotent), so upsert semantics are
  not required. Bulk insert at 5k rows is the SQLAlchemy sweet spot before
  memory pressure starts degrading throughput.

compute_metrics:
  Single GROUP BY aggregate query rather than Python-side arithmetic.
  Clears the metrics table first so re-runs never accumulate stale rows.

Cache invalidation:
  invalidate_analytics() is called after a successful pipeline run.
  The next HTTP request to any analytics endpoint recomputes from the
  fresh database state rather than serving day-old cached results.
"""
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, init_db
from app.etl.ingest import fetch_census, fetch_fema
from app.models.db import County, Disaster, Disbursement, Metric
from app.services.cache import invalidate_analytics

log = logging.getLogger(__name__)


def _parse_date(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except Exception:
        return None


def upsert_counties(db: Session, rows: list) -> int:
    df = pd.DataFrame(rows).dropna(subset=["fips"])
    if df.empty:
        return 0

    df = df.assign(
        state=df["fips"].str[:2],
        income_percentile=df["median_income"].rank(pct=True) * 100,
        is_rural=df["population"].fillna(0) < 50_000,
    )[["fips", "name", "state", "population", "median_income", "income_percentile", "is_rural"]]

    records = df.to_dict("records")
    stmt = pg_insert(County.__table__).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["fips"],
        set_={
            "name":               stmt.excluded.name,
            "state":              stmt.excluded.state,
            "population":         stmt.excluded.population,
            "median_income":      stmt.excluded.median_income,
            "income_percentile":  stmt.excluded.income_percentile,
            "is_rural":           stmt.excluded.is_rural,
        },
    )
    db.execute(stmt)
    db.commit()
    log.info("Counties upserted", extra={"ctx_count": len(records)})
    return len(records)


def upsert_disasters(db: Session, rows: list) -> int:
    seen: set[str] = set()
    records: list[dict] = []
    for r in rows:
        did = str(r.get("disasterNumber") or "")
        if not did or did in seen:
            continue
        seen.add(did)
        records.append({
            "id":               did,
            "title":            (r.get("declarationTitle") or "")[:256],
            "incident_type":    (r.get("incidentType") or "")[:64],
            "declaration_date": _parse_date(r.get("declarationDate")),
            "state":            r.get("state"),
        })
    if not records:
        return 0

    stmt = pg_insert(Disaster.__table__).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "title":            stmt.excluded.title,
            "incident_type":    stmt.excluded.incident_type,
            "declaration_date": stmt.excluded.declaration_date,
            "state":            stmt.excluded.state,
        },
    )
    db.execute(stmt)
    db.commit()
    log.info("Disasters upserted", extra={"ctx_count": len(records)})
    return len(records)


def upsert_disbursements(db: Session, rows: list) -> int:
    known_fips      = {c.fips for c in db.query(County.fips).all()}
    known_disasters = {d.id   for d in db.query(Disaster.id).all()}
    log.info(
        "Disbursement load starting",
        extra={"ctx_counties": len(known_fips), "ctx_disasters": len(known_disasters)},
    )

    db.execute(delete(Disbursement))
    db.commit()

    batch: list = []
    count = skip = 0

    for r in rows:
        did = r.get("disasterNumber")
        if did is None or str(did) not in known_disasters:
            skip += 1
            continue

        raw_state  = r.get("stateNumberCode")
        raw_county = r.get("countyCode")
        if not raw_county or not raw_state:
            skip += 1
            continue
        try:
            fips = str(int(raw_state)).zfill(2) + str(int(raw_county)).zfill(3)
        except (TypeError, ValueError):
            skip += 1
            continue
        if fips.endswith("000") or fips not in known_fips:
            skip += 1
            continue

        date_val = (
            _parse_date(r.get("lastObligationDate"))
            or _parse_date(r.get("firstObligationDate"))
            or _parse_date(r.get("lastRefresh"))
        )
        if not date_val:
            skip += 1
            continue

        try:
            amount = float(r.get("federalShareObligated") or r.get("projectAmount") or 0)
        except (TypeError, ValueError):
            amount = 0.0

        batch.append(
            Disbursement(
                disaster_id=str(did),
                county_fips=fips,
                disbursement_date=date_val,
                amount_disbursed=amount,
            )
        )
        count += 1

        if len(batch) >= 5_000:
            db.bulk_save_objects(batch)
            db.commit()
            batch.clear()
            log.info("Disbursement flush", extra={"ctx_total": count})

    if batch:
        db.bulk_save_objects(batch)
        db.commit()

    log.info(
        "Disbursements loaded",
        extra={"ctx_inserted": count, "ctx_skipped": skip},
    )
    return count


def compute_metrics(db: Session) -> int:
    db.execute(delete(Metric))
    db.commit()

    rows = db.execute(text("""
        SELECT
            d.id,
            d.declaration_date,
            dis.county_fips,
            MIN(dis.disbursement_date) AS first_disb,
            SUM(dis.amount_disbursed)  AS total,
            c.population
        FROM disasters     d
        JOIN disbursements dis ON dis.disaster_id = d.id
        JOIN counties      c   ON c.fips = dis.county_fips
        WHERE d.declaration_date  IS NOT NULL
          AND dis.disbursement_date IS NOT NULL
        GROUP BY d.id, d.declaration_date, dis.county_fips, c.population
    """)).fetchall()

    if not rows:
        log.warning("compute_metrics: no disbursements found — check pipeline ran correctly")
        return 0

    batch: list = []
    for r in rows:
        if not r.first_disb or not r.declaration_date:
            continue
        gap     = (r.first_disb - r.declaration_date).days
        per_cap = r.total / r.population if r.population else None
        batch.append(
            Metric(
                disaster_id=r.id,
                county_fips=r.county_fips,
                response_gap_days=gap,
                amount_per_capita=per_cap,
            )
        )
        if len(batch) >= 5_000:
            db.bulk_save_objects(batch)
            db.commit()
            batch.clear()

    if batch:
        db.bulk_save_objects(batch)
        db.commit()

    log.info("Metrics computed", extra={"ctx_count": len(rows)})
    return len(rows)


def run_pipeline() -> None:
    import app.core.logging as _log_cfg
    _log_cfg.configure()

    init_db()
    db = SessionLocal()
    try:
        log.info("ETL pipeline start")
        n_counties  = upsert_counties(db, fetch_census())
        n_disasters = upsert_disasters(db, fetch_fema("DisasterDeclarationsSummaries"))
        n_disb      = upsert_disbursements(db, fetch_fema("PublicAssistanceFundedProjectsDetails"))
        n_metrics   = compute_metrics(db)

        # Bust all analytics cache keys so the next HTTP request recomputes
        # from fresh data instead of serving yesterday's cached results.
        invalidate_analytics()

        log.info(
            "ETL pipeline complete",
            extra={
                "ctx_counties":      n_counties,
                "ctx_disasters":     n_disasters,
                "ctx_disbursements": n_disb,
                "ctx_metrics":       n_metrics,
            },
        )
    except Exception as exc:
        log.error("ETL pipeline failed", extra={"ctx_err": str(exc)}, exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_pipeline()
