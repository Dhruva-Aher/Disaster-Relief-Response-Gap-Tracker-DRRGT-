import logging
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text, delete
from app.core.database import SessionLocal, init_db
from app.models.db import County, Disaster, Disbursement, Metric
from app.etl.ingest import fetch_fema, fetch_census
from app.services.cache import invalidate_analytics

log = logging.getLogger(__name__)


def _parse_date(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except Exception:
        return None


def upsert_counties(db: Session, rows):
    df = pd.DataFrame(rows).dropna(subset=["fips"])
    if df.empty:
        return

    df["income_percentile"] = df["median_income"].rank(pct=True) * 100
    df["is_rural"] = df["population"].fillna(0) < 50000

    for _, r in df.iterrows():
        db.merge(County(
            fips=r["fips"],
            name=r["name"],
            state=r["fips"][:2],
            population=r["population"],
            median_income=r["median_income"],
            income_percentile=r["income_percentile"],
            is_rural=r["is_rural"],
        ))

    db.commit()
    log.info(f"Upserted {len(df)} counties")


def upsert_disasters(db: Session, rows):
    seen = set()
    for r in rows:
        did = str(r.get("disasterNumber"))
        if not did or did in seen:
            continue
        seen.add(did)
        db.merge(Disaster(
            id=did,
            title=r.get("declarationTitle", ""),
            incident_type=r.get("incidentType", ""),
            declaration_date=_parse_date(r.get("declarationDate")),
            state=r.get("state"),
        ))
    db.commit()
    log.info(f"Upserted {len(seen)} unique disasters")


def upsert_disbursements(db: Session, rows):
    """
    Load PublicAssistanceFundedProjectsDetails into disbursements.

    FEMA PA field mapping:
      stateNumberCode  — 2-digit numeric state FIPS  (e.g. "48" for Texas)
      countyCode       — 3-digit numeric county code  (e.g. "465" for Zapata)
      combined FIPS    — "48" + "465" = "48465"

      date priority: lastObligationDate → firstObligationDate → lastRefresh
    """
    known_fips      = {c.fips for c in db.query(County.fips).all()}
    known_disasters = {d.id   for d in db.query(Disaster.id).all()}

    log.info(f"Known counties: {len(known_fips):,}  |  known disasters: {len(known_disasters):,}")

    # Clear first so re-runs don't accumulate duplicate rows
    db.execute(delete(Disbursement))
    db.commit()

    count            = 0
    skip_no_disaster = 0
    skip_no_county   = 0
    skip_no_date     = 0
    batch            = []

    for r in rows:
        # ── disaster FK ───────────────────────────────────────────────
        did = r.get("disasterNumber")
        if did is None:
            skip_no_disaster += 1
            continue
        did = str(did)
        if did not in known_disasters:
            skip_no_disaster += 1
            continue

        # ── FIPS: stateNumberCode (2-digit) + countyCode (3-digit) ───
        raw_state  = r.get("stateNumberCode")
        raw_county = r.get("countyCode")
        if not raw_county or not raw_state:
            skip_no_county += 1
            continue
        try:
            fips = str(int(raw_state)).zfill(2) + str(int(raw_county)).zfill(3)
        except (TypeError, ValueError):
            skip_no_county += 1
            continue
        if fips.endswith("000"):          # statewide project — no county
            skip_no_county += 1
            continue
        if fips not in known_fips:
            skip_no_county += 1
            continue

        # ── date ──────────────────────────────────────────────────────
        date_val = (
            _parse_date(r.get("lastObligationDate"))
            or _parse_date(r.get("firstObligationDate"))
            or _parse_date(r.get("lastRefresh"))
        )
        if not date_val:
            skip_no_date += 1
            continue

        # ── amount ────────────────────────────────────────────────────
        try:
            amount = float(
                r.get("federalShareObligated") or r.get("projectAmount") or 0
            )
        except (TypeError, ValueError):
            amount = 0.0

        batch.append(Disbursement(
            disaster_id=did,
            county_fips=fips,
            disbursement_date=date_val,
            amount_disbursed=amount,
        ))
        count += 1

        if len(batch) >= 5000:
            db.bulk_save_objects(batch)
            db.commit()
            batch.clear()
            log.info(f"  …flushed, total so far: {count:,}")

    if batch:
        db.bulk_save_objects(batch)
        db.commit()

    log.info(
        "Inserted %s disbursements (skipped: %s no-disaster, %s no-county, %s no-date)",
        count, skip_no_disaster, skip_no_county, skip_no_date,
    )


def compute_metrics(db: Session):
    """
    response_gap_days = first disbursement date − declaration date
    Clears and recomputes so re-runs are idempotent.
    """
    db.execute(delete(Metric))
    db.commit()

    rows = db.execute(text("""
        SELECT d.id, d.declaration_date, dis.county_fips,
               MIN(dis.disbursement_date) AS first_disb,
               SUM(dis.amount_disbursed)  AS total,
               c.population
        FROM disasters d
        JOIN disbursements dis ON dis.disaster_id = d.id
        JOIN counties c ON c.fips = dis.county_fips
        WHERE d.declaration_date IS NOT NULL
          AND dis.disbursement_date IS NOT NULL
        GROUP BY d.id, d.declaration_date, dis.county_fips, c.population
    """)).fetchall()

    if not rows:
        log.warning("compute_metrics: 0 rows — check disbursements table is populated.")
        return

    batch = []
    for r in rows:
        if not r.first_disb or not r.declaration_date:
            continue
        gap     = (r.first_disb - r.declaration_date).days
        per_cap = r.total / r.population if r.population else None
        batch.append(Metric(
            disaster_id=r.id,
            county_fips=r.county_fips,
            response_gap_days=gap,
            amount_per_capita=per_cap,
        ))
        if len(batch) >= 5000:
            db.bulk_save_objects(batch)
            db.commit()
            batch.clear()

    if batch:
        db.bulk_save_objects(batch)
        db.commit()

    log.info(f"Computed {len(rows):,} metrics")


def run_pipeline():
    logging.basicConfig(level=logging.INFO)
    init_db()
    db = SessionLocal()
    try:
        log.info("Step 1/4 — Census county data…")
        upsert_counties(db, fetch_census())

        # No date filter: PA projects reference disasters back to the 1990s.
        # Filtering to 2015+ caused 585k "no-disaster" skips.
        log.info("Step 2/4 — FEMA disaster declarations (all years)…")
        upsert_disasters(db, fetch_fema("DisasterDeclarationsSummaries"))

        log.info("Step 3/4 — PA funded project details…")
        upsert_disbursements(db, fetch_fema("PublicAssistanceFundedProjectsDetails"))

        log.info("Step 4/4 — computing metrics…")
        compute_metrics(db)

        # Bust cached analytics so the next HTTP request recomputes from
        # the fresh database state instead of serving yesterday's results.
        invalidate_analytics()

        log.info("Pipeline complete ✓")
    finally:
        db.close()


if __name__ == "__main__":
    run_pipeline()