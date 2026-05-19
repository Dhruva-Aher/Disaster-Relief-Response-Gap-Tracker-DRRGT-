"""FastAPI application exposing metrics, counties, correlations, timeseries, outliers."""
import logging
import time
from typing import Optional

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.core.logging as _log_cfg
from app.core.config import get_settings
from app.core.database import get_db, init_db
from app.models.db import County, Metric
from app.services import cache as cache_svc
from app.services.analysis import (
    income_gap_correlation,
    income_quintile_analysis,
    disaster_type_analysis,
    regional_equity_analysis,
    underserved_counties,
    temporal_trends,
    multivariable_gap_model,
)

_log_cfg.configure()
log = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Rate-limit middleware is registered BEFORE timing so that timing remains the
# outermost layer and logs every response — including 429s — with a status code.
#
# Algorithm: Redis fixed-window counter (INCR + EXPIRE on first hit).
# Tradeoff vs sliding window: a client can burst 2× the limit across a window
# boundary. Acceptable here — the analytics endpoints are the main concern and
# even a 2× burst (20 req) still can't meaningfully abuse a cached endpoint.
# Fail-open: if Redis is unavailable, requests pass through rather than blocking
# legitimate traffic.
@app.middleware("http")
async def _rate_limit_middleware(request: Request, call_next) -> Response:
    path = request.url.path
    # Health probes and API docs are never rate-limited.
    if path.startswith("/health") or path in ("/docs", "/redoc", "/openapi.json"):
        return await call_next(request)

    ip    = request.client.host if request.client else "unknown"
    is_analytics = path.startswith("/analytics/")
    limit  = settings.rate_limit_analytics if is_analytics else settings.rate_limit_standard
    window = 60
    key    = f"rl:{'analytics' if is_analytics else 'api'}:{ip}"

    c = cache_svc.get_cache()
    if c:
        try:
            count = c.incr(key)
            if count == 1:
                c.expire(key, window)
            if count > limit:
                log.warning(
                    "rate limit exceeded",
                    extra={
                        "ctx_ip": ip,
                        "ctx_path": path,
                        "ctx_count": count,
                        "ctx_limit": limit,
                    },
                )
                return JSONResponse(
                    {"detail": "Rate limit exceeded. Please slow down."},
                    status_code=429,
                    headers={
                        "Retry-After": str(window),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Window": f"{window}s",
                    },
                )
        except Exception as exc:
            log.warning("rate limiter error — failing open", extra={"ctx_err": str(exc)})

    return await call_next(request)


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


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    """Log validation failures so we can spot probing / malformed client bugs."""
    log.warning(
        "request validation failed",
        extra={
            "ctx_path":   request.url.path,
            "ctx_method": request.method,
            "ctx_ip":     request.client.host if request.client else "unknown",
            "ctx_errors": str(exc.errors()),
        },
    )
    return JSONResponse({"detail": exc.errors()}, status_code=422)


@app.on_event("startup")
def _startup():
    init_db()
    cache_svc.get_cache()


