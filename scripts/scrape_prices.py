#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aiqarat.com에서 여러 지역/단지의 아파트 '매매' 호가를 매일 검색·수집해서
data/history.json 에 지역별·날짜별로 누적 저장하는 스크립트.

동작 방식
---------
1. TARGET_AREAS 에 등록된 지역/단지 이름을 하나씩 워드프레스 기본 검색
   (`https://aiqarat.com/?s=검색어`)에 넣어서 검색결과 페이지를 가져온다.
2. 결과 페이지에서 `/property/` 링크를 전부 뽑는다.
3. 각 매물 상세페이지를 열어서 '매매(للبيع)'만 통과시키고 '임대'는 제외,
   면적/가격을 추출해 m²당 단가를 계산한다.
4. 매물 제목/본문에서 "مجمع ..." 패턴으로 단지명을 최대한 추출한다
   (없으면 지역명만으로 그룹핑).
5. 지역별로 당일 평균/최소/최대/표본수를 계산해서 history.json에 append.

⚠️ 검증 필요 (1회만 해주시면 됩니다)
------------------------------------
`https://aiqarat.com/?s=...` 가 실제로 매물 검색결과를 돌려주는지, 아니면
Houzez 테마의 전용 검색 폼(`/property-search/?...`)을 써야 하는지는 브라우저로
직접 한 번 확인해주세요:
  1) https://aiqarat.com 에서 "بسماية" 로 검색
  2) 결과 페이지 주소창의 URL을 복사
  3) 그 URL의 패턴을 아래 SEARCH_URL_TEMPLATE 에 반영 (예: 쿼리 파라미터명이
     다르면 그에 맞게 수정)
