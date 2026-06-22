"""
FEMA and Census data ingestion.

S3 archival strategy
--------------------
Every successful API response is gzip-compressed and written to S3 before
the records are returned to the pipeline:

    s3://<RAW_BUCKET>/fema/<EndpointName>/YYYY-MM-DD/raw.json.gz
    s3://<RAW_BUCKET>/census/counties/YYYY-MM-DD/raw.json.gz

This "bronze layer" means:
- If the transformation logic has a bug, reprocess from S3 without hitting
  the rate-limited FEMA API again.
- Historical snapshots are available for trend analysis.
- S3 lifecycle transitions to STANDARD_IA after 30 days reduce storage cost.

S3 writes are non-fatal: a boto3 error logs a warning and the pipeline
continues, because failing to archive should never block data loading.
"""
import gzip
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional

import boto3
import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Resolve sample data directory for both local dev and Docker container:
#   Container: __file__ = /app/app/etl/ingest.py → parents[2] = /app → /app/data/sample ✔
#   Local dev:  __file__ = /proj/backend/app/etl/ingest.py → parents[3] = /proj → /proj/data/sample ✔
_etl_dir = Path(__file__).resolve()
_candidate_2 = _etl_dir.parents[2] / "data" / "sample"  # container
_candidate_3 = _etl_dir.parents[3] / "data" / "sample"  # local dev
SAMPLE_DIR = _candidate_2 if _candidate_2.is_dir() else _candidate_3


def _fallback(name: str) -> list:
    path = SAMPLE_DIR / f"{name}.json"
    if path.exists():
        log.warning("Sample fallback used", extra={"ctx_source": name})
        return json.loads(path.read_text())
    return []


def _archive_to_s3(dataset: str, prefix: str, records: list) -> None:
    """
    Write gzip-compressed JSON to S3 raw landing zone.
    No-op when RAW_BUCKET is not configured (local dev / tests).
    """
    bucket = settings.raw_bucket
    if not bucket:
        return
    key = f"{prefix}/{date.today().isoformat()}/raw.json.gz"
    try:
        body = gzip.compress(json.dumps(records).encode("utf-8"), compresslevel=6)
        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentEncoding="gzip",
            ContentType="application/json",
        )
        log.info(
            "S3 archive written",
            extra={"ctx_bucket": bucket, "ctx_key": key, "ctx_records": len(records)},
        )
    except Exception as exc:
        log.warning(
            "S3 archive failed (non-fatal)",
            extra={"ctx_key": key, "ctx_err": str(exc)},
        )


def fetch_fema(
    endpoint: str,
    params: Optional[dict] = None,
    page_size: int = 1000,
) -> list:
    """
    Paginate through FEMA OpenFEMA v2 endpoint with retry/backoff.

    Retry strategy: 3 attempts with exponential backoff (1s, 2s, 4s).
    On total failure, falls back to sample data if USE_SAMPLE_DATA_FALLBACK=true.
    Archives raw response to S3 before returning on success.
    """
    url = f"{settings.fema_base_url}/v2/{endpoint}"
    req_params = {**(params or {}), "$top": page_size, "$skip": 0, "$format": "json"}
    results: list = []

    try:
        with httpx.Client(timeout=30.0) as client:
            while True:
                req_params["$skip"] = len(results)

                for attempt in range(3):
                    try:
                        res = client.get(url, params=req_params)
                        res.raise_for_status()
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(2 ** attempt)

                data = res.json()
                page = data.get(endpoint) or next(
                    (v for v in data.values() if isinstance(v, list)), []
                )
                if not page:
                    break

                results.extend(page)
                log.info(
                    "FEMA page fetched",
                    extra={"ctx_endpoint": endpoint, "ctx_running_total": len(results)},
                )
                if len(page) < page_size:
                    break

        _archive_to_s3(endpoint, f"fema/{endpoint}", results)
        return results

    except Exception as exc:
        log.error(
            "FEMA ingest failed",
            extra={"ctx_endpoint": endpoint, "ctx_err": str(exc)},
        )
        if settings.use_sample_data_fallback:
            return _fallback(endpoint.lower())
        raise


def fetch_census() -> list:
    """
    ACS5 2022 county-level median household income + population.

    Census variable codes:
      B19013_001E = median household income
      B01003_001E = total population
    """
    url = f"{settings.census_base_url}/2022/acs/acs5"
    params: dict = {"get": "NAME,B19013_001E,B01003_001E", "for": "county:*"}
    if settings.census_api_key:
        params["key"] = settings.census_api_key

    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.get(url, params=params)
            res.raise_for_status()
            data = res.json()

        header, *rows = data
        output = []
        for row in rows:
            rec = dict(zip(header, row))
            fips = rec["state"] + rec["county"]
            output.append({
                "fips": fips,
                "name": rec["NAME"],
                "median_income": (
                    float(rec["B19013_001E"])
                    if rec["B19013_001E"] not in (None, "-666666666")
                    else None
                ),
                "population": int(rec["B01003_001E"]) if rec["B01003_001E"] else None,
            })

        _archive_to_s3("census_counties", "census/counties", output)
        return output

    except Exception as exc:
        log.error("Census ingest failed", extra={"ctx_err": str(exc)})
        if settings.use_sample_data_fallback:
            return _fallback("census_counties")
        raise
