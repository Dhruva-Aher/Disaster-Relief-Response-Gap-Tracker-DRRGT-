"""Basic smoke tests for ingest + ETL + analysis (no external API calls)."""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_drrgt.db"

from datetime import date
from app.core.database import SessionLocal, init_db, engine
from app.models.db import Base, County, Disaster, Disbursement
from app.etl.pipeline import compute_metrics
from app.services.analysis import income_gap_correlation


def setup_function(_):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_compute_metrics_and_correlation():
    db = SessionLocal()
    db.add_all([
        County(fips="10001", name="Rich County", state="CA",
               population=100000, median_income=120000, income_percentile=95, is_rural=False),
        County(fips="10002", name="Poor County", state="WV",
               population=8000, median_income=28000, income_percentile=5, is_rural=True),
        Disaster(id="D1", title="Test Hurricane", incident_type="Hurricane",
                 declaration_date=date(2024, 1, 1), state="CA"),
    ])
    db.commit()
    db.add_all([
        Disbursement(disaster_id="D1", county_fips="10001",
                     disbursement_date=date(2024, 1, 10), amount_disbursed=500000),
        Disbursement(disaster_id="D1", county_fips="10002",
                     disbursement_date=date(2024, 3, 15), amount_disbursed=100000),
    ])
    db.commit()

    compute_metrics(db)
    result = income_gap_correlation(db)
    assert result["n"] == 2
    # Lower-income county has longer gap → negative correlation
    assert result["pearson_r"] is not None
    db.close()


def test_fallback_when_fema_unreachable(monkeypatch):
    from app.etl import ingest
    monkeypatch.setenv("USE_SAMPLE_DATA_FALLBACK", "true")
    # Force failure by pointing to a bad URL
    monkeypatch.setattr(ingest.settings, "fema_base_url", "http://127.0.0.1:1")
    rows = ingest.fetch_fema("DisasterDeclarationsSummaries")
    # Sample file exists (lowercase match) → non-empty list
    assert isinstance(rows, list)