바로 안 맞더라도, 매물 상세페이지 파싱 로직(면적/가격/매매판별)은 그대로
재사용할 수 있습니다.
"""

import json
import re
import sys
import time
import statistics
import datetime
from pathlib import Path
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

# 워드프레스 기본 검색 URL 패턴. 브라우저로 검증 후 필요하면 수정하세요.
SEARCH_URL_TEMPLATE = "https://aiqarat.com/?s={query}"

# 검색할 지역/단지 목록. "query"는 검색창에 넣을 키워드,
# "district_key"/"district_kr"는 대시보드 쪽 지역 id와 맞춰주면 연동이 쉬움.
TARGET_AREAS = [
    {"district_key": "bismayah", "district_kr": "비스마야",  "query": "بسماية شقة"},
    {"district_key": "mansour",  "district_kr": "알만수르",  "query": "المنصور شقة"},
    {"district_key": "jadriya",  "district_kr": "알자드리야", "query": "الجادرية شقة"},
    {"district_key": "harthiya", "district_kr": "알하르씨야", "query": "الحارثية شقة"},
    {"district_key": "karrada",  "district_kr": "알카라다",  "query": "الكرادة شقة"},
    {"district_key": "yarmouk",  "district_kr": "야르무크",  "query": "اليرموك شقة"},
    {"district_key": "kadhimiya","district_kr": "카지미야",  "query": "الكاظمية شقة"},
    {"district_key": "zayouna",  "district_kr": "자야우나",  "query": "زيونة شقة"},
    {"district_key": "amiriya",  "district_kr": "알아미리야", "query": "العامرية شقة"},
    # 필요하면 여기에 지역/단지를 계속 추가하면 됩니다.
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BaghdadPriceTracker/1.0; "
                  "+https://example.com/about-this-bot)",
    "Accept-Language": "ar,en;q=0.8",
}

REQUEST_DELAY_SEC = 2.0
MAX_LISTINGS_PER_AREA = 40   # 지역당 너무 많이 긁지 않도록 상한
HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "history.json"
LATEST_PATH = Path(__file__).resolve().parent.parent / "data" / "latest.json"
MIN_PUBLISHABLE_SAMPLES = 3

SALE_KEYWORDS = ["للبيع"]
RENT_KEYWORDS = ["للايجار", "للإيجار", "ايجار", "إيجار"]

COMPLEX_NAME_PATTERN = re.compile(r"مجمع\s+[^\d,،\.\n]{2,30}")


# ---------------------------------------------------------------------------
# 파싱 유틸
# ---------------------------------------------------------------------------

def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def search_area(query: str) -> list[str]:
    url = SEARCH_URL_TEMPLATE.format(query=quote(query))
    try:
        html = fetch(url)
    except requests.RequestException as e:
        print(f"[경고] 검색 실패: {query} → {url} ({e})", file=sys.stderr)
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = {urljoin(url, a["href"]) for a in soup.select("a[href*='/property/']") if a.get("href")}
    return sorted(links)[:MAX_LISTINGS_PER_AREA]


def parse_property_page(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    is_rent = any(kw in text for kw in RENT_KEYWORDS)
    is_sale = any(kw in text for kw in SALE_KEYWORDS)
    if is_rent or not is_sale:
        return None

    area_match = re.search(r"(\d{2,4})\s*(?:متر مربع|م٢|م²)", text)
    if not area_match:
        return None
    area = int(area_match.group(1))
    if area < 30 or area > 1000:   # 아파트가 아닌 토지/농장 등 오인 방지 (러프 필터)
        return None

    price_match = re.search(r"([\d,]{6,})\s*IQD", text)
    if not price_match:
        return None
    price_iqd = int(price_match.group(1).replace(",", ""))
    if price_iqd < 15_000_000:
        return None

    complex_match = COMPLEX_NAME_PATTERN.search(text)
    complex_name = complex_match.group(0).strip() if complex_match else None

    return {
        "url": url,
        "area_m2": area,
        "price_iqd": price_iqd,
        "price_per_m2_iqd": round(price_iqd / area),
        "complex_name": complex_name,
    }


# ---------------------------------------------------------------------------
# 메인 로직
# ---------------------------------------------------------------------------

def collect_area(area_cfg: dict) -> list[dict]:
    links = search_area(area_cfg["query"])
    time.sleep(REQUEST_DELAY_SEC)

    results = []
    for link in links:
        try:
            html = fetch(link)
        except requests.RequestException as e:
            print(f"[경고] 매물 페이지 요청 실패: {link} ({e})", file=sys.stderr)
            continue
        parsed = parse_property_page(html, link)
        if parsed:
            results.append(parsed)
        time.sleep(REQUEST_DELAY_SEC)
    return results


def summarize(listings: list[dict]) -> dict:
    if not listings:
        return {
            "avg_price_per_m2_iqd": None, "min_price_per_m2_iqd": None,
            "max_price_per_m2_iqd": None, "sample_count": 0, "complexes_seen": [],
        }
    prices = [x["price_per_m2_iqd"] for x in listings]
    complexes = sorted({x["complex_name"] for x in listings if x["complex_name"]})
    return {
        # 호가의 극단값 영향을 줄이기 위해 화면 표시 기준은 중앙값을 사용한다.
        "median_price_per_m2_iqd": round(statistics.median(prices)),
        "avg_price_per_m2_iqd": round(sum(prices) / len(prices)),
        "min_price_per_m2_iqd": min(prices),
        "max_price_per_m2_iqd": max(prices),
        "sample_count": len(prices),
        "complexes_seen": complexes,
    }


def append_history(entry: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else []
    history.append(entry)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def write_latest(entry: dict) -> None:
    """대시보드가 읽는 최신 검증값을 별도 파일로 저장한다.

    표본이 3건 미만인 지역은 공개하지 않아 단일 호가가 지역 평균처럼
    표시되는 일을 막는다.
    """
    published = {}
    for key, summary in entry["by_district"].items():
        median = summary.get("median_price_per_m2_iqd")
        if summary.get("sample_count", 0) >= MIN_PUBLISHABLE_SAMPLES and median:
            published[key] = {
                "district_kr": summary["district_kr"],
                "price_per_m2_iqd": median,
                "sample_count": summary["sample_count"],
                "complexes_seen": summary["complexes_seen"],
            }
    payload = {
        "updated_at": entry["date"],
        "source": entry["source"],
        "method": "매매 아파트 공개 호가의 m²당 중앙값 (표본 3건 이상만 공개)",
        "by_district": published,
    }
    LATEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    today = datetime.date.today().isoformat()
    print(f"[{today}] 지역별 매매 매물 수집 시작 ({len(TARGET_AREAS)}개 지역)…")

    by_district = {}
    for area_cfg in TARGET_AREAS:
        key = area_cfg["district_key"]
        print(f"  → {area_cfg['district_kr']} ({area_cfg['query']}) 검색 중…")
        listings = collect_area(area_cfg)
        summary = summarize(listings)
        summary["district_kr"] = area_cfg["district_kr"]
        by_district[key] = summary
        print(f"     매매 {summary['sample_count']}건, 평균 {summary['avg_price_per_m2_iqd']} IQD/m²")

    entry = {"date": today, "source": "aiqarat.com", "by_district": by_district}
    append_history(entry)
    write_latest(entry)
    print(f"\n→ {HISTORY_PATH} 및 {LATEST_PATH} 에 저장 완료")


if __name__ == "__main__":
    main()

