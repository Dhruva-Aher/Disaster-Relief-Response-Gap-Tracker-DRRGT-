"""FastAPI application exposing metrics, counties, correlations, timeseries, outliers."""
import logging
import time
from typing import Optional

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.core.logging as _log_cfg
from app.core.config import get_settings
from app.core.database import get_db, init_db
from app.models.db import County, Metric
from app.services import cache as cache_svc
from app.services.analysis import income_gap_correlation

_log_cfg.configure()
log = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _timing_middleware(request: Request, call_next) -> Response:
    t0 = time.perf_counter()
    response: Response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    response.headers["X-Response-Time-Ms"] = f"{ms:.1f}"
    log.info(
        "request",
        extra={
            "ctx_method": request.method,
            "ctx_path": request.url.path,
            "ctx_status": response.status_code,
            "ctx_ms": round(ms, 1),
        },
    )
    return response


@app.on_event("startup")
def _startup():
    init_db()
    cache_svc.get_cache()


@app.get("/health")
def health():
    """Shallow liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}


@app.get("/health/deep")
def health_deep(db: Session = Depends(get_db)):
    """
    Deep readiness probe used by the ALB health check.

    Returns 503 if PostgreSQL is unreachable so the load balancer stops
    routing traffic to this container until the check recovers.
    """
    from fastapi.responses import JSONResponse
    checks: dict[str, str] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"
        log.error("DB health check failed", extra={"ctx_err": str(exc)})

    try:
        c = cache_svc.get_cache()
        checks["redis"] = "ok" if c else "unavailable"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    db_ok = checks.get("db") == "ok"
    return JSONResponse(
        {"status": "ok" if db_ok else "degraded", "checks": checks},
        status_code=200 if db_ok else 503,
    )


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
    hit = cache_svc.get("correlations")
    if hit is not None:
        return hit
    result = income_gap_correlation(db)
    cache_svc.set("correlations", result)
    return result


@app.get("/timeseries")
def timeseries(db: Session = Depends(get_db)):
    hit = cache_svc.get("timeseries")
    if hit is not None:
        return hit
    sql = text("""
        SELECT EXTRACT(YEAR FROM d.declaration_date)::int AS year,
               AVG(m.response_gap_days) AS avg_gap, COUNT(*) AS n
        FROM metrics m JOIN disasters d ON d.id = m.disaster_id
        WHERE m.response_gap_days IS NOT NULL
        GROUP BY year ORDER BY year
    """)
    result = [{"year": r.year, "avg_gap": round(float(r.avg_gap or 0), 1), "n": r.n}
              for r in db.execute(sql).fetchall()]
    cache_svc.set("timeseries", result)
    return result


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
    hit = cache_svc.get("insights")
    if hit is not None:
        return hit
    corr = income_gap_correlation(db)
    msgs = []
    if corr.get("pearson_r") is not None:
        direction = "faster" if corr["pearson_r"] < 0 else "slower"
        msgs.append(f"Higher-income counties receive aid {direction} on average (r={corr['pearson_r']:.2f}).")
    if corr.get("rural_mean_gap") and corr.get("urban_mean_gap"):
        diff = corr["rural_mean_gap"] - corr["urban_mean_gap"]
        msgs.append(f"Rural counties wait {diff:+.1f} days longer than urban counties on average.")
    result = {"stats": corr, "insights": msgs}
    cache_svc.set("insights", result)
    return result
