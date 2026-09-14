#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect Baghdad apartment asking prices from ibaity's public client API.

The API returns approved sale listings in pages of ten.  This collector walks
all pages, keeps only usable apartment sale records, removes duplicate listing
IDs, groups listings by the provider's residential-complex name, and writes a
privacy-safe snapshot for the SISE dashboard.
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_BASE = "https://v3.ibaity.com/api/client/Realestate"
PAGE_SIZE = 10
MAX_PAGES = 500
REQUEST_DELAY_SEC = 0.35
TIMEOUT_SEC = 30
CURRENT_WINDOW_DAYS = 90
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "ibaity-latest.json"

COMPLEX_KEY_BY_AR = {
    "المنصور ستي": "mansour_city",
    "بغداد مارينا": "baghdad_marina",
    "مدينة النسيم السكنية": "nasim_city",
    "دار السلام السكني": "dar_alsalam",
    "مجمع ابراج النخلة السكني": "palm_towers",
    "مجمع أبراج النخلة السكني": "palm_towers",
    "جواهر دجلة": "jawahir_dijla",
    "مجمع الود السكني": "al_wud",
}

COMPLEX_KEY_BY_PROVIDER_NAME = {
    "almnswr sty": "mansour_city",
    "bghdad maryna": "baghdad_marina",
    "alnsym a residential city": "nasim_city",
    "dar alslam residential": "dar_alsalam",
    "abraj alnkhla residential complex": "palm_towers",
    "royal city residential complex": "royal_city",
    "jwahr djla residential complex": "jawahir_dijla",
    "alwd residential complex": "al_wud",
    "mylynywm residential towers": "millennium",
    "alyrmwk residential complex": "yarmouk_compound",
    "alymama city": "yamama_city",
    "bsmaya residential": "bismayah_complex",
    "bwaba alaraq residential": "iraq_gate",
    "bwaba alaraq alb ra district": "iraq_gate",
}

PARAMS = {
    "PageSize": PAGE_SIZE,
    "offerType": "SELL",
    "CityId": "G76HDC",
    "CategoryId": "C8D46D",
    "SubCategoryId": "DEG8GH",
}

HEADERS = {
    "User-Agent": "SISE-Ibaity-Collector/1.0 (+https://sultjung.github.io/Sise/)",
    "Accept": "application/json",
    "Accept-Language": "ar,en;q=0.8",
}


def api_url(page: int) -> str:
    query = dict(PARAMS)
    query["PageNumber"] = page
    return f"{API_BASE}?{urlencode(query)}"


def detail_url(listing_id: str) -> str:
    return f"https://ibaity.com/realestate/{listing_id}?searchCountry=IQ&currency=IQD"


def fetch_page(page: int) -> list[dict[str, Any]]:
    request = Request(api_url(page), headers=HEADERS, method="GET")
    with urlopen(request, timeout=TIMEOUT_SEC) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("success") is not True:
        raise RuntimeError(f"ibaity API returned success={body.get('success')!r}")
    payload = body.get("payload")
    return payload if isinstance(payload, list) else []


def clean_listing(item: dict[str, Any], observed_at: str) -> dict[str, Any] | None:
    if item.get("offerType") != "SELL" or item.get("status") != "APPROVED":
        return None
    if item.get("isSold") is True or item.get("isExpired") is True:
        return None
    price = item.get("price")
    area = item.get("area")
    per_meter = item.get("perMeter")
    if not isinstance(price, (int, float)) or price <= 0:
        return None
    if not isinstance(area, (int, float)) or area <= 0:
        return None
    calculated = round(price / area)
    if not isinstance(per_meter, (int, float)) or per_meter <= 0:
        per_meter = calculated
    # Keep only non-sensitive fields. Do not write owner names, phones or IDs.
    complex_info = item.get("buildingComplexGroup") or {}
    district = item.get("district") or {}
    subdistrict = item.get("subDistrict") or {}
    images = item.get("images") or []
    return {
        "id": str(item.get("id") or ""),
        "observed_at": observed_at,
        "created_at": item.get("createdAt"),
        "expires_at": item.get("expiresAt"),
        "title": item.get("title"),
        "price_iqd": round(price),
        "area_m2": round(area, 2),
        "price_per_m2_iqd": round(per_meter),
        "calculated_price_per_m2_iqd": calculated,
        "bedrooms": item.get("noOfBedRooms"),
        "bathrooms": item.get("noOfBathRooms"),
        "lat": item.get("lat"),
        "lng": item.get("lng"),
        "complex_id": complex_info.get("id"),
        "complex_name_ar": complex_info.get("name"),
        "complex_key": COMPLEX_KEY_BY_AR.get(complex_info.get("name")) or COMPLEX_KEY_BY_PROVIDER_NAME.get(str(complex_info.get("name") or "").strip().lower()),
        "district_ar": district.get("name"),
        "subdistrict_ar": subdistrict.get("name"),
        "image": images[0] if images else item.get("image"),
        "source_url": detail_url(str(item.get("id") or "")),
        "source_api_url": api_url(1),
    }


