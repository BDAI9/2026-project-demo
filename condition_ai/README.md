# condition_ai — 조건 해석·AI (백엔드 ①)

사용자가 입력한 문장이나 단톡 대화에서 **지역·인원·선호·제외 조건**을, 데이트 모드에서는 **장소 종류와 순서**까지 뽑아 공통 형식(dict)으로 돌려줍니다.
프론트엔드와 잇플 연결 담당은 아래 **공통 입력 형식**만 보면 됩니다.

## 빠르게 써보기

```bash
pip install -r condition_ai/requirements.txt
python -m condition_ai --mode group --no-llm "강남에서 4명, 매운 음식과 해산물은 제외"
python -m condition_ai --mode date  --no-llm "홍대에서 카페 → 식사 → 술집"
python -m pytest tests -q
```

```python
from condition_ai import parse_conditions

result = parse_conditions("강남에서 4명, 매운 음식과 해산물은 제외", mode="group")
if result["is_ready"]:
    ...  # 잇플 검색으로 넘기기
else:
    for c in result["clarifications"]:
        print(c["question"], c["options"])  # 사용자에게 다시 물어보기
```

### 입력으로 받을 수 있는 것

| 형태 | 예 |
| --- | --- |
| 문자열 한 줄 | `"강남에서 4명, 해산물 제외"` |
| 여러 줄 단톡 | `"민수: 강남 어때?\n지영: 해산물 알레르기 있어"` |
| 카카오톡 내보내기 줄 | `"[민수] [오후 3:02] 강남 어때?"` |
| 메시지 리스트 (프론트 권장) | `[{"speaker": "민수", "text": "강남 어때?"}, ...]` |

`mode`는 `"group"`(단체 모임) 또는 `"date"`(데이트·소개팅)이고, `"데이트"`, `"단체 모임"`처럼 한국어로 넘겨도 됩니다.

## 공통 입력 형식 (결과 dict)

```json
{
  "schema_version": "1.0",
  "mode": "date",
  "region": "홍대",
  "people": 2,
  "preferences": ["양식"],
  "exclusions": ["해산물"],
  "atmosphere": ["조용한"],
  "place_types": ["카페", "식당", "술집"],
  "course": [
    {"order": 1, "place_type": "카페", "preferences": []},
    {"order": 2, "place_type": "식당", "preferences": ["양식"]},
    {"order": 3, "place_type": "술집", "preferences": []}
  ],
  "members": [{"name": "민수", "preferences": ["고기"], "exclusions": ["해산물"]}],
  "notes": null,
  "clarifications": [
    {"field": "region", "type": "missing", "question": "어느 지역에서 찾을까요?", "options": [], "blocking": true}
  ],
  "assumptions": [{"field": "people", "value": 2, "reason": "데이트 모드 기본값 2명이에요."}],
  "warnings": [],
  "is_ready": true,
  "source": "rule",
  "raw_text": "..."
}
```

| 키 | 설명 |
| --- | --- |
| `region` | 지역. 모르거나 후보가 여러 개면 `null` |
| `people` | 인원. 단톡에서 "한 명 더"도 반영. 데이트는 말하지 않으면 2 |
| `preferences` | 원하는 음식 종류 (표준 이름: 한식, 고기, 양식, 일식 …) |
| `exclusions` | **빼야 하는 것 전부** (음식·분위기·장소 종류, 알레르기 포함). 한 명이라도 원하지 않으면 들어감 |
| `atmosphere` | 원하는 분위기 (조용한, 가성비, 야외·테라스 …) |
| `place_types` | 원하는 장소 종류 (카페, 식당, 술집, 디저트, 산책, 전시, 영화, 놀거리) |
| `course` | **데이트 모드 전용.** 순서대로 방문할 장소 종류. 단체 모임은 항상 `[]` |
| `members` | 단톡 입력일 때 사람별 조건. 한 줄 입력이면 `[]` |
| `notes` | 형식에 안 맞는 기타 요청 (시간·예산 등, AI 해석 때만) |
| `clarifications` | 다시 물어볼 질문. `blocking: true`가 하나라도 있으면 검색하지 않음 |
| `assumptions` | 사용자가 말하지 않아 **기본값으로 채운 항목**. 결과 화면에 "가정" 표시 권장 |
| `warnings` | AI 호출 실패 같은 안내 (실패해도 규칙 기반 결과는 정상 반환) |
| `is_ready` | `true`면 바로 잇플 검색에 넘겨도 됨 |
| `source` | `"llm"`(AI 해석) 또는 `"rule"`(규칙 기반) |

`clarifications[].type`: `missing`(정보 없음) · `ambiguous`(후보 여러 개) · `conflict`(누구는 원하고 누구는 싫어함 → 일단 제외 처리) · `unverified`(AI가 입력에 없는 값을 냄)

## 동작 방식

1. **규칙 기반 해석** (`rule_parser.py`, `vocab.py`) — API 없이 항상 실행. "말고", "빼줘", "안 매운", "알레르기", "한 명 더" 같은 표현 처리
2. **AI 해석** (`llm_parser.py`, `prompts.py`) — `OPENROUTER_API_KEY`가 있으면 OpenRouter로 자연어를 JSON으로 변환
3. **합치기·검증** (`parser.py`)
   - AI 결과를 기본으로 쓰되 **제외 조건은 규칙 결과와 합침** (AI가 놓쳐도 빠지지 않게)
   - AI가 입력에 없는 지역을 내면 쓰지 않고 다시 물어봄
   - 선호와 제외가 겹치면 제외를 우선하고 확인 질문 생성
   - AI 오류(키 없음/잘못됨, 크레딧 부족, 요청 과다, 시간 초과, JSON 깨짐)가 나면 규칙 기반 결과로 대신하고 `warnings`에 이유를 남김

## API 키 설정

```bash
cp .env.example .env   # OPENROUTER_API_KEY 값 채우기 (.env는 git에 올라가지 않음)
```

## 알려진 한계

- 규칙 기반은 사전(`vocab.py`)에 있는 단어만 인식합니다. 새 지역·음식은 사전에 추가하세요.
- 규칙 기반 코스 순서는 "말한 순서" 기준이라 "카페 가기 전에 밥" 같은 역순 표현은 AI 해석이 필요합니다.
- 음식은 큰 분류로 묶습니다 (파스타 → 양식, 삼겹살 → 고기).
