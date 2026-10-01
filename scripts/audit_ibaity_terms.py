#!/usr/bin/env python3
"""Read public Ibaity listing descriptions for cash-sale screening."""
from __future__ import annotations

import concurrent.futures
import html
import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "ibaity-latest.json"
FINANCING = re.compile(r"قرض|قسط|اقساط|أقساط|مصرف|كفيل|تبديل|تنازل|مقدم|متبقي|متبقى|باقي|واصل|دفعة|دفعه|شهري|تسديد|loan|installment|mortgage|down.payment|remaining|monthly.payment|bank.finance", re.I)
CASH = re.compile(r"نقدا|نقداً|كاش|cash|خالي.من.الأقساط|خالي.من.الاقساط|مسدد.بالكامل|fully.paid", re.I)


class DescriptionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.parts = []
        self.found = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.depth:
            self.depth += 1
        elif tag == "p" and "line-clamp-3" in attrs.get("class", ""):
            self.depth = 1
            self.found = True

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)


def inspect(row):
    listing_id = row["id"]
    req = Request(row["source_url"], headers={"User-Agent": "Mozilla/5.0 (compatible; SisePriceAudit/1.0)", "Accept-Language": "ar,en;q=0.8"})
    for attempt in range(2):
        try:
            with urlopen(req, timeout=20) as response:
                body = response.read(1_000_000).decode("utf-8", "replace")
            parser = DescriptionParser()
            parser.feed(body)
            description = html.unescape(" ".join(parser.parts))
            if not parser.found or not description.strip():
                return listing_id, "missing", "", row.get("price_eligible", False)
            markers = sorted(set(m.group(0) for m in FINANCING.finditer(description)))
            status = "finance" if markers else "cash" if CASH.search(description) else "unspecified"
            return listing_id, status, ",".join(markers)[:100], row.get("price_eligible", False)
        except (HTTPError, URLError, TimeoutError, ValueError):
            if attempt == 0:
                time.sleep(1)
    return listing_id, "error", "", row.get("price_eligible", False)


def main():
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["listings"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(inspect, rows))
    counts = {}
    for _, status, _, eligible in results:
        counts[(status, bool(eligible))] = counts.get((status, bool(eligible)), 0) + 1
    print("TOTAL", len(rows), "COUNTS", sorted((status, eligible, count) for (status, eligible), count in counts.items()))
    for listing_id, status, markers, eligible in results:
        if eligible and status in ("finance", "missing", "error"):
            print("REVIEW", listing_id, status, markers)
    if sum(1 for _, status, _, _ in results if status in ("missing", "error")) > 30:
        print("DETAIL ACCESS TOO INCOMPLETE", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
