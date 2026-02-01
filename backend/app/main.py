"""FastAPI application exposing metrics, counties, correlations, timeseries, outliers."""
import json
import logging
from functools import wraps
from typing import Optional
import redis
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db, init_db
from app.models.db import County, Disaster, Metric
from app.services.analysis import income_gap_correlation

settings = get_settings()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

try:
    cache = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    cache.ping()
except Exception:
    cache = None


def cached(key_fn):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not cache:
                return fn(*args, **kwargs)
            key = key_fn(*args, **kwargs)
            hit = cache.get(key)
            if hit:
                return json.loads(hit)
            result = fn(*args, **kwargs)
            cache.setex(key, settings.cache_ttl_seconds, json.dumps(result, default=str))
            return result
        return wrapper
    return deco


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics(
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
                "disaster_id": m.disaster_id, "county_fips": m.county_fips,
                "county_name": c.name, "state": c.state,
                "response_gap_days": m.response_gap_days,
                "amount_per_capita": m.amount_per_capita,
                "median_income": c.median_income, "is_rural": c.is_rural,
            } for m, c in rows
        ],
    }


@app.get("/counties")
def counties(search: Optional[str] = None, state: Optional[str] = None,
             limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(County)
    if search:
        q = q.filter(County.name.ilike(f"%{search}%"))
    if state:
        q = q.filter(County.state == state.upper())
    return [
        {"fips": c.fips, "name": c.name, "state": c.state,
         "median_income": c.median_income, "population": c.population,
         "is_rural": c.is_rural, "income_percentile": c.income_percentile}
        for c in q.limit(limit).all()
    ]


@app.get("/correlations")
def correlations(db: Session = Depends(get_db)):
    return income_gap_correlation(db)


@app.get("/timeseries")
def timeseries(db: Session = Depends(get_db)):
    sql = text("""
        SELECT EXTRACT(YEAR FROM d.declaration_date)::int AS year,
               AVG(m.response_gap_days) AS avg_gap, COUNT(*) AS n
        FROM metrics m JOIN disasters d ON d.id = m.disaster_id
        WHERE m.response_gap_days IS NOT NULL
        GROUP BY year ORDER BY year
    """)
    return [{"year": r.year, "avg_gap": float(r.avg_gap or 0), "n": r.n}
            for r in db.execute(sql).fetchall()]


@app.get("/outliers")
def outliers(top: int = 25, db: Session = Depends(get_db)):
    rows = (db.query(Metric, County)
              .join(County, County.fips == Metric.county_fips)
              .order_by(Metric.response_gap_days.desc().nullslast())
              .limit(top).all())
    return [{
        "county": c.name, "state": c.state, "fips": c.fips,
        "response_gap_days": m.response_gap_days,
        "median_income": c.median_income, "is_rural": c.is_rural,
        "disaster_id": m.disaster_id,
    } for m, c in rows]


@app.get("/insights")
def insights(db: Session = Depends(get_db)):
    corr = income_gap_correlation(db)
    msgs = []
    if corr.get("pearson_r") is not None:
        direction = "faster" if corr["pearson_r"] < 0 else "slower"
        msgs.append(f"Higher-income counties receive aid {direction} on average (r={corr['pearson_r']:.2f}).")
    if corr.get("rural_mean_gap") and corr.get("urban_mean_gap"):
        diff = corr["rural_mean_gap"] - corr["urban_mean_gap"]
        msgs.append(f"Rural counties wait {diff:+.1f} days longer than urban counties on average.")
    return {"stats": corr, "insights": msgs}
