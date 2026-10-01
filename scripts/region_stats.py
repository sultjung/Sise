#!/usr/bin/env python3
"""Baghdad district prices from approved Ibaity apartment listings.

The region metric is the median of each mapped complex's listing-price median.
This gives each complex one vote and matches the dashboard's regional map,
trend and workbook. Missing samples remain missing.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
from pathlib import Path
from typing import Any

REGION_GROUPS = {
    "mansour": ("mansour_city", "iraq_gate", "palm_towers", "royal_city"),
    "saydiya": ("baghdad_marina",),
    "kadhimiya": ("jawahir_dijla",),
    "jihad": ("nasim_city",),
    "amiriya": ("al_wud", "millennium"),
    "yarmouk": ("yarmouk_compound",),
    "bismayah": ("bismayah_complex",),
    "karrada": ("DECCG8",),
    "newbaghdad": ("D58DG8",),
    "zayouna": ("2E44F6",),
}
ALL_REGION_KEYS = (
    "mansour", "jadriya", "harthiya", "karrada", "yarmouk",
    "kadhimiya", "zayouna", "newbaghdad", "amiriya", "saydiya",
    "jihad", "sadrcity", "bismayah",
)
HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "region-history.json"


def _created(record: dict[str, Any]) -> dt.datetime | None:
    try:
        value = dt.datetime.fromisoformat(str(record.get("created_at") or "").replace("Z", "+00:00"))
        return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value
    except ValueError:
        return None


def _price(record: dict[str, Any]) -> int | None:
    value = record.get("price_per_m2_iqd") or record.get("calculated_price_per_m2_iqd")
    return round(value) if isinstance(value, (float, int)) and value > 0 else None


def summarize_region(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    eligible = [row for row in records if row.get("price_eligible") is not False and _price(row)]
    result: dict[str, dict[str, Any]] = {}
    for region in ALL_REGION_KEYS:
        groups = REGION_GROUPS.get(region, ())
        by_group: dict[str, list[dict[str, Any]]] = {}
        for row in eligible:
            key = str(row.get("complex_key") or "")
            complex_id = str(row.get("complex_id") or "")
            group = key if key in groups else complex_id if complex_id in groups else None
            if group:
                by_group.setdefault(group, []).append(row)
        rows = [row for group_rows in by_group.values() for row in group_rows]
        prices = [_price(row) for row in rows]
        complex_medians = [statistics.median(_price(row) for row in group_rows) for group_rows in by_group.values()]
        result[region] = {
            "price_per_m2_iqd": round(statistics.median(complex_medians)) if complex_medians else None,
            "sample_count": len(rows),
            "complex_count": len(by_group),
            "min_price_per_m2_iqd": min(prices) if prices else None,
            "max_price_per_m2_iqd": max(prices) if prices else None,
            "listing_ids": [row["id"] for row in rows],
        }
    return result


def region_quarters(records: list[dict[str, Any]], observed_at: str) -> dict[str, dict[str, Any]]:
    observed_date = dt.date.fromisoformat(observed_at)
    by_quarter: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        created = _created(row)
        if not created or created.date() >= observed_date:
            continue
        quarter = (created.month - 1) // 3 + 1
        next_month = quarter * 3 + 1
        close_date = dt.date(created.year + (next_month == 13), 1 if next_month == 13 else next_month, 1)
        if close_date <= observed_date:
            by_quarter.setdefault(f"{created.year}-q{quarter}", []).append(row)
    return {quarter: summarize_region(rows) for quarter, rows in sorted(by_quarter.items())}


def append_region_history(snapshot: dict[str, Any]) -> None:
    observed_at = snapshot["updated_at"]
    try:
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            history = []
    except (FileNotFoundError, json.JSONDecodeError):
        history = []
    previous = next((row for row in history if str(row.get("date", "")).startswith(observed_at[:7]) and row.get("status") == "verified_snapshot"), None)
    history = [row for row in history if not str(row.get("date", "")).startswith(observed_at[:7])]
    history.append({
        "date": observed_at,
        "status": "verified_snapshot",
        "source": "ibaity.com 승인 활성 매매 아파트",
        "method": "지역 내 단지별 매물 m² 단가 중앙값의 중앙값; 조건부 가격 제외; 표본 수 병기",
        "by_region": snapshot["by_region"],
        "by_quarter": {**snapshot["by_region_quarter"], **(previous or {}).get("by_quarter", {})},
    })
    history.sort(key=lambda row: str(row.get("date", "")))
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
