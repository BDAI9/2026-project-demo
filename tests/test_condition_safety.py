"""User-facing safety regressions for conditions that must not disappear."""

import pytest

from condition_ai import parse_conditions
from condition_ai.schema import empty_draft


def blocking_questions(result):
    return [item for item in result["clarifications"] if item.get("blocking")]


@pytest.mark.parametrize("term", ["계란", "복숭아", "견과류"])
def test_unknown_allergy_never_silently_permits_search(term):
    text = f"강남에서 4명, {term} 알레르기가 있어요"
    result = parse_conditions(text, "group", use_llm=False)
    assert result["region"] == "강남"
    assert result["is_ready"] is False
    assert any(term in item["question"] for item in blocking_questions(result))


def test_unknown_exclusion_remains_visible_and_blocking():
    result = parse_conditions("강남에서 4명, 치즈 빼줘", "group", use_llm=False)
    assert result["region"] == "강남"
    assert result["is_ready"] is False
    assert any("치즈" in item["question"] for item in blocking_questions(result))


def test_mixed_recognized_and_unknown_exclusion_is_not_truncated():
    result = parse_conditions([
        {"speaker": "민수", "text": "강남에서 4명"},
        {"speaker": "지영", "text": "해산물이랑 치즈 빼줘"},
    ], "group", use_llm=False)
    assert "해산물" in result["exclusions"]
    assert not result["is_ready"]
    assert any(item["kind"] == "exclusion" and item["speaker"] == "지영" and "치즈" in item["text"]
               for item in result["unresolved_inputs"])


def test_known_exclusion_does_not_require_unsupported_input_confirmation():
    result = parse_conditions("강남에서 4명, 매운 음식과 해산물은 제외", "group", use_llm=False)
    assert result["is_ready"]
    assert result["unresolved_inputs"] == []


@pytest.mark.parametrize("budget", ["1인 2만원 이하", "예산은 3만원", "너무 비싸지 않게"])
def test_unhandled_budget_never_silently_permits_search(budget):
    result = parse_conditions(f"강남에서 4명, {budget}", "group", use_llm=False)
    assert result["is_ready"] is False
    assert any(item["field"] == "budget" for item in blocking_questions(result))


def test_llm_success_does_not_erase_unsupported_budget_or_allergy(monkeypatch):
    def incomplete_llm(*args, **kwargs):
        draft = empty_draft()
        draft.update(region="강남", people=4)
        return draft

    monkeypatch.setattr("condition_ai.parser.parse_llm", incomplete_llm)
    result = parse_conditions("강남 4명, 1인 2만원 이하, 계란 알레르기", "group", use_llm=True)
    assert result["source"] == "llm"
    assert result["is_ready"] is False
    clarifications = blocking_questions(result)
    assert any(item["field"] == "budget" for item in clarifications)
    assert any("계란" in item["question"] for item in clarifications)


def test_unrecognized_speaker_condition_keeps_owner_visible():
    messages = [
        {"speaker": "민수", "text": "강남에서 4명"},
        {"speaker": "지영", "text": "복숭아 알레르기 있어요"},
    ]
    result = parse_conditions(messages, "group", use_llm=False)
    assert result["is_ready"] is False
    assert any("복숭아" in item["question"] and "지영" in item["question"]
               for item in blocking_questions(result))


def test_region_is_not_negated_by_an_unrelated_food_exclusion():
    result = parse_conditions("강남에서 4명 해산물 싫어", "group", use_llm=False)
    assert result["region"] == "강남"
    assert "해산물" in result["exclusions"]


def test_conversation_speakers_do_not_establish_party_size():
    result = parse_conditions([
        {"speaker": "민수", "text": "강남에서 보자"},
        {"speaker": "지영", "text": "좋아"},
    ], "group", use_llm=False)
    assert result["people"] is None or any(
        item["field"] == "people" for item in blocking_questions(result)
    )


def test_llm_cannot_invent_a_group_headcount(monkeypatch):
    def invented_people(*args, **kwargs):
        draft = empty_draft()
        draft.update(region="강남", people=2)
        return draft

    monkeypatch.setattr("condition_ai.parser.parse_llm", invented_people)
    result = parse_conditions("강남에서 보자", "group", use_llm=True)
    assert result["people"] is None
    assert not result["is_ready"]
    assert any(item["field"] == "people" for item in blocking_questions(result))
