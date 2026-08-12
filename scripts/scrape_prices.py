#!/usr/bin/env python3
"""Collect monthly Baghdad apartment asking prices from public listing pages.

The collector deliberately publishes samples and source URLs, not a single opaque
"market price".  A district value is eligible to replace the website's example
value only when at least three fresh, non-outlier apartment listings remain.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = ROOT / "config" / "targets.json"
LATEST_PATH = ROOT / "data" / "latest.json"
HISTORY_PATH = ROOT / "data" / "history.json"
LISTINGS_PATH = ROOT / "data" / "listings-latest.json"

SEARCH_URL = "https://aiqarat.com/?s={query}"
SOURCE_NAME = "aiqarat.com"
MAX_LINKS_PER_TARGET = 24
MAX_SEARCH_PAGES = 2
REQUEST_DELAY_SECONDS = 1.2
MAX_LISTING_AGE_DAYS = 395
MIN_PUBLISH_SAMPLES = 3
DEFAULT_IQD_PER_USD = 1310

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ARABIC_MONTHS = {
    "يناير": 1, "كانون الثاني": 1, "فبراير": 2, "شباط": 2,
    "مارس": 3, "آذار": 3, "ابريل": 4, "أبريل": 4, "نيسان": 4,
    "مايو": 5, "أيار": 5, "يونيو": 6, "حزيران": 6,
    "يوليو": 7, "تموز": 7, "اغسطس": 8, "أغسطس": 8, "آب": 8,
    "سبتمبر": 9, "أيلول": 9, "اكتوبر": 10, "أكتوبر": 10, "تشرين الأول": 10,
    "نوفمبر": 11, "تشرين الثاني": 11, "ديسمبر": 12, "كانون الأول": 12,
}
SALE_WORDS = ("للبيع", "حالة العقار للبيع", "الغرض بيع")
RENT_WORDS = ("للايجار", "للإيجار", "ايجار", "إيجار", "شهريا", "سنويا")
APARTMENT_WORDS = ("شقة", "شقق", "apartment")
EXCLUDED_TYPES = ("ارض", "أرض", "دار للبيع", "بيت للبيع", "فيلا", "عمارة", "تجاري")


def normalized(value: str) -> str:
    value = value.translate(ARABIC_DIGITS)
    value = value.replace("٬", ",").replace("٫", ".").replace("ـ", "")
    return re.sub(r"\s+", " ", value).strip()


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/") + "/", "", ""))


def first_number(raw: str) -> float | None:
    match = re.search(r"\d[\d,.]*", normalized(raw))
    if not match:
        return None
    token = match.group(0).replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None


def parse_area(text: str) -> int | None:
    text = normalized(text)
    patterns = (
        r"(?:حجم العقار|المساحة|مساحة|Area Size|area)\s*[:\-]?\s*(\d{2,4})\s*(?:متر مربع|م2|م²|م٢|sqm)?",
        r"(\d{2,4})\s*(?:متر مربع|م2|م²|م٢|sqm)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            area = int(match.group(1))
            if 50 <= area <= 400:
                return area
    return None


def parse_price_iqd(text: str, iqd_per_usd: int) -> int | None:
    text = normalized(text)
    # Prefer explicitly labelled total prices.  "per metre" offers are excluded.
    windows = re.findall(
        r"(?:السعر(?: الكلي| البيع)?|سعرها الكلي|price)\s*[:\-]?\s*([^\n|]{1,80})",
        text,
        flags=re.IGNORECASE,
    )
    windows.append(text[:2500])
    candidates: list[int] = []
    for window in windows:
        for match in re.finditer(r"([\d,.]+)\s*(مليون|مليار)?\s*(IQD|دينار(?: عراقي)?|دولار|USD|\$)", window, re.IGNORECASE):
            snippet = window[max(0, match.start() - 20): match.end() + 30]
            if any(term in snippet for term in ("للمتر", "للمتر المربع", "/ للمتر", "per m")):
                continue
            number = first_number(match.group(1))
            if number is None:
                continue
            scale = match.group(2)
            currency = match.group(3).lower()
            if scale == "مليون":
                number *= 1_000_000
            elif scale == "مليار":
                number *= 1_000_000_000
            if currency in ("دولار", "usd", "$"):
                number *= iqd_per_usd
            value = round(number)
            if 20_000_000 <= value <= 2_000_000_000:
                candidates.append(value)
        if candidates:
            break
    return candidates[0] if candidates else None


def parse_listing_date(text: str) -> dt.date | None:
    text = normalized(text)
    iso = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if iso:
        try:
            return dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass
    for month_name, month in sorted(ARABIC_MONTHS.items(), key=lambda item: -len(item[0])):
        match = re.search(rf"(?:تحديث في|نشر في)?\s*(\d{{1,2}})\s+{re.escape(month_name)}\s+(20\d{{2}})", text)
        if match:
            try:
                return dt.date(int(match.group(2)), month, int(match.group(1)))
            except ValueError:
                return None
    return None


def page_title(soup: BeautifulSoup) -> str:
    for selector in ("h1", ".page-title", ".property-title", "title"):
        node = soup.select_one(selector)
        if node and node.get_text(strip=True):
            return normalized(node.get_text(" ", strip=True))
    return ""


def target_matches(text: str, aliases: list[str]) -> bool:
    return any(normalized(alias) in text for alias in aliases)


def parse_property(html: str, url: str, target: dict[str, Any], today: dt.date, iqd_per_usd: int) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    title = page_title(soup)
    text = normalized(soup.get_text(" ", strip=True))
    compact = f"{title} {text}"

    if not target_matches(compact, target["aliases"]):
        return None
    if not any(word in compact for word in SALE_WORDS) or any(word in compact for word in RENT_WORDS):
        return None
    if not any(word.lower() in compact.lower() for word in APARTMENT_WORDS):
        return None
    if any(word in title for word in EXCLUDED_TYPES):
        return None

    area = parse_area(compact)
    price = parse_price_iqd(compact, iqd_per_usd)
    if not area or not price:
        return None
    unit_price = round(price / area)
    if not 100_000 <= unit_price <= 10_000_000:
        return None

    listing_date = parse_listing_date(compact)
    age_days = (today - listing_date).days if listing_date else None
    if age_days is not None and (age_days < -7 or age_days > MAX_LISTING_AGE_DAYS):
        return None

    property_id = None
    match = re.search(r"(?:معرف العقار|Property ID)\s*[:\-]?\s*([A-Za-z]+-?\d+)", compact, re.IGNORECASE)
    if match:
        property_id = match.group(1)
    return {
        "source": SOURCE_NAME,
        "url": canonical_url(url),
        "property_id": property_id,
        "title": title[:240],
        "target_key": target["key"],
        "area_m2": area,
        "price_iqd": price,
        "price_per_m2_iqd": unit_price,
        "listing_date": listing_date.isoformat() if listing_date else None,
        "age_days": age_days,
    }


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, connect=3, read=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; BaghdadRealtyWatch/2.0; +https://sultjung.github.io/Sise/)",
        "Accept-Language": "ar,en;q=0.8",
    })
    return session


def fetch(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY_SECONDS)
    return response.text


def discover_links(session: requests.Session, queries: list[str]) -> tuple[list[str], list[str]]:
    links: set[str] = set()
    errors: list[str] = []
    for query in queries:
        for page in range(1, MAX_SEARCH_PAGES + 1):
            base = SEARCH_URL.format(query=quote(query))
            url = base if page == 1 else f"https://aiqarat.com/page/{page}/?s={quote(query)}"
            try:
                soup = BeautifulSoup(fetch(session, url), "html.parser")
            except requests.RequestException as exc:
                errors.append(f"{query}: {type(exc).__name__}")
                break
            before = len(links)
            for anchor in soup.select("a[href*='/property/']"):
                href = anchor.get("href")
                if href:
                    links.add(canonical_url(urljoin(url, href)))
            if len(links) == before:
                break
            if len(links) >= MAX_LINKS_PER_TARGET:
                break
    return sorted(links)[:MAX_LINKS_PER_TARGET], errors


def remove_outliers(listings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    if len(listings) < 4:
        return listings, 0
    values = sorted(item["price_per_m2_iqd"] for item in listings)
    lower_half = values[: len(values) // 2]
    upper_half = values[(len(values) + 1) // 2:]
    q1 = statistics.median(lower_half)
    q3 = statistics.median(upper_half)
    iqr = q3 - q1
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    kept = [item for item in listings if low <= item["price_per_m2_iqd"] <= high]
    return kept, len(listings) - len(kept)


def summarize(listings: list[dict[str, Any]], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    filtered, excluded = remove_outliers(listings)
    if not filtered:
        return {"sample_count": 0, "confidence": "none", "publishable": False, "outliers_excluded": excluded}
    values = [item["price_per_m2_iqd"] for item in filtered]
    count = len(values)
    median = round(statistics.median(values))
    confidence = "high" if count >= 8 else "medium" if count >= MIN_PUBLISH_SAMPLES else "low"
    review_required = False
    previous_price = (previous or {}).get("published_price_per_m2_iqd")
    if previous_price and abs(median - previous_price) / previous_price > 0.45 and count < 8:
        review_required = True
    publishable = count >= MIN_PUBLISH_SAMPLES and not review_required
    return {
        "observed_median_price_per_m2_iqd": median,
        "observed_average_price_per_m2_iqd": round(statistics.mean(values)),
        "min_price_per_m2_iqd": min(values),
        "max_price_per_m2_iqd": max(values),
        "published_price_per_m2_iqd": median if publishable else previous_price,
        "sample_count": count,
        "confidence": confidence,
        "publishable": publishable,
        "review_required": review_required,
        "outliers_excluded": excluded,
        "source_count": 1,
        "source_names": [SOURCE_NAME],
        "source_urls": [item["url"] for item in filtered[:10]],
        "newest_listing_date": max((item["listing_date"] for item in filtered if item["listing_date"]), default=None),
    }


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_target(session: requests.Session, target: dict[str, Any], today: dt.date, iqd_per_usd: int, cache: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    links, errors = discover_links(session, target["queries"])
    parsed: dict[str, dict[str, Any]] = {}
    for url in links:
        try:
            html = cache.get(url)
            if html is None:
                html = fetch(session, url)
                cache[url] = html
            item = parse_property(html, url, target, today, iqd_per_usd)
        except requests.RequestException as exc:
            errors.append(f"{url}: {type(exc).__name__}")
            continue
        if item:
            dedupe_key = item["property_id"] or item["url"]
            parsed[dedupe_key] = item
    return list(parsed.values()), errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Override collection date (YYYY-MM-DD), useful for tests")
    parser.add_argument("--iqd-per-usd", type=int, default=DEFAULT_IQD_PER_USD)
    args = parser.parse_args()
    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    period = today.strftime("%Y-%m")

    config = read_json(TARGETS_PATH, {})
    if not config.get("districts") or not config.get("complexes"):
        print("targets.json is missing district/complex targets", file=sys.stderr)
        return 2

    previous_latest = read_json(LATEST_PATH, {})
    session = build_session()
    html_cache: dict[str, str] = {}
    all_listings: list[dict[str, Any]] = []
    all_errors: list[str] = []
    result_groups: dict[str, dict[str, Any]] = {"districts": {}, "complexes": {}}

    for group_name in ("districts", "complexes"):
        for target in config[group_name]:
            print(f"[{group_name}] {target['name_kr']} 수집 중…")
            listings, errors = collect_target(session, target, today, args.iqd_per_usd, html_cache)
            all_listings.extend({**item, "target_type": group_name[:-1]} for item in listings)
            all_errors.extend(errors)
            previous = previous_latest.get(group_name, {}).get(target["key"], {})
            summary = summarize(listings, previous)
            summary.update({"name_kr": target["name_kr"], "district_key": target.get("district_key")})
            if group_name == "complexes" and target["key"] == "bismayah":
                by_size: dict[str, Any] = {}
                for size in (100, 120, 140):
                    size_items = [item for item in listings if item["area_m2"] == size]
                    by_size[str(size)] = summarize(size_items, previous.get("by_size_m2", {}).get(str(size), {}))
                summary["by_size_m2"] = by_size
            result_groups[group_name][target["key"]] = summary
            print(f"  표본 {summary['sample_count']}건 · 신뢰도 {summary['confidence']}")

    # A Bismayah listing, for example, legitimately contributes to both the
    # Bismayah district and complex statistics.  Store it once in the audit file
    # while retaining every target it matched.
    consolidated: dict[str, dict[str, Any]] = {}
    for item in all_listings:
        dedupe_key = item.get("property_id") or item["url"]
        match = {"type": item.pop("target_type"), "key": item.pop("target_key")}
        if dedupe_key not in consolidated:
            item["matched_targets"] = [match]
            consolidated[dedupe_key] = item
        elif match not in consolidated[dedupe_key]["matched_targets"]:
            consolidated[dedupe_key]["matched_targets"].append(match)
    all_listings = list(consolidated.values())

    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    latest = {
        "schema_version": 2,
        "period": period,
        "generated_at": generated_at,
        "collection_date": today.isoformat(),
        "price_basis": "public asking prices; not completed transactions",
        "iqd_per_usd": args.iqd_per_usd,
        "minimum_publish_samples": MIN_PUBLISH_SAMPLES,
        "districts": result_groups["districts"],
        "complexes": result_groups["complexes"],
        "collection": {
            "source_names": [SOURCE_NAME],
            "listing_count": len(all_listings),
            "request_error_count": len(all_errors),
            "errors": all_errors[:30],
        },
    }
    write_json(LATEST_PATH, latest)
    write_json(LISTINGS_PATH, {"generated_at": generated_at, "listings": all_listings})

    history = read_json(HISTORY_PATH, [])
    if not isinstance(history, list):
        history = []
    snapshot = {k: v for k, v in latest.items() if k != "collection"}
    history = [entry for entry in history if entry.get("period") != period]
    history.append(snapshot)
    history.sort(key=lambda entry: entry.get("period") or entry.get("date", ""))
    write_json(HISTORY_PATH, history)

    print(f"완료: 매물 {len(all_listings)}건, 요청 오류 {len(all_errors)}건")
    # Do not erase old values during a temporary source outage, but fail a totally
    # empty first collection so Actions clearly reports that no market data arrived.
    if not all_listings and not previous_latest.get("districts"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
