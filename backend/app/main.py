"""FastAPI application entrypoint."""
import logging
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

import app.core.logging as _log_cfg
from app.core.config import get_settings
from app.api.routes import health, data, analytics, reports
from app.services import cache as cache_svc

_log_cfg.configure()
log = logging.getLogger(__name__)
settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(title=settings.app_name, version="2.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

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
def _startup() -> None:
    cache_svc.get_cache()  # fail fast on misconfigured Redis URL at startup


app.include_router(health.router)
app.include_router(data.router)
app.include_router(analytics.router)
app.include_router(reports.router)
