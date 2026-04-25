"""
Redis cache helpers with versioned keys.

All keys include a version suffix (key:v1) so bumping cache_version in
Settings invalidates every key simultaneously without a separate flush.

Redis unavailability is non-fatal: get() returns None so the caller falls
through to the database, and set() is a no-op. The API continues working
correctly when Redis is down — it just runs without caching.
"""
import json
import logging
from typing import Any

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
        c.delete(*[_vkey(k) for k in keys])
        log.info("Cache invalidated", extra={"ctx_keys": list(keys)})
    except Exception as exc:
        log.warning("Cache invalidate failed", extra={"ctx_err": str(exc)})


# Keys for all analytics endpoints — invalidated together after each ETL run
ANALYTICS_KEYS = ["correlations", "timeseries", "insights", "quintiles", "underserved:25"]


def invalidate_analytics() -> None:
    invalidate(*ANALYTICS_KEYS)
