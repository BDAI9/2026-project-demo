"""조건 해석 모듈 테스트.  실행: python -m pytest tests -q

AI 호출은 실제로 하지 않고 가짜 응답으로 바꿔서 검사한다 (키·인터넷 없이 실행 가능).
"""

import json

import pytest
import requests

from condition_ai import parse_conditions


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def rule(text, mode):
    return parse_conditions(text, mode, use_llm=False)


# ---- 기획서 예시 ----------------------------------------------------------

def test_group_example_from_plan():
    r = rule("강남에서 4명, 매운 음식과 해산물은 제외", "group")
    assert r["region"] == "강남"
    assert r["people"] == 4
    assert r["exclusions"] == ["매운 음식", "해산물"]
    assert r["is_ready"] is True
    assert r["course"] == []


def test_date_example_from_plan():
    r = rule("홍대에서 카페 → 식사 → 술집", "date")
    assert r["region"] == "홍대"
    assert [s["place_type"] for s in r["course"]] == ["카페", "식당", "술집"]
    assert [s["order"] for s in r["course"]] == [1, 2, 3]
    assert r["people"] == 2
    assert r["is_ready"] is True


# ---- 단톡 입력 --------------------------------------------------------------

def test_group_chat_members_and_conflict():
    chat = (
        "민수: 강남역 근처 어때?\n"
        "지영: 난 해산물 알레르기 있어\n"
        "현우: 고기랑 해산물 먹고 싶다, 근데 시끄러운 데는 별로"
    )
    r = rule(chat, "group")
    assert r["region"] == "강남"
    assert r["people"] == 3  # 인원을 말하지 않아 참여자 수로 가정
    assert any(a["field"] == "people" for a in r["assumptions"])
    assert "해산물" in r["exclusions"] and "해산물" not in r["preferences"]
    assert "시끄러운" in r["exclusions"]
    conflict = [c for c in r["clarifications"] if c["type"] == "conflict"]
    assert conflict and "현우" in conflict[0]["question"] and "지영" in conflict[0]["question"]
    names = [m["name"] for m in r["members"]]
    assert names == ["민수", "지영", "현우"]


def test_list_of_dict_input():
    r = rule([{"speaker": "A", "text": "성수에서 보자"}, {"speaker": "B", "text": "고기 좋아"}], "group")
    assert r["region"] == "성수"
    assert r["members"][1]["preferences"] == ["고기"]


def test_kakao_export_format():
    r = rule("[민수] [오후 3:02] 합정에서 5명이야", "group")
    assert r["region"] == "합정" and r["people"] == 5
    assert r["members"][0]["name"] == "민수"


def test_people_changes_in_chat():
    r = rule("홍대에서 3명인데\n아 한 명 더 온대", "group")
    assert r["people"] == 4


# ---- 표현 처리 --------------------------------------------------------------

def test_except_expression_and_not_spicy():
    r = rule("연남에서 해산물 말고 고기, 안 매운 거로", "group")
    assert r["preferences"] == ["고기"]
    assert set(r["exclusions"]) == {"해산물", "매운 음식"}


def test_region_negated_with_malgo():
    r = rule("강남 말고 홍대에서 보자 3명", "group")
    assert r["region"] == "홍대"


def test_time_is_not_a_speaker():
    r = rule("저녁 7:30에 연남에서, 술은 안 마셔", "date")
    assert r["members"] == []
    assert "술집" in r["exclusions"]
    assert all(s["place_type"] != "술집" for s in r["course"])


def test_food_only_date_creates_restaurant_step():
    r = rule("성수에서 파스타 먹고 카페 가고 싶어", "date")
    assert [s["place_type"] for s in r["course"]] == ["식당", "카페"]
    assert r["course"][0]["preferences"] == ["양식"]


# ---- 모호·누락 -------------------------------------------------------------

def test_missing_region_blocks():
    r = rule("4명이고 고기 먹고 싶어", "group")
    assert r["region"] is None
    assert r["is_ready"] is False
    assert any(c["field"] == "region" and c["blocking"] for c in r["clarifications"])


