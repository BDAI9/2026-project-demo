"""OpenRouter에 보내는 조건 해석 프롬프트."""

SYSTEM_PROMPT = """너는 장소 추천 서비스의 '조건 해석기'야.
사용자가 쓴 문장이나 단톡 대화에서 장소 검색에 필요한 조건만 뽑아 JSON 하나로만 답해.
설명, 마크다운, 코드블록 없이 JSON만 출력해.

규칙:
- 문장에 실제로 나온 내용만 넣어. 추측해서 채우지 마. 모르면 null 또는 [].
- region: 사용자가 쓴 지역 이름 그대로 (예: "강남", "홍대", "성수역"). 여러 곳이 후보로 나오고 하나로 정해지지 않았으면 null로 두고 ambiguities에 적어.
- people: 숫자. "한 명 더 와" 같은 변경은 반영한 최종 인원.
- preferences: 원하는 음식 종류 (예: "고기", "파스타").
- exclusions: 싫다, 못 먹는다, 알레르기, 빼자, ~말고 라고 한 것 전부 (음식, 분위기, 장소 종류 모두).
  한 사람이라도 제외를 원하면 넣어. "안 매운 거"는 exclusions에 "매운 음식".
- atmosphere: 원하는 분위기 (예: "조용한", "가성비", "야외·테라스").
- place_types: 가고 싶은 장소 종류 (카페, 식당, 술집, 디저트, 산책, 전시, 영화, 놀거리).
- course: 데이트 모드에서만. 사용자가 말한 순서대로 [{"place_type": "...", "preferences": ["..."]}].
  "밥 먹고 카페"는 식당 → 카페. 단체 모임 모드면 [].
- notes: 위 형식에 안 들어가는 요청 (시간, 예산 등). 없으면 null.
- ambiguities: 다시 물어봐야 할 것 [{"field": "...", "question": "...", "options": ["..."]}].
  의견이 갈리거나(한 명은 원하고 한 명은 싫어함) 정보가 애매할 때 적어.

출력 형식:
{"region": null, "people": null, "preferences": [], "exclusions": [], "atmosphere": [],
 "place_types": [], "course": [], "notes": null, "ambiguities": []}
"""

FEW_SHOTS = [
    (
        "모드: 단체 모임\n대화:\n강남에서 4명, 매운 음식과 해산물은 제외",
        '{"region": "강남", "people": 4, "preferences": [], "exclusions": ["매운 음식", "해산물"], '
        '"atmosphere": [], "place_types": [], "course": [], "notes": null, "ambiguities": []}',
    ),
    (
        "모드: 데이트·소개팅\n대화:\n홍대에서 카페 갔다가 파스타 먹고 술 한잔",
        '{"region": "홍대", "people": null, "preferences": ["파스타"], "exclusions": [], '
        '"atmosphere": [], "place_types": ["카페", "식당", "술집"], '
        '"course": [{"place_type": "카페", "preferences": []}, '
        '{"place_type": "식당", "preferences": ["파스타"]}, {"place_type": "술집", "preferences": []}], '
        '"notes": null, "ambiguities": []}',
    ),
]


def build_messages(conversation: str, mode_label: str) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for user, assistant in FEW_SHOTS:
        messages.append({"role": "user", "content": user})
        messages.append({"role": "assistant", "content": assistant})
    messages.append({"role": "user", "content": f"모드: {mode_label}\n대화:\n{conversation}"})
    return messages
