"""AI 모델 순차 시도와 통합 화면 AI 스위치 테스트 (실제 API는 호출하지 않음)."""

import json

import pytest
import requests

from condition_ai import parse_conditions
from condition_ai.llm_parser import DEFAULT_MODELS, get_models

OK = json.dumps({"region": "강남", "people": 4, "exclusions": ["해산물"]}, ensure_ascii=False)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "CONDITION_AI_USE_LLM"):
        monkeypatch.delenv(k, raising=False)


class Resp:
    def __init__(self, status, content=None):
        self.status_code, self._content = status, content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def scripted(monkeypatch, answers):
    """모델 이름별 응답을 정해 두고, 호출된 모델 순서를 기록한다."""
    calls = []

    def post(url, headers=None, json=None, timeout=None):
        calls.append(json["model"])
        status, content = answers[json["model"]]
        return Resp(status, content)

    monkeypatch.setattr(requests, "post", post)
    return calls


def test_model_list_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", " a:free , b:free ,")
    assert get_models() == ["a:free", "b:free"]


def test_default_models_when_unset():
    assert get_models() == DEFAULT_MODELS


def test_falls_through_to_next_model_on_429_and_404(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "busy:free,gone:free,good:free")
    calls = scripted(monkeypatch, {"busy:free": (429, None), "gone:free": (404, None), "good:free": (200, OK)})
    r = parse_conditions("강남 4명 해산물 빼고", "group", api_key="test")
    assert calls == ["busy:free", "gone:free", "good:free"]
    assert r["source"] == "llm" and r["warnings"] == []


def test_broken_json_tries_next_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "chatty:free,good:free")
    calls = scripted(monkeypatch, {"chatty:free": (200, "모르겠어요"), "good:free": (200, OK)})
    assert parse_conditions("강남 4명", "group", api_key="test")["source"] == "llm"
    assert calls == ["chatty:free", "good:free"]


def test_bad_key_stops_immediately(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "a:free,b:free")
    calls = scripted(monkeypatch, {"a:free": (401, None), "b:free": (200, OK)})
    r = parse_conditions("강남 4명", "group", api_key="test")
    assert calls == ["a:free"]
    assert r["source"] == "rule" and "API 키" in r["warnings"][0]


def test_all_models_fail_falls_back_to_rule(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "a:free,b:free")
    scripted(monkeypatch, {"a:free": (429, None), "b:free": (503, None)})
    r = parse_conditions("강남에서 4명, 해산물 제외", "group", api_key="test")
    assert r["source"] == "rule" and r["exclusions"] == ["해산물"]
    assert "2개를 모두 시도" in r["warnings"][0]


def test_integration_uses_rule_by_default(monkeypatch):
    from backend.app import team_integration

    def boom(*a, **k):
        raise AssertionError("기본값에서는 API를 호출하면 안 돼요")
    monkeypatch.setattr(requests, "post", boom)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    out = team_integration.interpret({"text": "강남에서 4명, 해산물 제외", "product_mode": "group"})
    assert out["proposal"]["source"] == "rule"


def test_integration_uses_llm_when_enabled(monkeypatch):
    from backend.app import team_integration

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("CONDITION_AI_USE_LLM", "1")
    monkeypatch.setenv("OPENROUTER_MODEL", "good:free")
    scripted(monkeypatch, {"good:free": (200, OK)})
    out = team_integration.interpret({"text": "강남에서 4명, 해산물 제외", "product_mode": "group"})
    assert out["proposal"]["source"] == "llm"
