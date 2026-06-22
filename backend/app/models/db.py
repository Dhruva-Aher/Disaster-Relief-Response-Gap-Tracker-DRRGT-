"""
Database models with indexes tuned for the analytics query patterns.

Index design rationale
----------------------
counties:
  ix_counties_state_income (state, median_income)
  - /metrics?state=TX and income_quintile_analysis both filter by state
    then sort/group by income. Composite covering index avoids a table scan.

disasters:
  ix_disasters_type_date (incident_type, declaration_date)
  - disaster_type_analysis groups by incident_type and filters by date range.

disbursements:
  ix_disbursements_county_date (county_fips, disbursement_date)
  - compute_metrics MIN(disbursement_date) per county — this index supports
    the GROUP BY aggregation without a full table scan on 800k+ rows.

metrics:
  ix_metrics_county_disaster (county_fips, disaster_id) UNIQUE
  - Enforces one metric row per county/disaster pair (idempotent recompute).
  ix_metrics_gap_fips (response_gap_days, county_fips)
  - /outliers ORDER BY response_gap_days DESC uses this index.
  - underserved_counties WHERE response_gap_days BETWEEN 0 AND 730 benefits
    from the leading response_gap_days column.
"""
from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class County(Base):
    __tablename__ = "counties"
    fips:               Mapped[str]        = mapped_column(String(5), primary_key=True)
    name:               Mapped[str]        = mapped_column(String(128))
    state:              Mapped[str]        = mapped_column(String(2), index=True)
    population:         Mapped[int | None] = mapped_column(Integer)
    median_income:      Mapped[float | None] = mapped_column(Float, index=True)
    income_percentile:  Mapped[float | None] = mapped_column(Float)
    rural_urban_code:   Mapped[int | None] = mapped_column(Integer)
    is_rural:           Mapped[bool | None] = mapped_column(Boolean)

    __table_args__ = (
        Index("ix_counties_state_income", "state", "median_income"),
    )


class Disaster(Base):
    __tablename__ = "disasters"
    id:               Mapped[str]        = mapped_column(String(32), primary_key=True)
    title:            Mapped[str]        = mapped_column(String(256))
    incident_type:    Mapped[str]        = mapped_column(String(64), index=True)
    declaration_date: Mapped[date]       = mapped_column(Date, index=True)
    state:            Mapped[str]        = mapped_column(String(2), index=True)

    __table_args__ = (
        Index("ix_disasters_type_date", "incident_type", "declaration_date"),
    )


class Disbursement(Base):
    __tablename__ = "disbursements"
    id:                 Mapped[int]          = mapped_column(Integer, primary_key=True, autoincrement=True)
    disaster_id:        Mapped[str]          = mapped_column(ForeignKey("disasters.id"), index=True)
    county_fips:        Mapped[str]          = mapped_column(ForeignKey("counties.fips"), index=True)
    disbursement_date:  Mapped[date | None]  = mapped_column(Date)
    amount_disbursed:   Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        Index("ix_disbursements_county_date", "county_fips", "disbursement_date"),
    )


class Metric(Base):
    __tablename__ = "metrics"
    id:                 Mapped[int]          = mapped_column(Integer, primary_key=True, autoincrement=True)
    disaster_id:        Mapped[str]          = mapped_column(ForeignKey("disasters.id"), index=True)
    county_fips:        Mapped[str]          = mapped_column(ForeignKey("counties.fips"), index=True)
    response_gap_days:  Mapped[int | None]   = mapped_column(Integer, index=True)
    amount_per_capita:  Mapped[float | None] = mapped_column(Float)
    computed_at:        Mapped[datetime]     = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_metrics_county_disaster", "county_fips", "disaster_id", unique=True),
        Index("ix_metrics_gap_fips", "response_gap_days", "county_fips"),
    )

class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[str] = mapped_column(String)  # JSON payload
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)




class CountyInsight(Base):
    __tablename__ = "county_insights"
    fips: Mapped[str] = mapped_column(ForeignKey("counties.fips"), primary_key=True)
    avg_response_gap_days: Mapped[float | None] = mapped_column(Float)
    national_rank: Mapped[int | None] = mapped_column(Integer)
    national_percentile: Mapped[float | None] = mapped_column(Float)
    comparable_counties: Mapped[list | None] = mapped_column(JSON)
    historical_trend: Mapped[list | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class StateInsight(Base):
    __tablename__ = "state_insights"
    state: Mapped[str] = mapped_column(String(2), primary_key=True)
    avg_response_gap_days: Mapped[float | None] = mapped_column(Float)
    national_rank: Mapped[int | None] = mapped_column(Integer)
    historical_trend: Mapped[list | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
