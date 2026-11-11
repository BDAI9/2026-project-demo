# 좌표 확보/검증 방법

- 잇플에서 제공한 장소명·주소를 원본으로 보관합니다.
- 카카오 로컬 API의 장소/주소 검색 결과에서 `x`(경도), `y`(위도)를 확보합니다.
- 장소명+주소를 대조하고 일치했을 때만 `coordinate_verified=true`로 바꿉니다.
- 출처는 `coordinate_source=kakao_local`, 근거는 `coordinate_evidence`에 기록합니다.
- 다른 좌표계(예: TM128)를 WGS84 위도/경도에 그대로 복사하지 않습니다.
- `validation.haversine_km`는 직선거리이며 실제 도보 거리/소요시간이 아닙니다.
- 검색 결과를 신뢰할 수 없으면 `coordinate_verified=false`로 남기고, 결과를 `needs_verification`으로 표시합니다.

참고: https://developers.kakao.com/docs/latest/ko/local/dev-guide
