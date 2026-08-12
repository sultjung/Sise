# Baghdad & Bismayah Realty Watch

바그다드 주요 지역·아파트 단지와 비스마야의 공개 매물 **호가**를 월 1회 수집해 보여주는 GitHub Pages 대시보드입니다. 이라크에는 한국식 공개 실거래가 데이터베이스가 없으므로, 사이트의 자동 갱신값은 계약 체결가가 아니라 매도자가 등록한 가격입니다.

## 자동 업데이트 방식

매월 1일 바그다드 시간 06:20(한국 12:20)에 GitHub Actions가 다음 순서로 실행됩니다.

1. `config/targets.json`에 등록된 13개 지역과 12개 주요 단지를 아랍어 명칭으로 검색
2. `aiqarat.com`의 각 매물 상세페이지에서 매매 여부, 아파트 여부, 면적, 총가격, 등록일을 확인
3. 임대·토지·주택·상가, 395일 초과 매물, 비정상 단가, 중복 매물을 제외
4. ㎡당 가격의 IQR 이상치를 제거하고 평균·중앙값·최저·최고·표본 수를 계산
5. 표본이 3건 이상인 지역만 지도상의 예시값을 자동 교체
6. 직전 공개가격 대비 45% 넘게 급변하면서 표본이 8건 미만이면 기존 값을 유지하고 `변동 검토`로 표시
7. `data/latest.json`, `data/history.json`, `data/listings-latest.json`을 갱신하고 GitHub Pages에 반영

워크플로: `.github/workflows/monthly-prices.yml`

## 비스마야 처리 원칙

- 상단 100·120·140㎡ 카드는 NIC/은행의 **신규 공급 공식가격**으로 유지합니다.
- 자동 수집되는 비스마야 값은 중고·전매를 포함한 **공개 매물 호가**로 별도 표시합니다.
- `بسماية`뿐 아니라 현지에서 자주 쓰는 `بسمايه` 표기도 함께 검색합니다.
- 100·120·140㎡별 통계도 `data/latest.json > complexes > bismayah > by_size_m2`에 별도 저장합니다.

공식 공급가격과 중고 매물 호가는 성격이 다르기 때문에 합쳐서 평균내지 않습니다.

## 데이터 신뢰도

| 등급 | 기준 | 화면 반영 |
|---|---:|---|
| 높음 | 유효 표본 8건 이상 | 자동 반영 |
| 보통 | 유효 표본 3~7건 | 자동 반영 |
| 표본 부족 | 유효 표본 1~2건 | 단지표 참고용, 지도 예시값 미교체 |
| 미확인 | 유효 표본 0건 | 기존 예시값 유지 |
| 변동 검토 | 전월 대비 45% 초과 급변 + 표본 8건 미만 | 이전 공개값 유지 |

각 자동 수집값에는 표본 수와 원문 매물 링크를 함께 표시합니다. 따라서 하나의 숫자만 보고 확정 시세로 오인하지 않고 근거를 바로 확인할 수 있습니다.

## 주요 파일

```text
index.html                         대시보드
assets/live-prices.js              최신 JSON을 읽어 화면·지도·단지표 갱신
config/targets.json                지역/단지 아랍어 검색어와 일치어
scripts/scrape_prices.py           수집·정제·통계·이력 저장
scripts/validate_prices.py         데이터 구조와 단가 범위 검증
.github/workflows/monthly-prices.yml 월간 자동 실행 및 커밋
data/latest.json                   현재 공개 데이터
data/history.json                  월별 이력
data/listings-latest.json          최신 계산에 사용한 매물·출처
tests/                             아랍어 숫자·가격·면적 파서 테스트
```

## 수동 실행

GitHub 저장소의 `Actions` → `Monthly Baghdad apartment prices` → `Run workflow`를 누르면 정기일을 기다리지 않고 즉시 조사할 수 있습니다.

로컬에서는 다음과 같이 실행합니다.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/scrape_prices.py
python scripts/validate_prices.py
```

자동 커밋을 위해 저장소 `Settings` → `Actions` → `General` → `Workflow permissions`에서 **Read and write permissions**가 허용되어 있어야 합니다.

## 조사 대상 수정

새 단지를 추가하거나 표기를 보완할 때 `config/targets.json`의 `complexes`에 다음 필드를 추가합니다.

```json
{
  "key": "stable_english_key",
  "name_kr": "화면 표시명",
  "district_key": null,
  "queries": ["아랍어 단지명 شقة للبيع"],
  "aliases": ["본문에서 반드시 확인할 정확한 단지명"]
}
```

검색 결과에 나타났다는 이유만으로 포함하지 않고, 상세페이지의 제목·본문에 `aliases` 중 하나가 실제로 있는 경우만 해당 지역/단지 표본으로 인정합니다.
