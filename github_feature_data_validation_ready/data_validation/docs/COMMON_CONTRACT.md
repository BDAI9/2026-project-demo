# 팀 공통 데이터 계약 — 먼저 ②, ③, ① 담당과 합의할 내용

**파이썬 코드는 `validation.py`를 기준으로 합니다.**

## A. ② AI 담당 → ④ 검증 담당: UserConditions

모든 키를 보내는 것을 권장합니다. 빠진 선택값은 검증기가 기본값/빈 배열로 정리합니다.

```json
{
  "mode": "group",
  "region": "강남",
  "party_size": 4,
  "preferred_cuisines": ["한식"],
  "excluded_terms": ["매운", "해산물"],
  "required_tags": [],
  "category_order": [],
  "max_budget_per_person": 30000,
  "max_leg_straight_km": 1.5
}
```

- `mode`: `group` 또는 `date`.
- `region`: 지역 문자열. 버전 1에서는 단순 텍스트 포함 검사. **`강남역`과 `강남구`/`홍대`와 `마포구` 같은 동의어 인식은 아직 하지 않음.** 지도 해석 결과로 정확한 위치를 확인할 것.
- `party_size`: 필수 정수(1~30), 데이트 모드에서만 생략하면 2로 설정.
- `preferred_cuisines`: 필수 *선호*로 취급합니다. 아무거나 가능하면 `[]`.
- `excluded_terms`: 검증되어야 하는 음식/재료/성향 키워드입니다. **기본 값은 빈 배열이며 알레르기 의료 안전을 보증하지 않습니다.**
- `required_tags`: `조용한`, `룸` 등. 검증 근거 없으면 확인 필요.
- `category_order`: 데이트 코스 순서. 예 `['cafe', 'restaurant', 'bar']`; 2개 이상.
- `max_budget_per_person`: 1인당 예산 상한(원) 또는 null. 현재 단일 예상가격과 비교하는 MVP이며 실제 메뉴 가격/총액은 아님.
- `max_leg_straight_km`: **각 구간 직선거리** 한도. 도보거리 아님.

**핵심 API:**

```python
from validation import validate_conditions
checked = validate_conditions(ai_output)
# checked = {"ok": bool, "errors": list[str], "normalized": dict | None}
```

## B. ③ 잇플 담당 → ④ 검증 담당: 개별 가맹점 행

가능하면 아래 함수로 표준화합니다. 잇플 실제 응답의 배열 wrapper는 ③이 확인하여 각 row를 꺼내야 합니다.

```python
from eatpl_adapter import normalize_eatpl_merchant
place = normalize_eatpl_merchant(one_merchant_dict, region_hint="강남")
```

공개 명세에서 확인 가능한 원천 키: `merNm`, `addr`, `merTpbuzNm`, `allSaleRnk`, `ccgSaleRnk`, `merUrl`, `srtTime`, `endTime`. 실제 반환값에는 누락/다른 형식이 있을 수 있어 **실응답 검증 필요**.

**없는 정보는 절대 날조하지 않습니다.** `capacity`, `price_per_person_krw`, `safe_for_terms`, `menu_verified`, 위경도는 빈 값으로 남깁니다.

## C. 팀 표준 Place (CSV 컬럼 = 파이썬 dict key)

