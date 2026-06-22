"""
Redis cache helpers.

Design decisions:
- All keys are versioned (key:v2) so bumping cache_version in Settings busts
  every key simultaneously without a separate flush step.
- Redis unavailability is non-fatal: get() returns None, set() is a no-op.
  The API falls through to the database on every cache miss when Redis is down.
- invalidate_analytics() is called at the end of every ETL run so the first
  request after a pipeline run recomputes from fresh data.
"""
import json
import logging
from typing import Any, Callable

import redis as redis_lib

from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

_client: redis_lib.Redis | None = None


def get_cache() -> redis_lib.Redis | None:
    global _client
    if _client is not None:
        return _client
    try:
        c = redis_lib.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        c.ping()
        _client = c
        log.info("Redis connected", extra={"ctx_url": settings.redis_url})
    except Exception as exc:
        log.warning("Redis unavailable — cache disabled", extra={"ctx_err": str(exc)})
        _client = None
    return _client


def _vkey(name: str) -> str:
    return f"{name}:{settings.cache_version}"


def get(key: str) -> Any | None:
    c = get_cache()
    if not c:
        return None
    try:
        raw = c.get(_vkey(key))
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        log.warning("Cache get failed", extra={"ctx_key": key, "ctx_err": str(exc)})
        return None


def set(key: str, value: Any, ttl: int | None = None) -> None:
    c = get_cache()
    if not c:
        return
    try:
        c.setex(_vkey(key), ttl or settings.cache_ttl_seconds, json.dumps(value, default=str))
    except Exception as exc:
        log.warning("Cache set failed", extra={"ctx_key": key, "ctx_err": str(exc)})


def invalidate(*keys: str) -> None:
    c = get_cache()
    if not c:
        return
    try:
        versioned = [_vkey(k) for k in keys]
        c.delete(*versioned)
        log.info("Cache invalidated", extra={"ctx_keys": list(keys)})
    except Exception as exc:
        log.warning("Cache invalidate failed", extra={"ctx_err": str(exc)})


# All keys touched by analytics endpoints — invalidated together after each ETL run
ANALYTICS_KEYS = [
    "correlations",
    "timeseries",
    "insights",
    "quintiles",
    "disaster_types",
    "regional",
    "underserved_30",
    "trends",
    "model",
]


def invalidate_analytics() -> None:
    invalidate(*ANALYTICS_KEYS)