def collect() -> tuple[list[dict[str, Any]], int]:
    observed_at = dt.datetime.now(dt.timezone.utc).date().isoformat()
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    pages = 0
    for page in range(1, MAX_PAGES + 1):
        payload = fetch_page(page)
        pages = page
        if not payload:
            break
        for item in payload:
            record = clean_listing(item, observed_at)
            if record and record["id"] and record["id"] not in seen_ids:
                seen_ids.add(record["id"])
                record["source_api_url"] = api_url(page)
                records.append(record)
        if len(payload) < PAGE_SIZE:
            break
        time.sleep(REQUEST_DELAY_SEC)
    return records, pages


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = record.get("complex_id") or f"unmapped:{record.get('complex_name_ar') or 'unknown'}"
        groups.setdefault(key, []).append(record)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=CURRENT_WINDOW_DAYS)

    def is_current(record: dict[str, Any]) -> bool:
        value = record.get("created_at")
        if not value:
            return False
        try:
            created = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return False
        return created >= cutoff

    result: dict[str, Any] = {}
    for key, items in sorted(groups.items()):
        current_items = [x for x in items if is_current(x)]
        prices = [x["price_per_m2_iqd"] for x in current_items]
        all_prices = [x["price_per_m2_iqd"] for x in items]
        latest_created_at = max((x.get("created_at") for x in items if x.get("created_at")), default=None)
        result[key] = {
            "complex_key": next((x.get("complex_key") for x in items if x.get("complex_key")), None),
            "complex_id": items[0].get("complex_id"),
            "complex_name_ar": items[0].get("complex_name_ar"),
            "district_ar": items[0].get("district_ar"),
            "subdistricts_ar": sorted({x.get("subdistrict_ar") for x in items if x.get("subdistrict_ar")}),
            "median_price_per_m2_iqd": round(statistics.median(prices)) if prices else None,
            "min_price_per_m2_iqd": min(prices) if prices else None,
            "max_price_per_m2_iqd": max(prices) if prices else None,
            "sample_count": len(current_items),
            "all_sample_count": len(items),
            "all_median_price_per_m2_iqd": round(statistics.median(all_prices)),
            "current_window_days": CURRENT_WINDOW_DAYS,
            "latest_created_at": latest_created_at,
            "listing_ids": [x["id"] for x in current_items],
            "all_listing_ids": [x["id"] for x in items],
        }
    return result


def main() -> int:
    observed_at = dt.datetime.now(dt.timezone.utc).date().isoformat()
    try:
        records, pages = collect()
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
        print(f"[ERROR] ibaity collection failed: {exc}", file=sys.stderr)
        return 2
    if not records:
        print("[ERROR] no valid ibaity listings returned; existing snapshot preserved", file=sys.stderr)
        return 2
    output = {
        "schema_version": "1.0",
        "updated_at": observed_at,
        "source": "ibaity.com public client API",
        "api": API_BASE,
        "query": PARAMS,
        "pages_collected": pages,
        "listing_count": len(records),
        "method": f"APPROVED, active SELL apartment listings; current median uses listings created in the last {CURRENT_WINDOW_DAYS} days; duplicate IDs removed",
        "by_complex": summarize(records),
        "listings": records,
    }
    OUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {len(records)} valid listings from {pages} pages → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
