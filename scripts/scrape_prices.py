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
    # 아파트를 우선 수집하고, 없을 때만 빌라·단독주택 매물을 대체 표본으로 사용한다.
    {"district_key":"bismayah","district_kr":"비스마야","apartment":["بسماية شقة"],"fallback":["بسماية فيلا","بسماية دار"]},
    {"district_key":"mansour","district_kr":"알만수르","apartment":["المنصور شقة"],"fallback":["المنصور فيلا","المنصور دار"]},
    {"district_key":"jadriya","district_kr":"알자드리야","apartment":["الجادرية شقة"],"fallback":["الجادرية فيلا","الجادرية دار"]},
    {"district_key":"harthiya","district_kr":"알하르씨야","apartment":["الحارثية شقة"],"fallback":["الحارثية فيلا","الحارثية دار"]},
    {"district_key":"karrada","district_kr":"알카라다","apartment":["الكرادة شقة"],"fallback":["الكرادة فيلا","الكرادة دار"]},
    {"district_key":"yarmouk","district_kr":"야르무크","apartment":["اليرموك شقة"],"fallback":["اليرموك فيلا","اليرموك دار"]},
    {"district_key":"kadhimiya","district_kr":"카지미야","apartment":["الكاظمية شقة"],"fallback":["الكاظمية فيلا","الكاظمية دار"]},
    {"district_key":"zayouna","district_kr":"자야우나","apartment":["زيونة شقة"],"fallback":["زيونة فيلا","زيونة دار"]},
    {"district_key":"newbaghdad","district_kr":"뉴바그다드","apartment":["بغداد الجديدة شقة"],"fallback":["بغداد الجديدة فيلا","بغداد الجديدة دار"]},
    {"district_key":"amiriya","district_kr":"알아미리야","apartment":["العامرية شقة"],"fallback":["العامرية فيلا","العامرية دار"]},
    {"district_key":"saydiya","district_kr":"사이디야","apartment":["السيدية شقة"],"fallback":["السيدية فيلا","السيدية دار"]},
    {"district_key":"jihad","district_kr":"알지하드","apartment":["حي الجهاد شقة"],"fallback":["حي الجهاد فيلا","حي الجهاد دار"]},
    {"district_key":"sadrcity","district_kr":"사드르시티","apartment":["مدينة الصدر شقة"],"fallback":["مدينة الصدر فيلا","مدينة الصدر دار"]},
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
MIN_PUBLISHABLE_SAMPLES = 1

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

def collect_area(query: str) -> list[dict]:
    links = search_area(query)
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

    표본이 1건뿐인 지역도 공개하되, 대시보드에서 단일 매물임을 명확히 표시한다.
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
                "property_type": summary.get("property_type") or "아파트",
            }
    payload = {
        "updated_at": entry["date"],
        "source": entry["source"],
        "method": "매매 아파트 공개 호가의 m²당 중앙값 (1건은 단일 매물 표기)",
        "by_district": published,
    }
    LATEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    today = datetime.date.today().isoformat()
    print(f"[{today}] 지역별 매매 매물 수집 시작 ({len(TARGET_AREAS)}개 지역)…")

    by_district = {}
    for area_cfg in TARGET_AREAS:
        key = area_cfg["district_key"]
        print(f"  → {area_cfg['district_kr']} 아파트 매물 검색 중…")
        apartment_listings = []
        for query in area_cfg["apartment"]:
            apartment_listings.extend(collect_area(query))
        if apartment_listings:
            listings = apartment_listings
            property_type = "아파트"
        else:
            print("     아파트 표본 없음 → 빌라/단독주택 매물 보조 검색")
            fallback_listings = []
            for query in area_cfg["fallback"]:
                fallback_listings.extend(collect_area(query))
            listings = fallback_listings
            property_type = "빌라/단독주택" if fallback_listings else None
        summary = summarize(listings)
        summary["district_kr"] = area_cfg["district_kr"]
        summary["property_type"] = property_type
        by_district[key] = summary
        print(f"     {property_type or '매물 없음'} {summary['sample_count']}건, 중앙값 {summary.get('median_price_per_m2_iqd')} IQD/m²")

    entry = {"date": today, "source": "aiqarat.com", "by_district": by_district}
    append_history(entry)
    write_latest(entry)
    print(f"\n→ {HISTORY_PATH} 및 {LATEST_PATH} 에 저장 완료")


if __name__ == "__main__":
    main()

