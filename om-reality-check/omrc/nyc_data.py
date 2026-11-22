"""Thin clients for NYC public data: geocoding and NYC Open Data (Socrata).

All network calls go through `_get_json`, which caches responses on disk for a
day so repeat runs (and tests) don't hammer the city's APIs.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

SOCRATA = "https://data.cityofnewyork.us/resource/{}.json"
GEOSEARCH = "https://geosearch.planninglabs.nyc/v2/search"

DATASETS = {
    "pluto": "64uk-42ks",              # MapPLUTO: lot, building, zoning
    "assessment": "8y4t-faws",         # DOF property valuation & assessment
    "exemptions": "muvi-b6kx",         # DOF property exemption detail
    "exemption_codes": "myn9-hwsy",    # DOF exemption classification codes
    "hpd_violations": "wvxf-dwi5",     # HPD housing maintenance violations
    "hpd_registrations": "tesw-yqqr",  # HPD multiple dwelling registrations
    "ecb_violations": "6bgk-3dad",     # DOB/ECB violations
    "acris_legals": "8h5j-fqxa",       # ACRIS real property legals
    "acris_master": "bnx9-e6tj",       # ACRIS real property master
}

CACHE_DIR = Path(os.environ.get("OMRC_CACHE", Path.home() / ".cache" / "omrc"))
CACHE_TTL = 24 * 3600
APP_TOKEN = os.environ.get("NYC_OPEN_DATA_APP_TOKEN")  # optional, raises rate limits


class DataError(RuntimeError):
    pass


def _get_json(url: str, params: dict) -> Any:
    key = hashlib.sha1((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL:
        return json.loads(path.read_text())
    headers = {"X-App-Token": APP_TOKEN} if APP_TOKEN else {}
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
            return data
        except (requests.RequestException, ValueError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise DataError(f"Request failed: {url} {params}: {last_err}")


def socrata(dataset: str, **params) -> list:
    """Query a NYC Open Data dataset by friendly name, e.g. socrata('pluto', bbl='1...')."""
    ds = DATASETS.get(dataset, dataset)
    return _get_json(SOCRATA.format(ds), params)


def split_bbl(bbl: str) -> tuple:
    bbl = str(bbl)
    return int(bbl[0]), int(bbl[1:6]), int(bbl[6:10])


def geocode(address: str) -> dict:
    """Resolve a free-text NYC address to BBL/BIN using NYC Planning's GeoSearch."""
    data = _get_json(GEOSEARCH, {"text": address, "size": 1})
    feats = data.get("features") or []
    if not feats:
        raise DataError(f"Address not found: {address!r}")
    props = feats[0]["properties"]
    pad = (props.get("addendum") or {}).get("pad") or {}
    if not pad.get("bbl"):
        raise DataError(f"No BBL for address: {address!r}")
    return {
        "label": props.get("label"),
        "bbl": pad["bbl"],
        "bin": pad.get("bin"),
        "borough": props.get("borough"),
        "lat": feats[0]["geometry"]["coordinates"][1],
        "lon": feats[0]["geometry"]["coordinates"][0],
    }


_exemption_code_cache: Optional[dict] = None


def exemption_descriptions() -> dict:
    global _exemption_code_cache
    if _exemption_code_cache is None:
        rows = socrata("exemption_codes", **{"$limit": 5000})
        _exemption_code_cache = {}
        for r in rows:
            _exemption_code_cache.setdefault(r["exempt_code"], r.get("description", ""))
    return _exemption_code_cache
