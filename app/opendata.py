from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR


PACKAGE_URL = (
    "https://admin.opendata.az/api/3/action/package_show"
    "?id=stansiyalar-uzre-gundelik-sernisin-gedislerinin-sayi"
)
CACHE_PATH = DATA_DIR / "opendata_station_cache.json"
CACHE_TTL = timedelta(hours=12)

OPENDATA_STATION_MAP = {
    "20 yanvar": "twenty-yanvar",
    "28 may": "may28",
    "8 noyabr": "eight-noyabr",
    "akhmedli": "ahmedli",
    "avtovaghzal": "avtovagzal",
    "ganjlik": "ganclik",
    "hazi aslanov": "hazi-aslanov",
    "icherisheher": "iceri-seher",
    "inshaatchilar": "inshaatcilar",
    "jafar jabbarli": "jafar-jabbarli",
    "khatai": "khatai",
    "koroghlu": "koroglu",
    "memar ajami": "memar-ecemi",
    "nariman narimanov": "narimanov",
    "nizami": "nizami",
    "sahil": "sahil",
    "ulduz": "ulduz",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_station_name(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_value).strip()


def _read_cache() -> dict[str, Any] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_is_fresh(cache: dict[str, Any]) -> bool:
    fetched_at = cache.get("fetched_at")
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except ValueError:
        return False
    return (_utc_now() - fetched) < CACHE_TTL


def _download_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read().decode("utf-8-sig")


def _aggregate_station_entries(resources: list[dict[str, Any]]) -> dict[str, Any]:
    station_daily: dict[tuple[str, str], int] = {}
    latest_date: str | None = None

    for resource in resources:
        if str(resource.get("format", "")).upper() != "CSV":
            continue
        resource_url = resource.get("url")
        if not resource_url:
            continue

        reader = csv.reader(io.StringIO(_download_text(resource_url)), delimiter=";")
        next(reader, None)

        for row in reader:
            if len(row) < 3:
                continue

            date_key = row[0].split(" ")[0]
            station_name = row[1].strip().strip('"')
            normalized_name = _normalize_station_name(station_name)
            if not normalized_name:
                continue

            try:
                count = int(str(row[2]).replace(",", "").strip())
            except ValueError:
                continue

            station_daily[(date_key, normalized_name)] = station_daily.get((date_key, normalized_name), 0) + count
            if latest_date is None or date_key > latest_date:
                latest_date = date_key

    station_entries: dict[str, dict[str, Any]] = {}
    if latest_date is None:
        return {"latest_date": None, "station_entries": station_entries}

    for (date_key, normalized_name), total in station_daily.items():
        if date_key != latest_date:
            continue
        station_id = OPENDATA_STATION_MAP.get(normalized_name)
        if not station_id:
            continue
        station_entries[station_id] = {
            "daily_entries": total,
            "source_name": normalized_name,
        }

    return {"latest_date": latest_date, "station_entries": station_entries}


def _default_payload() -> dict[str, Any]:
    return {
        "source": "seed",
        "latest_date": None,
        "package_modified": None,
        "station_entries": {},
        "fetched_at": _utc_now().isoformat(),
        "cache_status": "unavailable",
    }


def get_latest_station_entries() -> dict[str, Any]:
    cache = _read_cache()
    if cache and _cache_is_fresh(cache):
        return cache

    try:
        package_data = _download_json(PACKAGE_URL)
        resources = package_data.get("result", {}).get("resources", [])
        aggregated = _aggregate_station_entries(resources)
        payload = {
            "source": "opendata.az",
            "latest_date": aggregated["latest_date"],
            "package_modified": package_data.get("result", {}).get("metadata_modified"),
            "station_entries": aggregated["station_entries"],
            "fetched_at": _utc_now().isoformat(),
            "cache_status": "fresh",
            "package_url": PACKAGE_URL,
        }
        _write_cache(payload)
        return payload
    except Exception:
        if cache:
            cache["cache_status"] = "stale"
            return cache
        return _default_payload()