| 컬럼 | 타입 | 의미/규칙 |
| --- | --- | --- |
| `place_id` | string | 가맹점 식별 ID. 어댑터는 상호+주소 해시 생성 |
| `name` | string | 상호명 |
| `address` | string | 검증용 주소(잇플 원문) |
| `region` | string | **검증된** 요청 지역. 확신이 없으면 빈 값 |
| `category` | `restaurant/cafe/bar` | 업종. 불확실하면 빈 값으로 유지 후 검증 대상으로 분류 |
| `cuisine` | string | 확인된 음식 종류, 없으면 빈 값 |
| `price_per_person_krw` | number/null | 확인된 1인당 예상가, 없으면 null |
| `capacity` | integer/null | **확인된** 수용인원. 없으면 null |
| `lat_wgs84`, `lon_wgs84` | number/null | 위도(WGS84), 경도(WGS84); TM128 복사 금지 |
| `coordinate_source` | string | `kakao_local`, `manual_map_check`, `demo` 중 하나 등 |
| `coordinate_verified` | bool | 검증되었을 때만 true |
| `coordinate_evidence` | string | 매장 ID/정확한 주소와 교차검증 근거 |
| `contains_terms` | string[] | 제외 조건과 충돌하는 것으로 **확인된** 항목 |
| `safe_for_terms` | string[] | **확인된** 제외 조건 충족 항목 (메뉴 근거 필수) |
| `menu_verified` | bool | 메뉴/재료에 대한 점검 완료 여부 |
| `menu_evidence` | string | 실제 영수증·공식 메뉴·확인 근거 등 출처 |
| `tags` | string[] | 조용한/룸 등 근거가 있는 속성 |
| `tags_evidence` | string | 속성 근거 |
| `merchant_url` | string | 잇플이 반환한 HTTPS 상세 링크만 허용, 추측 생성 금지 |
| `all_sale_rank_pct` | number/null | 전국 매출 상위 백분위. **작을수록 상위** |
| `estimated_hours` | string | 결제 데이터 기반 예상시간(공식 영업시간 아님) |
| `source` | string | `eatpl` 또는 `demo` |
| `is_demo` | bool | 가상 자료를 실데이터와 혼합하지 않도록 표시 |

CSV 저장에서는 문자열 배열을 `매운|해산물`처럼 `|`로 연결하고, 미확인 값은 **빈 칸**으로 두세요. API/파이썬에서는 배열과 `null`을 그대로 사용합니다.

## D. ④ 검증 담당 → ③/①: 검사 결과

```python
from validation import evaluate_candidate, filter_places, validate_course
# 각 장소: {"status":"pass|needs_verification|reject", "reasons":[], "is_demo": bool}
check = evaluate_candidate(place, conditions)
# 전체: {"pass":[...], "needs_verification":[...], "reject":[...]}
all_results = filter_places(places, conditions)
# 코스: {"status":"pass|needs_verification|fail", "failures":[], "unknown":[], "legs":[]}
course = validate_course(place_ids, places_by_id, date_conditions)
```

`course`의 실제 운영 호출에서는 `allow_demo_coordinates`를 **절대 True로 두지 마세요**. 이 옵션은 가상 샘플 시연에서만 사용합니다.

## E. ③ 담당이 카카오 좌표를 보강할 때 주의할 점

다음은 **매칭 검증이 완료된 장소일 때만** 적용하는 예시입니다. 카카오 검색 결과가 같은 상호의 다른 지점일 수 있으므로 이름·주소·지점 확인이 먼저입니다.

```python
# kakao_place = 카카오 Local API에서 교차확인한 정확히 동일 매장
place["lat_wgs84"] = float(kakao_place["y"])   # latitude
place["lon_wgs84"] = float(kakao_place["x"])   # longitude
place["coordinate_source"] = "kakao_local"
place["coordinate_evidence"] = f"kakao_id={kakao_place['id']} ; 동일 매장/주소 교차확인"
place["coordinate_verified"] = True
```

추가로 WGS84인지 카카오 공식 명세와 실제 응답을 확인하세요. 잇플 TM128 값과 혼용하지 않습니다.

## F. 판정이 필요할 때 팀이 결정해야 할 정책

- `needs_verification` 후보를 화면에서 숨길지, "확인 필요"로만 보여줄지
- '매운' 제외가 매장의 모든 메뉴를 뜻하는지, 적어도 한 개의 안 매운 메뉴가 있으면 되는지
- 특정 음식 알레르기/교차오염 가능성은 **자동 안전 보증 불가**로 별도 처리
- 예산에 음료/주류/세금 등이 포함되는지
- `region`을 행정구역·반경·지하철역 거리 중 무엇으로 정의하는지
- 동일 장소의 중복과 동일 프랜차이즈의 다른 지점 중복을 어떻게 구분하는지
