"""Database models for disasters, aid, counties, and computed metrics."""
from datetime import date, datetime
from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class County(Base):
    __tablename__ = "counties"
    fips: Mapped[str] = mapped_column(String(5), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(2), index=True)
    population: Mapped[int | None] = mapped_column(Integer)
    median_income: Mapped[float | None] = mapped_column(Float, index=True)
    income_percentile: Mapped[float | None] = mapped_column(Float)
    rural_urban_code: Mapped[int | None] = mapped_column(Integer)  # USDA RUCC 1-9
    is_rural: Mapped[bool | None] = mapped_column()


class Disaster(Base):
    __tablename__ = "disasters"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # disasterNumber
    title: Mapped[str] = mapped_column(String(256))
    incident_type: Mapped[str] = mapped_column(String(64), index=True)
    declaration_date: Mapped[date] = mapped_column(Date, index=True)
    state: Mapped[str] = mapped_column(String(2), index=True)


class AidApproval(Base):
    __tablename__ = "aid_approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    disaster_id: Mapped[str] = mapped_column(ForeignKey("disasters.id"), index=True)
    county_fips: Mapped[str] = mapped_column(ForeignKey("counties.fips"), index=True)
    approval_date: Mapped[date | None] = mapped_column(Date)
    amount_approved: Mapped[float | None] = mapped_column(Float)


class Disbursement(Base):
    __tablename__ = "disbursements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    disaster_id: Mapped[str] = mapped_column(ForeignKey("disasters.id"), index=True)
    county_fips: Mapped[str] = mapped_column(ForeignKey("counties.fips"), index=True)
    disbursement_date: Mapped[date | None] = mapped_column(Date)
    amount_disbursed: Mapped[float | None] = mapped_column(Float)


class Metric(Base):
    __tablename__ = "metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    disaster_id: Mapped[str] = mapped_column(ForeignKey("disasters.id"), index=True)
    county_fips: Mapped[str] = mapped_column(ForeignKey("counties.fips"), index=True)
    response_gap_days: Mapped[int | None] = mapped_column(Integer, index=True)
    amount_per_capita: Mapped[float | None] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_metrics_county_disaster", "county_fips", "disaster_id", unique=True),
    )
