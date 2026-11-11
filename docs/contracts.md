# 장소·코스 모듈 임시 계약

팀 공통 계약이 아직 없는 초기 저장소에서 담당 범위를 독립적으로 테스트하기 위한 제안이다. 서버·프론트엔드·조건 해석 담당자와 합의 후 공통 API와 직렬화 형식으로 확정해야 한다.

- `Place`: `id`, `name`, `category` (`cafe` / `restaurant` 등), `address`, WGS84 `latitude` / `longitude` 쌍 또는 `None`, `attributes`, `eatpl_url`, `source`. 샘플 `source`는 `mock`, 실제 잇플은 `eatpl`. 원본 링크가 없는 샘플에는 이동 링크가 없다.
- `Fact`: `value`, `source`, `complete`. 출처나 값이 없으면 미확인이다. 목록에서 값이 없다는 사실은 완전한 목록(`complete=True`)일 때만 확인할 수 있다. 가게 업종만으로 재료·알레르기 부재를 추론하지 않는다.
- `Constraint`: `id`, `owner_id`, `field`, `operator` (`eq`, `neq`, `lte`, `gte`, `contains`, `excludes`), `value`, `strength` (`hard` / `soft`), `scope` (`room` / `stop`), `stop_index`, `active`. 자연어 원문, 수정 버전, 권한 검증은 방·조건 담당 모듈과 통합할 때 전달·관리해야 한다.
- `evaluate_candidates`: 전체 기준 후보와 현재 유효한 조건, 직접 제외된 장소 ID, 인원, 코스 인덱스를 받는다. 결과는 `eligible`, `needs_review`, `excluded`로 구분한다. 직접 제외의 작성자별 기록과 복구 판단은 호출자가 관리한다. 매번 전체 기준 후보를 다시 평가한다.
- `build_courses`: 카페·식당 순서, 장소별 조건, 직접 제외, 인원, 구간별 최대 직선거리, 코스 전체 1인 예산, 고정 장소를 받는다. `fixed_stops`는 유지할 장소의 인덱스와 ID다. 다른 장소를 바꾸거나 순서를 바꿀 때 함수를 다시 호출하면 전체 조건을 다시 검사한다. 한 장소 예산은 `price_per_person_krw` 조건으로, 코스 총예산은 `max_total_per_person_krw`로 구분한다.
- 거리는 WGS84 좌표가 모두 있을 때만 미터 단위 직선거리다. 거리 제한을 적용했는데 좌표가 없거나 총예산 제한을 적용했는데 가격이 없으면 `needs_review`다. 도보 경로·시간은 계산하지 않는다.
- 추천 결과의 입력 리비전 확인, 사용자 인증, 조건 작성자 권한과 실시간 전송은 이 순수 모듈 밖의 서버 책임이다. 외부 조회는 별도로 로딩·오류 처리한다.

예산 평가에 쓰는 `price_per_person_krw`는 확인된 장소별 1인 비용만 뜻한다. 가격 또는 인원 정보가 제공되지 않았으면 필수 조건을 충족한 것으로 처리하지 않는다. 선호 점수는 참가자별 조건 평균을 다시 참가자 간 평균하여 문장 수가 많은 사람의 가중치가 커지지 않도록 한다.

로컬 데이트 검색 API는 선택적 `constraints` 배열을 받아 각 조건의 `id`, `owner_id`, `field`, `operator`, `value`, `strength`, `scope`, `stop_index`, `active`를 검증한다. 인식하지 못하는 요청 키는 무시하지 않고 거부한다. `owner_id`는 이 데모에서 선호도를 묶는 값일 뿐 인증 정보가 아니다. 화면의 해산물 제외는 `contains_seafood = false`로 표현하며 신뢰할 수 있는 출처가 해산물 부재를 명시한 경우에만 충족한다. 단순 재료명 목록에서 ‘해산물’이라는 단어가 없다는 이유로 새우 등 해산물이 없다고 단정하지 않는다. 공식 잇플 데이터에는 이 속성이 없어 확인 필요다.

## 공동 장소 후보와 방 서버 연결

`backend.app.place_search.search_group_places`는 잇플 provider, 거래추적번호, 지역과 선택적 업종·가게명, 참가자별 `Constraint` 및 `CandidateExclusion` 목록을 받는다. 결과에는 재평가용 `baseline_places`, `candidates.eligible` / `needs_review` / `excluded`, 데이터 출처, `truncated`가 있다. 각 후보에는 장소·판정 이유와 활성 직접 제외 기록이 포함된다. 빈 결과와 외부 호출 실패는 구분되며 실패 시 샘플로 자동 대체하지 않는다. 검색 결과는 카페·식당으로 제한하지 않고 원본 업종 `business_type`과 잇플 링크를 보존한다.

공유 방의 조건이나 직접 제외가 바뀌면 보관한 `baseline_places`와 **현재 전체 조건·제외 기록**을 `backend.app.recommendations.group.evaluate_group_candidates`에 전달한다. 한 사람의 조건을 지워도 다른 사람의 조건은 유지되며, 같은 장소에 대해 다른 사람의 직접 제외가 남아 있으면 후보로 복귀하지 않는다. 해당 함수는 채팅이나 다중 접속 기능이 아니며, 방 서버가 작성자 권한, 저장·동기화와 추천 입력 리비전을 관리해야 한다. 지역·조회 업종 같은 검색 기준을 바꾸면 기준 후보를 새로 조회해야 한다.

데이트 코스 조합기는 현재 카페와 식당 두 곳의 순서만 지원한다. 잇플의 업종 범위와 코스 조합기의 현재 범위는 별개이며, 영화관·공원 같은 장소까지 확장하려면 적합한 추가 데이터 소스를 확인해야 한다.
