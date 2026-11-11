# 데이터·검증 모듈 (④ 담당)

## 상태
- 실제 잇플 API 또는 카카오 API를 호출하지 않는 **검증 모듈**입니다.
- `data/sample_places_v2_30.csv`의 30개 매장은 모두 **가상 테스트 데이터**입니다.
- `docs/test_scenarios_15.csv`는 가상 데이터 기반 결과이며 AI 실제 추론/잇플 실연동을 검증한 결과가 아닙니다.

## 파일
- `validation.py`: 사용자 조건/장소/거리/코스 검증 및 분류
- `eatpl_adapter.py`: 공개 명세에 맞춘 잇플 **예시 필드 정제기** (실제 응답 검증 전)
- `data/sample_places_v2_30.csv`: 가상 장소 30개
- `data/sample_user_requests.json`: 자연어 요청 12개 및 기대 JSON (AI의 실제 출력 아님)
- `run_test_scenarios.py`: 15개 시나리오 확인/결과 CSV 재생성
- `tests/`: 원본 샘플 12개 기반 자동 단위 테스트 27개
- `docs/`: 팀 협의 규격/제약사항/검증 결과
- `data/sample_places.csv`: 원래 단위 테스트 27개용 가상 매장 12개

## 팀 저장소 루트에서 실행

```bash
python -m unittest discover -s data_validation/tests -p 'test_*.py' -v
python data_validation/run_test_scenarios.py data_validation/data/sample_places_v2_30.csv data_validation/data/sample_user_requests.json --output data_validation/docs/test_scenarios_15.csv
```

## 팀 저장소 루트에서 불러오기

```python
from data_validation.validation import validate_conditions, filter_places, validate_course

checked = validate_conditions(ai_parsed_json)
if checked['ok']:
    result = filter_places(normalized_eatpl_places, checked['normalized'])
else:
    result = {'error': checked['errors']}
```

`normalized_eatpl_places`는 `validation.py`에 맞춰 보강한 장소 정보여야 합니다. 잇플의 실제 반환형식(중첩 구조 포함)을 확인한 다음 어댑터를 팀과 함께 보완해야 합니다.

## 판정 원칙
- `pass`: 확인 가능한 필수 조건을 만족한 경우 (가상 데이터에서는 가상 근거)
- `needs_verification`: 메뉴/인원/가격 등 정보가 불충분한 경우
- `reject`: 확인된 조건에 위배되거나 레코드 형식이 잘못된 경우
- `validate_course()`의 거리는 실제 도보거리가 아닌 **직선거리**이며 미검증 좌표는 확정 판단에 사용하지 않습니다.

## 미확인 및 팀원 요청 자료
1. AI 담당: 실제 출력 JSON 1~3개 및 필드 정의
2. 잇플 담당: 민감정보 제거한 실제 검색 JSON 1~3개 및 접근/오류 응답 양식
3. 코스 담당: 장소 ID 목록 및 좌표를 얻는 과정/출처
4. 프론트 담당: `pass`/`needs_verification`/`reject` 표시 방식
5. 팀 통합시 기존 경로/모듈명과 충돌 없는지 확인

## 업로드 주의
- API 키, `.env`, 비밀정보, 실제 이용자/결제 기록 등은 업로드 금지
- 실제 카카오 조회 좌표 및 직선거리 CSV는 사용자가 별도 생성한 파일입니다. 공개 레포에 올리기 전 민감정보나 이용조건을 확인하고 **팀 합의 후** 추가하세요.
- `docs/*legacy.csv`: 초기에 생성한 12개 샘플 관련 테스트 실행 기록. 현재 30개 fixture의 최신 실행 결과와 구분해야 합니다.