def test_multiple_regions_ask_with_options():
    r = rule("강남이나 홍대에서 보자", "group")
    c = next(c for c in r["clarifications"] if c["field"] == "region")
    assert c["type"] == "ambiguous" and c["options"] == ["강남", "홍대"]
    assert r["is_ready"] is False


def test_date_default_course_is_marked_as_assumption():
    r = rule("홍대에서 만나", "date")
    assert [s["place_type"] for s in r["course"]] == ["카페", "식당"]
    assert any(a["field"] == "course" for a in r["assumptions"])


def test_date_mode_with_many_people_suggests_group():
    r = rule("홍대 4명", "date")
    assert any(c["field"] == "mode" for c in r["clarifications"])


def test_empty_input():
    r = rule("   ", "group")
    assert r["is_ready"] is False
    assert r["clarifications"][0]["field"] == "input"


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        parse_conditions("강남", "picnic")


def test_korean_mode_name():
    assert rule("강남 2명", "데이트")["mode"] == "date"


def test_result_is_json_serializable():
    json.dumps(rule("강남에서 4명", "group"), ensure_ascii=False)


# ---- AI(OpenRouter) 경로: 가짜 응답 ----------------------------------------

class FakeResp:
    def __init__(self, status=200, content=None):
        self.status_code = status
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def fake_post(status=200, content=None, exc=None):
    def _post(*args, **kwargs):
        if exc:
            raise exc
        return FakeResp(status, content)
    return _post


def test_llm_success_and_safety_merge(monkeypatch):
    content = json.dumps({
        "region": "강남", "people": 4, "preferences": ["삼겹살"], "exclusions": ["매운 거"],
        "atmosphere": [], "place_types": [], "course": [], "notes": "7시 이후", "ambiguities": [],
    }, ensure_ascii=False)
    monkeypatch.setattr(requests, "post", fake_post(content=content))
    r = parse_conditions("강남 4명, 삼겹살 먹자. 매운 거랑 해산물은 빼줘", "group", api_key="test")
    assert r["source"] == "llm"
    assert r["preferences"] == ["고기"]  # 표준 이름으로 정리
    assert "매운 음식" in r["exclusions"]
    assert "해산물" in r["exclusions"]  # AI가 놓친 제외 조건을 규칙 결과로 보완
    assert r["notes"] == "7시 이후"


def test_llm_json_in_code_block(monkeypatch):
    content = '```json\n{"region": "홍대", "people": null, "course": ["카페", "식사"]}\n```'
    monkeypatch.setattr(requests, "post", fake_post(content=content))
    r = parse_conditions("홍대에서 카페 갔다가 밥", "date", api_key="test")
    assert r["source"] == "llm"
    assert [s["place_type"] for s in r["course"]] == ["카페", "식당"]


def test_llm_invented_region_is_not_trusted(monkeypatch):
    content = json.dumps({"region": "이태원", "people": 3})
    monkeypatch.setattr(requests, "post", fake_post(content=content))
    r = parse_conditions("3명이서 고기 먹자", "group", api_key="test")
    assert r["region"] is None
    assert any(c["type"] == "unverified" for c in r["clarifications"])
    assert r["is_ready"] is False


@pytest.mark.parametrize("post, msg", [
    (fake_post(status=401), "API 키"),
    (fake_post(status=429), "너무 많아요"),
    (fake_post(status=500), "HTTP 500"),
    (fake_post(content="죄송해요, 모르겠어요"), "JSON"),
    (fake_post(exc=requests.Timeout()), "늦어요"),
    (fake_post(exc=requests.ConnectionError()), "연결"),
])
def test_llm_errors_fall_back_to_rule(monkeypatch, post, msg):
    monkeypatch.setattr(requests, "post", post)
    r = parse_conditions("강남에서 4명, 해산물 제외", "group", api_key="test")
    assert r["source"] == "rule"
    assert r["region"] == "강남" and r["exclusions"] == ["해산물"]
    assert r["warnings"] and msg in r["warnings"][0]


def test_no_key_uses_rule_without_calling_api(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("API를 호출하면 안 돼요")
    monkeypatch.setattr(requests, "post", boom)
    r = parse_conditions("강남 4명", "group")
    assert r["source"] == "rule" and r["warnings"] == []
