# Baghdad & Bismayah Realty Watch

바그다드·비스마야 부동산 시세를 지역별/단지별로 비교해서 보여주는 대시보드 + 자동 시세 수집 파이프라인입니다.

## 구성

```
index.html                        ← 대시보드 (GitHub Pages로 바로 배포 가능)
design/map-preview.html           ← 지도 컴포넌트만 따로 뗀 개발/검토용 파일
scripts/scrape_ibaity.py                  ← ibaity 승인·활성 아파트 매매 매물 전체 수집 및 월간 이력 누적
.github/workflows/ibaity-price-update.yml ← 매월 1일(KST) 자동 실행 + 수동 실행 버튼
data/history.json                         ← 날짜별·지역별 원시 수집 이력
data/latest.json                          ← 표본 3건 이상인 최신 지역 중앙값
data/ibaity-latest.json                   ← ibaity 전체 페이지에서 수집한 최신 아파트 매물·단지별 중앙값
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

- `scripts/scrape_ibaity.py`는 ibaity 공개 client API의 `PageNumber=1`부터 마지막 페이지까지 바그다드 아파트 매매 매물을 수집합니다.
- 승인된 현행 매물만 남기고, 가격·면적이 없는 매물과 판매 완료·만료 매물을 제외합니다. 개인정보(중개인 이름·전화번호)는 저장하지 않습니다.
- `data/ibaity-latest.json`에는 개별 매물 원장과 단지별 ㎡당 호가 중앙값을 저장합니다. 가격은 실거래가가 아닌 등록 호가입니다.
- `.github/workflows/ibaity-price-update.yml`가 매월 1일(KST) 실행되며, Actions에서 수동 실행도 가능합니다.

- ibaity 공개 client API에서 승인된 활성 아파트 매매 매물을 페이지 끝까지 수집
- 월 1회 매물 원장(`data/ibaity-latest.json`)과 단지별 월간 기준값(`data/complex-history.json`)을 같은 실행에서 갱신
- 화면 상단의 갱신일, 단지별 현재 시세·지역 요약·매물 링크·분기 그래프가 같은 ibaity 원장을 사용
- 중복 매물 ID와 확인된 선수금·분할납부·잔금승계 조건 매물은 대표 가격 산정에서 제외
- aiqarat 기반 월말 workflow는 중단했습니다. 기존 스크립트와 과거 지역 데이터는 보존합니다.

## 데이터 파이프라인 세부사항

### 동작 방식
1. ibaity의 바그다드 승인 매매 아파트 API를 10건 단위로 마지막 페이지까지 조회
2. 판매·만료 상태, 가격, 면적, 중복 ID를 점검하고 가격 적격성을 표시
3. 매물별 링크와 단지 정보를 원장에 저장
4. 최근 90일 단지별 중앙값 및 월간 검증 스냅샷을 생성
5. 같은 실행에서 최신 날짜와 단지 이력을 함께 커밋

### 로컬 테스트
```bash
python scripts/scrape_ibaity.py
```

### GitHub Actions 활성화
저장소 Settings → Actions → General → "Read and write permissions" 켜기
(자동 커밋/푸시에 필요합니다). 월간 업데이트는 `Monthly Ibaity apartment-price update` workflow 하나만 사용합니다.

### 데이터 성격 관련 주의사항
- 모든 가격은 **매물 등록 호가(asking price)**이며, 실제 계약 체결가(실거래가)가
  아닙니다. 이라크에는 한국 국토부 실거래가 시스템 같은 공식 데이터베이스가 없습니다.
- 표본수(`sample_count`)가 적은 날은 평균이 튈 수 있으니, 대시보드에 표시할 때
  표본수도 같이 보여주는 걸 권장합니다.
- ibaity API 요청 간 대기시간을 임의로 줄이지 않습니다.

## 다음 단계 제안
- 기존 Raqi 자료는 출처와 관측일이 확인되는 기존 기간에만 보존하며 ibaity 월간 스냅샷과 구분
