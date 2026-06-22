"""Seed the database with sample disasters, counties, and synthetic disbursements for demo.
Run with: python -m app.etl.seed
"""
import json
import logging
import random
from datetime import timedelta
from pathlib import Path
from app.core.database import SessionLocal, init_db
from app.models.db import County, Disaster, Disbursement
from app.etl.pipeline import upsert_counties, upsert_disasters, compute_metrics

log = logging.getLogger(__name__)
SAMPLE = Path(__file__).resolve().parents[3] / "data" / "sample"


def seed() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    db = SessionLocal()
    try:
        counties = json.loads((SAMPLE / "census_counties.json").read_text())
        disasters = json.loads((SAMPLE / "disasterdeclarationssummaries.json").read_text())
        upsert_counties(db, counties)
        upsert_disasters(db, disasters)

        # Synthesize disbursements: rural/low-income counties get longer delays
        random.seed(42)
        rows_added = 0
        for d in db.query(Disaster).all():
            # Assign to a random subset of counties in the same or nearby state
            candidates = db.query(County).filter(County.state == d.state).all() or db.query(County).limit(3).all()
            for c in candidates[:5]:
                base_gap = 20
                if c.median_income and c.median_income < 50000:
                    base_gap += 35
                if c.is_rural:
                    base_gap += 25
                gap = max(3, int(random.gauss(base_gap, 12)))
                disb_date = d.declaration_date + timedelta(days=gap)
                amount = random.randint(50_000, 2_000_000)
                db.add(Disbursement(disaster_id=d.id, county_fips=c.fips,
                                    disbursement_date=disb_date, amount_disbursed=amount * 0.9))
                rows_added += 1
        db.commit()
        log.info("Seeded %s disbursement rows", rows_added)
        compute_metrics(db)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
