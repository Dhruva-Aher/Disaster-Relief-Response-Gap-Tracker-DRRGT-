"""
Smoke tests for ETL pipeline and analytics.

Test strategy
-------------
- Use SQLite in-memory (via file path) for speed and zero external deps.
- Tests that call `_load_base` or `income_quintile_analysis` use standard SQL
  that SQLite supports. `temporal_trends` and `multivariable_gap_model` use
  PostgreSQL-specific SQL (PERCENTILE_CONT, EXTRACT::int); they are not
  unit-tested here — they are covered by integration tests against a real DB.
- Seed enough rows (10 counties, 1 disaster → 10 metrics) for statistical
  functions that require n >= 10 to run.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_drrgt.db"
os.environ["USE_SAMPLE_DATA_FALLBACK"] = "true"

from datetime import date

import pytest

from app.core.database import SessionLocal, engine, init_db
from app.etl.pipeline import compute_metrics
from app.models.db import Base, County, Disaster, Disbursement
from app.services.analysis import (
    income_gap_correlation,
    income_quintile_analysis,
    underserved_counties,
)


def setup_function(_):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed(db):
    """
    10 counties spanning a wide income range; 1 disaster; 10 disbursements.
    Lower-income counties (i < 5) get longer gaps to produce a measurable
    correlation direction without hard-coding the exact r value.
    """
    counties = [
        County(
            fips=f"1000{i}",
            name=f"County {i}",
            state="TX",
            population=10_000 + i * 5_000,
            median_income=20_000 + i * 12_000,
            income_percentile=float(i * 10),
            is_rural=(i < 5),
        )
        for i in range(10)
    ]
    disaster = Disaster(
        id="D1",
        title="Test Hurricane",
        incident_type="Hurricane",
        declaration_date=date(2022, 6, 1),
        state="TX",
    )
    db.add_all(counties + [disaster])
    db.commit()

    # Lower-income counties (i < 5) wait longer (gap = 30 + i*2 days)
    # Higher-income counties (i >= 5) wait less (gap = 10 + i days)
    disbursements = [
        Disbursement(
            disaster_id="D1",
            county_fips=f"1000{i}",
            disbursement_date=date(2022, 6, 1 + (30 - i * 3 if i < 5 else 10 + i)),
            amount_disbursed=float(100_000 + i * 50_000),
        )
        for i in range(10)
    ]
    db.add_all(disbursements)
    db.commit()


def test_compute_metrics_populates_table():
    db = SessionLocal()
    _seed(db)
    n = compute_metrics(db)
    assert n == 10, f"Expected 10 metric rows, got {n}"
    db.close()


def test_income_gap_correlation_returns_valid_stats():
    db = SessionLocal()
    _seed(db)
    compute_metrics(db)
    result = income_gap_correlation(db)
    assert result["n"] == 10
    assert result["pearson_r"] is not None
    assert result["spearman_r"] is not None
    # Higher income → shorter gap should produce a negative correlation
    assert result["spearman_r"] < 0, "Expected negative rank correlation (higher income, shorter gap)"
    db.close()


def test_income_quintile_analysis_returns_five_buckets():
    db = SessionLocal()
    _seed(db)
    compute_metrics(db)
    result = income_quintile_analysis(db)
    assert len(result) == 5
    for bucket in result:
        assert "quintile" in bucket
        assert "median_gap_days" in bucket
        assert bucket["n"] > 0
    db.close()


def test_underserved_counties_respects_top_n():
    db = SessionLocal()
    _seed(db)
    compute_metrics(db)
    result = underserved_counties(db, top_n=3)
    assert len(result) <= 3
    # Scores should be in descending order
    scores = [r["underserved_score"] for r in result]
    assert scores == sorted(scores, reverse=True)
    db.close()


def test_compute_metrics_is_idempotent():
    db = SessionLocal()
    _seed(db)
    n1 = compute_metrics(db)
    n2 = compute_metrics(db)
    assert n1 == n2, "Re-running compute_metrics should produce the same row count"
    db.close()


def test_fallback_when_fema_unreachable(monkeypatch):
    from app.etl import ingest
    monkeypatch.setattr(ingest.settings, "fema_base_url", "http://127.0.0.1:1")
    monkeypatch.setattr(ingest.settings, "use_sample_data_fallback", True)
    rows = ingest.fetch_fema("DisasterDeclarationsSummaries")
    assert isinstance(rows, list)
