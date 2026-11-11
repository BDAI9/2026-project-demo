"""OpenRouter로 자연어 조건을 JSON 형식으로 바꾼다.

API 키는 환경 변수(또는 .env)의 OPENROUTER_API_KEY에서 읽는다. 키를 코드에 쓰지 않는다.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from .prompts import build_messages
from .schema import empty_draft
from .vocab import canonicalize

try:  # .env 파일이 있으면 읽는다 (python-dotenv가 없어도 동작)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
TIMEOUT_SECONDS = 20


class LLMError(Exception):
    """AI 해석 실패. message는 사용자에게 보여줘도 되는 한국어 문장."""


def get_api_key() -> Optional[str]:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return key or None


def call_openrouter(messages: list[dict], api_key: str, model: Optional[str] = None) -> str:
    """OpenRouter 호출 후 모델 응답 텍스트를 돌려준다. 실패하면 LLMError."""
    import requests

    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Title": "BDAI 2026 project demo",
            },
            json={
                "model": model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL),
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.Timeout as e:
        raise LLMError("AI 응답이 너무 늦어요.") from e
    except requests.RequestException as e:
        raise LLMError("AI 서버에 연결하지 못했어요.") from e

    if resp.status_code == 401:
        raise LLMError("OpenRouter API 키가 올바르지 않아요.")
    if resp.status_code == 402:
        raise LLMError("OpenRouter 크레딧이 부족해요.")
    if resp.status_code == 429:
        raise LLMError("AI 요청이 너무 많아요. 잠시 후 다시 시도해 주세요.")
    if resp.status_code >= 400:
        raise LLMError(f"AI 서버 오류가 났어요. (HTTP {resp.status_code})")

    try:
        return resp.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LLMError("AI 응답 형식이 예상과 달라요.") from e


def parse_json_text(text: str) -> dict:
    """모델이 ```json 블록이나 앞뒤 설명을 붙여도 JSON 객체만 꺼낸다."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise LLMError("AI 응답에서 JSON을 찾지 못했어요.")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LLMError("AI 응답 JSON이 깨져 있어요.") from e
    if not isinstance(obj, dict):
        raise LLMError("AI 응답이 JSON 객체가 아니에요.")
    return obj


def _str_list(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if isinstance(v, (str, int, float)) and str(v).strip()]


def _dedup(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def normalize_llm_output(obj: dict) -> dict:
    """AI가 준 값을 타입 검사하고 사전의 표준 이름으로 맞춰 초안으로 만든다."""
    draft = empty_draft()

    region = obj.get("region")
    draft["region"] = str(region).strip() if isinstance(region, str) and region.strip() else None
    if draft["region"]:
        draft["region_candidates"] = [draft["region"]]

    people = obj.get("people")
    if isinstance(people, bool):
        people = None
    if isinstance(people, str) and people.strip().isdigit():
        people = int(people.strip())
    draft["people"] = people if isinstance(people, int) and 0 < people <= 100 else None

    prefs, excl, atmos = [], [], []
    for v in _str_list(obj.get("preferences")):
        name, kind, force = canonicalize(v)
        (excl if force == "neg" else atmos if kind == "atmosphere" else prefs).append(name)
    for v in _str_list(obj.get("exclusions")):
        excl.append(canonicalize(v)[0])
    for v in _str_list(obj.get("atmosphere")):
        name, _, force = canonicalize(v)
        (excl if force == "neg" else atmos).append(name)
    draft["preferences"] = _dedup(prefs)
    draft["exclusions"] = _dedup(excl)
    draft["atmosphere"] = _dedup(atmos)
    draft["place_types"] = _dedup(canonicalize(v)[0] for v in _str_list(obj.get("place_types")))

    course = []
    raw_course = obj.get("course") if isinstance(obj.get("course"), list) else []
    for step in raw_course:
        if isinstance(step, str):
            step = {"place_type": step}
        if not isinstance(step, dict) or not str(step.get("place_type", "")).strip():
            continue
        course.append({
            "order": len(course) + 1,
            "place_type": canonicalize(str(step["place_type"]))[0],
            "preferences": _dedup(canonicalize(v)[0] for v in _str_list(step.get("preferences"))),
        })
    draft["course"] = course

    notes = obj.get("notes")
    draft["notes"] = notes.strip() if isinstance(notes, str) and notes.strip() else None

    for a in obj.get("ambiguities") or []:
        if isinstance(a, dict) and str(a.get("question", "")).strip():
            draft["ambiguities"].append({
                "field": str(a.get("field") or "기타"),
                "question": str(a["question"]).strip(),
                "options": _str_list(a.get("options")),
            })
    return draft


def parse_llm(conversation: str, mode_label: str, api_key: Optional[str] = None,
              model: Optional[str] = None) -> dict:
    """대화를 AI로 해석해 초안을 돌려준다. 실패하면 LLMError."""
    api_key = api_key or get_api_key()
    if not api_key:
        raise LLMError("OPENROUTER_API_KEY가 설정되지 않았어요.")
    content = call_openrouter(build_messages(conversation, mode_label), api_key, model)
    return normalize_llm_output(parse_json_text(content))
