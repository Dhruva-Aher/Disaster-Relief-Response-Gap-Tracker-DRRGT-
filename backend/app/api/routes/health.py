import logging
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import cache as cache_svc
from app.core.config import get_settings

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)
settings = get_settings()

@router.get("/health")
def health():
    """Shallow liveness probe — returns 200 if the process is running."""
    return {"status": "ok"}

@router.get("/health/deep")
def health_deep(db: Session = Depends(get_db)):
    """Deep readiness probe used by the ALB health check."""
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
        {
            "status": "ok" if db_ok else "degraded",
            "checks": checks,
            "cache_version": settings.cache_version,
        },
        status_code=200 if db_ok else 503,
    )
