# 잇플 연결·코스: 팀 공유 및 통합 메모

기준 확인일: 2026-11-12 · 담당 브랜치: `feature/eatpl-course`

## 브랜치와 통합 기준

잇플 담당 작업은 `feature/eatpl-course`에서 개발하고 `dev` 대상 PR을 통해 공유한다. 브랜치에 포함된 코드와 PR 상태는 GitHub에서 확인한다.

2026-11-12 확인한 `dev`의 머리는 `aef2615`다. 데이터 검증 담당 작업이 [공통 데이터 계약](https://github.com/BDAI9/2026-project-demo/blob/aef2615688ce1cd07290bbabb5a0efe5795ffff1/github_feature_data_validation_ready/data_validation/docs/COMMON_CONTRACT.md)과 [잇플 데이터 정규화 코드](https://github.com/BDAI9/2026-project-demo/blob/aef2615688ce1cd07290bbabb5a0efe5795ffff1/github_feature_data_validation_ready/data_validation/eatpl_adapter.py)를 추가했다. 계약을 확인하고 상호 검증한 뒤 실제 앱에서 통합한다.

## 담당자가 로컬에서 확인하는 방법

저장소 루트에서 Python 3.10 이상으로 다음 명령을 실행한다. 아래 결과는 가상의 데이터에 관한 것이며 실제 잇플 연결 성공을 뜻하지 않는다.

```powershell
python -m unittest discover -s tests -v
python -m backend.demo
python -m backend.server
```

서버 실행 후 브라우저에서 `http://127.0.0.1:8000/`을 연다. `샘플 데이터로 둘러보기`와 `가상 지역`을 선택해 조건·순서를 바꿔 볼 수 있다. 실제 개인 단발 조회는 `k-skill 개인 단발 테스트`를 선택하고 `서울 중구` 등 지역을 입력한다. 서버는 실행 중 터미널을 점유하므로 서버 종료는 `Ctrl+C`다. 사용자 화면은 독립 데모이며 팀 프론트 및 실시간 공유 방은 아직 연결되지 않았다.

자동 테스트 50개가 통과했다. 직접 제휴 API의 응답 테스트는 **모의 응답**이다. 2026-11-12 `python -m backend.skill_probe` 개인 단발 조회에서 HTTP 200과 실제 가맹점 1건·상세 주소를 확인했다(캐시 적중). 로컬 화면 `k-skill 개인 단발 테스트`에서 서울 중구로 조회해 실제 카페·식당 코스와 잇플 링크를 표시했고 캐시 미사용으로 표시됐다. 좁은 주소에서 반환한 링크를 별도 브라우저 탭으로 직접 열어 잇플 상세 페이지를 확인했다. 직접 제휴 API의 실서버 검색, 팀 프론트 연동, 공모전 유입 집계는 검증되지 않았다. 실제 접속 경로와 관련 전제는 [잇플 연동 조사](integration.md)를 참고한다.

## 팀 간 모델을 맞출 부분

아래는 확인한 구현들의 차이로, **이미 통합되었다는 뜻이 아니다.** 상대 담당자와 기준을 합의하고 변환 계층 및 상호 테스트를 추가한다.

로컬에는 `backend.app.providers.team_contract.to_team_place` 변환 함수를 준비했다. `merAddr`를 내부 모델을 거쳐 팀의 `address`로 전달하고, 메뉴나 좌표에 대한 근거는 임의로 채우지 않는다. 팀 검증기와의 통합 호출과 팀 합의는 아직 필요하다.

| 항목 | 로컬 잇플·코스 코드 | 데이터 검증 담당 제안 | 통합 시 확인 |
| --- | --- | --- | --- |
| 장소 ID·링크 | `Place.id`, `eatpl_url` | `place_id`, `merchant_url` | 실제 원문 링크를 보존하고 ID 생성·중복 정책을 통일 |
| 위치 | `latitude`, `longitude`는 WGS84 또는 없음 | `lat_wgs84`, `lon_wgs84`, 검증 여부·근거 | 좌표 출처와 검증 기준을 함께 전달. TM128 값을 WGS84로 복사 금지 |
| 후보 판정 | `eligible`, `needs_review`, `excluded` | `pass`, `needs_verification`, `reject` | 상태와 이유의 변환을 정하고 미확인을 충족으로 바꾸지 않기 |
| 주소 원문 | 현재 직접 API 매핑은 `merAddr` | `normalize_eatpl_merchant`는 `addr`를 읽음 | 2026-11-12 프록시 실응답 1건에도 `merAddr` 확인. 전달 시 변환 및 다른 응답 확인 필요 |
| 거리 제한 | `max_leg_distance_m`, 미터 | `max_leg_straight_km`, 킬로미터 | 변환 시 1 km = 1,000 m. 둘 다 직선거리 |
| 예산 | `max_total_per_person_krw`는 코스 전체 1인 합계 | `max_budget_per_person`은 현재 장소별 예상가격 기준 MVP | 단일 장소와 전체 코스 예산을 합의 없이 같은 값으로 취급하지 않기 |
| 참가자 조건 | 작성자 ID를 가진 `Constraint` 목록, 참가자별 직접 제외 | 조건 목록을 검증하는 구조화 데이터 | 공통 조건 형식·입력자 ID·필수/선호·중복 삭제 권한을 합의 |

조건 해석 담당의 최신 `feature/condition-ai` 확인 기준 결과는 `region`, `people`, `preferences`, `exclusions`, `course`, `members`, `clarifications`, `is_ready` 등을 담는 별도 구조다. 이 결과를 현재 잇플 담당의 `Constraint`·지역·순서로 바꾸는 통합 코드는 아직 없다. 모호한 조건이나 `blocking` 확인 질문을 건너뛰지 않도록 조건 담당과 입력 계약을 정한다. 작성자 닉네임을 서버 인증 ID로 간주하지 않는다.

## 연결 순서와 합의가 필요한 사항

1. 잇플 담당은 실제 사용이 허용된 호출 경로와 해당 응답의 필드를 확인하고, `merUrl`을 변형하지 않고 전달한다. 직접 제휴 API와 k-skill 프록시의 권한·요청 형식은 구분한다.
2. 조건 담당과 `is_ready` 및 확인 질문, `members`의 작성자 식별, 선호·필수 조건, 음식 제외 범위를 합의하고 변환한다. 잇플에서 재료·가격 등이 확인되지 않을 때는 미확인으로 유지한다.
3. 검증 담당과 장소 모델·ID·주소·좌표·판정 상태·단위를 맞추고 동일한 입력으로 두 모듈을 함께 검증한다. 상대의 정규화 모듈은 현재 네트워크 호출 기능이 아니라 단일 레코드 변환 기능이다.
4. 방·프론트 담당은 인증·조건 저장·전파를 관리하고, 조건이 바뀔 때 `search_group_places`의 전체 기준 후보와 현재 조건·제외 기록을 `evaluate_group_candidates`에 전달한다. 조회 지역·업종이 바뀌면 후보를 재조회한다. 추천 리비전 확인과 작성자 권한은 방 서버 책임이다.
5. 팀 프론트에서 입력 → 조건 표시 → 후보/코스 → 잇플 상세 링크를 연결하고, 서로 다른 브라우저 세션과 실제 응답으로 검증한다. 링크 유입·공모전 집계는 별도로 확인한다.

결정이 필요한 사항: 재료를 싫어하는 것과 알레르기를 어떻게 구분할지, 정보 미확인 후보의 표시 방식, 가격의 기준, 지역의 의미, 조회 100건 제한 시 안내, 세 곳 이상 데이트 코스의 대상·순서, 잇플의 TM128 위치를 검증할 방법. 현재 카페·식당 2곳 조합은 MVP이며 잇플의 전체 업종이 두 종류뿐이라는 의미는 아니다.
