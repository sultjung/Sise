#!/usr/bin/env python3
"""Validate generated market-price JSON before it is committed by Actions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "data" / "latest.json"


def fail(message: str) -> None:
    print(f"[validate] {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    try:
        data = json.loads(LATEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"latest.json cannot be read: {exc}")

    if data.get("schema_version") != 2:
        fail("unsupported schema_version")
    if data.get("price_basis_code") != "private_resale_asking_price":
        fail("latest data must be explicitly marked as private-market asking prices")
    if data.get("includes_nic_direct_allocation_price") is not False:
        fail("NIC direct-allocation prices must not be mixed into market data")
    if not isinstance(data.get("districts"), dict) or not isinstance(data.get("complexes"), dict):
        fail("districts/complexes must be objects")
    pending_first_collection = data.get("collection", {}).get("status") == "pending_first_collection"
    if not data.get("period") or not data.get("generated_at"):
        if pending_first_collection and not data.get("period") and not data.get("generated_at"):
            print("[validate] OK · pending first collection")
            return
        fail("period/generated_at missing")

    warnings = 0
    for group_name in ("districts", "complexes"):
        for key, item in data[group_name].items():
            count = item.get("sample_count", 0)
            price = item.get("published_price_per_m2_iqd")
            if not isinstance(count, int) or count < 0:
                fail(f"{group_name}.{key}: invalid sample_count")
            if price is not None and not 100_000 <= price <= 10_000_000:
                fail(f"{group_name}.{key}: implausible published unit price {price}")
            if item.get("publishable") and count < data.get("minimum_publish_samples", 3):
                fail(f"{group_name}.{key}: marked publishable with too few samples")
            if item.get("review_required"):
                warnings += 1
                print(f"[validate] warning: {group_name}.{key} changed sharply; previous published value retained")

    print(f"[validate] OK · districts={len(data['districts'])}, complexes={len(data['complexes'])}, review_warnings={warnings}")


if __name__ == "__main__":
    main()
