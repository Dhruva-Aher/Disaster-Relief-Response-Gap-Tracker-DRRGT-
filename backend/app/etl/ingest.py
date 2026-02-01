import logging
import time
from pathlib import Path
import json
import httpx
from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

SAMPLE_DIR = Path(__file__).resolve().parents[3] / "data" / "sample"


def _fallback(name: str):
    path = SAMPLE_DIR / f"{name}.json"
    if path.exists():
        log.warning(f"Fallback used for {name}")
        return json.loads(path.read_text())
    return []


def fetch_fema(endpoint: str, params=None, page_size=1000):
    url = f"{settings.fema_base_url}/v2/{endpoint}"
    params = {**(params or {}), "$top": page_size, "$skip": 0, "$format": "json"}

    results = []
    skip = 0

    try:
        with httpx.Client(timeout=30.0) as client:
            while True:
                params["$skip"] = skip

                for attempt in range(3):
                    try:
                        res = client.get(url, params=params)
                        res.raise_for_status()
                        break
                    except Exception:
                        time.sleep(2 ** attempt)
                else:
                    raise Exception("FEMA API failed")

                data = res.json()
                records = data.get(endpoint) or next(
                    (v for v in data.values() if isinstance(v, list)), []
                )

                if not records:
                    break

                results.extend(records)

                if len(records) < page_size:
                    break

                skip += page_size

        log.info(f"Fetched {len(results)} records from {endpoint}")
        return results

    except Exception as e:
        log.error(f"FEMA ingest failed: {e}")
        if settings.use_sample_data_fallback:
            return _fallback(endpoint.lower())
        raise


def fetch_census():
    url = f"{settings.census_base_url}/2022/acs/acs5"

    params = {
        "get": "NAME,B19013_001E,B01003_001E",
        "for": "county:*"
    }

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
                "median_income": float(rec["B19013_001E"]) if rec["B19013_001E"] not in (None, "-666666666") else None,
                "population": int(rec["B01003_001E"]) if rec["B01003_001E"] else None
            })

        return output

    except Exception as e:
        log.error(f"Census failed: {e}")
        if settings.use_sample_data_fallback:
            return _fallback("census_counties")
        raise