@app.get("/status")
def status(db: Session = Depends(get_db)):
    """
    Operational metadata consumed by the frontend status strip.
    Returns row counts and the timestamp of the last completed ETL run.
    Kept separate from /health/deep so ALB probes don't trigger the COUNT
    queries on every health check interval.
    """
    try:
        row = db.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM counties)      AS n_counties,
                (SELECT COUNT(*) FROM disasters)     AS n_disasters,
                (SELECT COUNT(*) FROM disbursements) AS n_disbursements,
                (SELECT COUNT(*) FROM metrics)       AS n_metrics
        """)).fetchone()

        c = cache_svc.get_cache()
        last_etl = None
        if c:
            try:
                last_etl = c.get("etl:last_run")
            except Exception:
                pass

        return {
            "counts": {
                "counties":      int(row.n_counties or 0),
                "disasters":     int(row.n_disasters or 0),
                "disbursements": int(row.n_disbursements or 0),
                "metrics":       int(row.n_metrics or 0),
            },
            "last_etl":  last_etl,
            "cache":     "connected" if c else "unavailable",
        }
    except Exception as exc:
        log.warning("status endpoint error", extra={"ctx_err": str(exc)})
        return {"counts": {}, "last_etl": None, "cache": "unknown"}


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
             limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
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


@app.get("/analytics/quintiles")
def quintiles(db: Session = Depends(get_db)):
    """Income quintile breakdown of average response gap."""
    hit = cache_svc.get("quintiles")
    if hit is not None:
        return hit
    result = income_quintile_analysis(db)
    cache_svc.set("quintiles", result)
    return result


@app.get("/analytics/disaster-types")
def disaster_types(db: Session = Depends(get_db)):
    """Median response gap stratified by FEMA incident type."""
    hit = cache_svc.get("disaster_types")
    if hit is not None:
        return hit
    result = disaster_type_analysis(db)
    cache_svc.set("disaster_types", result)
    return result


@app.get("/analytics/regional")
def regional(db: Session = Depends(get_db)):
    """Average gap and income by FEMA administrative region."""
    hit = cache_svc.get("regional")
    if hit is not None:
        return hit
    result = regional_equity_analysis(db)
    cache_svc.set("regional", result)
    return result


@app.get("/analytics/underserved")
def underserved(top: int = Query(25, le=100), db: Session = Depends(get_db)):
    """Counties with the highest composite underserved score."""
    key = f"underserved:{top}"
    hit = cache_svc.get(key)
    if hit is not None:
        return hit
    result = underserved_counties(db, top_n=top)
    cache_svc.set(key, result)
    return result


@app.get("/analytics/trends")
def trends(db: Session = Depends(get_db)):
    """Year-over-year response gap trends with rural/urban split."""
    hit = cache_svc.get("trends")
    if hit is not None:
        return hit
    result = temporal_trends(db)
    cache_svc.set("trends", result)
    return result


@app.get("/analytics/model")
def gap_model(db: Session = Depends(get_db)):
    """Ridge regression model of log(response_gap) on income, rurality, and FEMA region."""
    hit = cache_svc.get("model")
    if hit is not None:
        return hit
    result = multivariable_gap_model(db)
    cache_svc.set("model", result)
    return result


@app.get("/outliers")
def outliers(top: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)):
    """
    Worst counties by average response gap, deduplicated by county.

    Previous version returned one row per metric row, so a county that
    appeared in many disasters would dominate the table. This query
    aggregates per county so the top-N list is actually diverse.
    """
    key = f"outliers:{top}"
    hit = cache_svc.get(key)
    if hit is not None:
        return hit

    sql = text("""
        SELECT c.fips, c.name, c.state, c.median_income, c.is_rural,
               ROUND(AVG(m.response_gap_days)::numeric, 1) AS avg_gap,
               MAX(m.response_gap_days)                    AS worst_gap,
               COUNT(*)                                    AS disaster_count
        FROM metrics m JOIN counties c ON c.fips = m.county_fips
        WHERE m.response_gap_days BETWEEN 0 AND 730
        GROUP BY c.fips, c.name, c.state, c.median_income, c.is_rural
        ORDER BY avg_gap DESC NULLS LAST
        LIMIT :top
    """)
    rows = db.execute(sql, {"top": top}).fetchall()
    result = [
        {
            "county":          r.name,
            "state":           r.state,
            "fips":            r.fips,
            "response_gap_days": float(r.avg_gap),
            "worst_gap":       int(r.worst_gap),
            "disaster_count":  int(r.disaster_count),
            "median_income":   r.median_income,
            "is_rural":        r.is_rural,
        }
        for r in rows
    ]
    cache_svc.set(key, result)
    return result


@app.get("/insights")
def insights(db: Session = Depends(get_db)):
    hit = cache_svc.get("insights")
    if hit is not None:
        return hit
    corr = income_gap_correlation(db)
    msgs = []
    r = corr.get("spearman_r")
    if r is not None:
        direction = "faster" if r < 0 else "slower"
        msgs.append(f"Higher-income counties receive aid {direction} on average (Spearman ρ={r:.3f}, p={corr.get('p_value', '?')}).")
    if corr.get("rural_mean_gap") and corr.get("urban_mean_gap"):
        diff = corr["rural_mean_gap"] - corr["urban_mean_gap"]
        msgs.append(f"Rural counties wait {diff:+.1f} days longer than urban counties on average.")
    result = {"stats": corr, "insights": msgs}
    cache_svc.set("insights", result)
    return result
