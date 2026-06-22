import io
import csv
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.db import County, Metric
from app.models.domain import MetricsResponse, CountyBase, OutlierItem

router = APIRouter(tags=["data"])

@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    state: Optional[str] = None,
    min_gap: Optional[int] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Metric, County).join(County, County.fips == Metric.county_fips)
    if state:
        q = q.filter(County.state == state.upper())
    if min_gap is not None:
        q = q.filter(Metric.response_gap_days >= min_gap)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "disaster_id": m.disaster_id,
                "county_fips": m.county_fips,
                "county_name": c.name,
                "state": c.state,
                "response_gap_days": m.response_gap_days,
                "amount_per_capita": m.amount_per_capita,
                "median_income": c.median_income,
                "is_rural": c.is_rural,
            }
            for m, c in rows
        ],
    }

@router.get("/counties", response_model=List[CountyBase])
def get_counties(
    search: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(County)
    if search:
        q = q.filter(County.name.ilike(f"%{search}%"))
    if state:
        q = q.filter(County.state == state.upper())
    return q.limit(limit).all()

@router.get("/outliers", response_model=List[OutlierItem])
def get_outliers(top: int = Query(25, le=100), db: Session = Depends(get_db)):
    rows = (
        db.query(Metric, County)
        .join(County, County.fips == Metric.county_fips)
        .order_by(Metric.response_gap_days.desc().nullslast())
        .limit(top)
        .all()
    )
    return [
        {
            "county": c.name, "state": c.state, "fips": c.fips,
            "response_gap_days": m.response_gap_days,
            "median_income": c.median_income, "is_rural": c.is_rural,
            "disaster_id": m.disaster_id,
        }
        for m, c in rows
    ]

# Export endpoints

def _to_csv(data: list[dict], filename: str) -> Response:
    if not data:
        return Response("No data", status_code=204)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "text/csv"
    }
    return Response(content=output.getvalue(), headers=headers)

@router.get("/export/counties")
def export_counties(format: str = Query("csv", pattern="^(csv|json)$"), db: Session = Depends(get_db)):
    rows = db.query(County).all()
    data = [
        {
            "fips": c.fips, "name": c.name, "state": c.state,
            "population": c.population, "median_income": c.median_income,
            "is_rural": c.is_rural
        }
        for c in rows
    ]
    if format == "json":
        return data
    return _to_csv(data, "counties.csv")

@router.get("/export/outliers")
def export_outliers(format: str = Query("csv", pattern="^(csv|json)$"), db: Session = Depends(get_db)):
    rows = (
        db.query(Metric, County)
        .join(County, County.fips == Metric.county_fips)
        .order_by(Metric.response_gap_days.desc().nullslast())
        .limit(100)
        .all()
    )
    data = [
        {
            "county": c.name, "state": c.state, "fips": c.fips,
            "response_gap_days": m.response_gap_days,
            "median_income": c.median_income, "is_rural": c.is_rural,
            "disaster_id": m.disaster_id,
        }
        for m, c in rows
    ]
    if format == "json":
        return data
    return _to_csv(data, "outliers.csv")

@router.get("/export/states")
def export_states(format: str = Query("csv", pattern="^(csv|json)$"), db: Session = Depends(get_db)):
    # Group metrics by state
    rows = (
        db.query(
            County.state,
            func.avg(Metric.response_gap_days).label("avg_gap_days"),
            func.count(Metric.id).label("disaster_count")
        )
        .join(Metric, County.fips == Metric.county_fips)
        .group_by(County.state)
        .all()
    )
    data = [
        {"state": r.state, "avg_gap_days": round(r.avg_gap_days, 1) if r.avg_gap_days else None, "disaster_count": r.disaster_count}
        for r in rows
    ]
    if format == "json":
        return data
    return _to_csv(data, "states.csv")
