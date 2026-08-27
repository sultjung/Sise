# Baghdad & Bismayah Realty Watch

바그다드·비스마야 부동산 시세를 지역별/단지별로 비교해서 보여주는 대시보드 + 자동 시세 수집 파이프라인입니다.

## 구성

```
index.html                        ← 대시보드 (GitHub Pages로 바로 배포 가능)
design/map-preview.html           ← 지도 컴포넌트만 따로 뗀 개발/검토용 파일
scripts/scrape_prices.py                  ← aiqarat.com에서 지역별 매매 호가를 수집하는 스크립트
.github/workflows/monthly-price-update.yml ← 매월 말일(KST) 자동 실행 + 수동 실행 버튼
data/history.json                         ← 날짜별·지역별 원시 수집 이력
data/latest.json                          ← 표본 3건 이상인 최신 지역 중앙값
```

## 대시보드 (`index.html`)

- 비스마야 세대별(100/120/140㎡) 시세 — 알라피다인 은행 공식 발표가 기준(검증됨)
- 바그다드 지역 비교 — 실제 트레이싱한 경계 좌표 기반 지도(Leaflet) + 리스트
- 공개 매물이 2건 이상이면 중앙값으로 표시하고, 1건만 확보된 지역은 ‘단일 매물’ 배지로 표본 한계를 함께 표시
- 지도 마우스 휠 확대/축소, 리스트 ↔ 지도 클릭 연동
- 기본 통화 USD, IQD 전환 가능

**GitHub Pages로 배포하려면**: 저장소 Settings → Pages → Source를 "Deploy from a branch",
Branch를 `main` / `(root)`로 설정하면 `index.html`이 바로 사이트로 열립니다.

## 시세 자동 수집 (`scripts/`, `.github/workflows/`)

- aiqarat.com을 지역명으로 매월 말일 자동 검색해서 매물을 수집
- "매매(للبيع)"만 남기고 "임대"는 자동 제외
- 지역별 중앙값/평균/최소/최대/표본수를 `data/history.json`에 날짜별로 누적하고, 표시 가능한 최신 중앙값은 `data/latest.json`에 저장
- OpenSooq는 봇 차단이 걸려있어 소스에서 제외했습니다 (자세한 내용은
  `scripts/scrape_prices.py` 상단 주석 및 아래 주의사항 참고)

**시작 전 꼭 확인할 것**: `scripts/scrape_prices.py` 상단의 `SEARCH_URL_TEMPLATE`이
실제 aiqarat.com 검색 결과 URL과 맞는지 브라우저로 1회 확인해주세요. 자세한 절차는
바로 아래 "데이터 파이프라인 세부사항" 절을 참고하세요.

## 데이터 파이프라인 세부사항

### 동작 방식
1. `TARGET_AREAS`의 각 지역에서 아파트 검색어를 먼저 실행하고, 결과가 없으면 빌라·단독주택 검색어를 실행
2. 검색결과의 매물 링크를 전부 방문
3. 매매만 필터링, 면적·가격 추출 → m²당 단가 계산
4. "مجمع ..." 패턴으로 단지명도 최대한 추출
5. 지역별 요약을 `data/history.json`에 append

### 로컬 테스트
```bash
pip install requests beautifulsoup4
python scripts/scrape_prices.py
```

### GitHub Actions 활성화
저장소 Settings → Actions → General → "Read and write permissions" 켜기
(자동 커밋/푸시에 필요합니다)

### 데이터 성격 관련 주의사항
- 모든 가격은 **매물 등록 호가(asking price)**이며, 실제 계약 체결가(실거래가)가
  아닙니다. 이라크에는 한국 국토부 실거래가 시스템 같은 공식 데이터베이스가 없습니다.
- 표본수(`sample_count`)가 적은 날은 평균이 튈 수 있으니, 대시보드에 표시할 때
  표본수도 같이 보여주는 걸 권장합니다.
- aiqarat.com 이용약관을 확인하시고, 요청 간 대기시간(`REQUEST_DELAY_SEC`)을
  임의로 줄이지 마세요.

## 다음 단계 제안
- `data/history.json`이 며칠 쌓이면 대시보드의 스파크라인/추이 그래프에 실제 데이터 연결
- 나머지 지역(사이디야, 알지하드, 사드르시티, 뉴바그다드 등)도 `TARGET_AREAS`에 추가
- 바그다드 지역별로도 만수르처럼 특정 대표 단지를 하나씩 조사해서 "예시" 배지를 "검증됨"으로 교체
