#!/usr/bin/env python3
"""Read-only verification of public Ibaity sale descriptions."""
from __future__ import annotations

from collections import Counter
from scrape_ibaity import collect

REJECTED_IDS = {"86BCD7", "DC268G"}


def main() -> int:
    records, pages = collect()
    counts = Counter(row["sale_terms_status"] for row in records)
    eligible = [row for row in records if row["price_eligible"]]
    errors = [
        row["id"] for row in eligible
        if row["sale_terms_status"] != "cash" or row["id"] in REJECTED_IDS
    ]
    print("LISTINGS", len(records), "PAGES", pages, "TERMS", dict(counts),
          "PRICE_ELIGIBLE", len(eligible))
    print("EXCLUDED_ZOHOUR", [(row["id"], row["price_exclusion_reason"])
          for row in records if row["id"] in REJECTED_IDS])
    if errors or len(records) < 100 or counts["missing"] > len(records) // 4:
        print("ERROR", errors)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
