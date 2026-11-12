"""Location polarity must not inherit exclusions for food or activities."""

import json

import pytest

from condition_ai import parse_conditions


@pytest.mark.parametrize("sentence, expected_exclusion", [
    ("강남에서 4명 해산물 싫어", "해산물"),
    ("강남에서 4명 견과류 빼줘", "견과류"),
    ("강남에서 해산물 말고 고기", "해산물"),
    ("강남역 근처에서 4명 해산물 제외", "해산물"),
])
def test_food_exclusion_does_not_exclude_location(sentence, expected_exclusion):
    result = parse_conditions(sentence, "group", use_llm=False)
    assert result["region"] == "강남"
    assert expected_exclusion in result["exclusions"]


@pytest.mark.parametrize("sentence, expected_region", [
    ("강남 말고 홍대에서 보자 3명", "홍대"),
    ("강남 말고 성수에서 보자 3명", "성수"),
    ("강남은 싫어", None),
    ("강남에서 만나기 싫어", None),
])
def test_explicit_location_exclusion_is_preserved(sentence, expected_region):
    result = parse_conditions(sentence, "group", use_llm=False)
    assert result["region"] == expected_region
    if expected_region is None:
        assert not result["is_ready"]


def test_multiple_locations_remain_ambiguous():
    result = parse_conditions("강남에서 해산물 싫어, 홍대에서 고기 좋아", "group", use_llm=False)
    assert result["region"] is None
    assert not result["is_ready"]


def test_location_explicitly_rejected_after_positive_mention_is_not_restored():
    result = parse_conditions("강남에서 해산물은 싫어, 강남은 싫어", "group", use_llm=False)
    assert result["region"] is None
    assert not result["is_ready"]


@pytest.mark.parametrize("sentence,llm_region", [
    ("강남은 싫어", "강남"),
    ("강남 말고 홍대에서 3명", "강남"),
    ("강남역 말고 홍대에서 3명", "강남역"),
])
def test_llm_must_not_select_a_region_the_user_rejected(monkeypatch, sentence, llm_region):
    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"region": llm_region, "people": 3}, ensure_ascii=False)}}]}

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: Response())
    result = parse_conditions(sentence, "group", use_llm=True, api_key="example")
    assert result["source"] == "llm"
    assert result["region"] is None
    assert not result["is_ready"]
    assert any(c["field"] == "region" and c["blocking"] for c in result["clarifications"])
