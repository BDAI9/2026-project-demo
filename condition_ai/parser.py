"""조건 해석의 진입점: parse_conditions().

흐름: 입력 정리 → 규칙 기반 해석 → (키가 있으면) AI 해석 → 둘을 합침 → 검증·확인 질문 생성
"""

from __future__ import annotations

from typing import Optional

from .llm_parser import LLMError, get_api_key, parse_llm
from .rule_parser import MessageInput, Message, normalize_messages, parse_rule
from .schema import (
    DEFAULT_DATE_COURSE,
    DEFAULT_DATE_PEOPLE,
    MODE_LABELS,
    SCHEMA_VERSION,
    ConditionResult,
    empty_draft,
    normalize_mode,
)


def parse_conditions(
    user_input: MessageInput,
    mode: str,
    use_llm: Optional[bool] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> ConditionResult:
    """사용자 입력을 공통 조건 형식(dict)으로 바꾼다.

    user_input: 문자열(여러 줄 단톡 가능) / 문자열 리스트 / [{"speaker": "민수", "text": "..."}]
    mode: "group"(단체 모임) 또는 "date"(데이트·소개팅). 한국어 이름도 된다.
    use_llm: None이면 OPENROUTER_API_KEY가 있을 때만 AI를 쓴다. False면 규칙 기반만.
    """
    mode = normalize_mode(mode)
    messages = normalize_messages(user_input)
    raw_text = "\n".join(f"{m.speaker}: {m.text}" if m.speaker else m.text for m in messages)
    warnings: list[str] = []

    if not messages:
        draft = empty_draft()
        draft["_empty"] = True
        return _finalize(draft, mode, messages, raw_text, "rule", warnings)

    rule = parse_rule(messages, mode)
    draft, source = rule, "rule"

    if use_llm is None:
        use_llm = bool(api_key or get_api_key())
    if use_llm:
        try:
            llm = parse_llm(raw_text, MODE_LABELS[mode], api_key=api_key, model=model)
            draft, source = _merge(llm, rule, raw_text, mode), "llm"
        except LLMError as e:
            warnings.append(f"{e} 규칙 기반 해석으로 대신했어요.")

    return _finalize(draft, mode, messages, raw_text, source, warnings)


# ---------------------------------------------------------------------------


def _dedup(items):
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _josa(word: str, pair: str) -> str:
    """받침에 따라 '을/를', '이/가' 등을 붙인다."""
    last = word[-1] if word else ""
    has_batchim = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (pair[0] if has_batchim else pair[1])


def _appears(region: str, raw_text: str) -> bool:
    return region in raw_text or region.removesuffix("역") in raw_text


def _merge(llm: dict, rule: dict, raw_text: str, mode: str) -> dict:
    """AI 결과를 기본으로 하되, 안전과 관련된 부분은 규칙 결과로 보완한다."""
    d = dict(llm)
    llm_region_ambiguous = any(a["field"] == "region" for a in llm["ambiguities"])

    if d["region"] and not _appears(d["region"], raw_text):
        # 입력에 없는 지역을 AI가 지어냈을 가능성 → 그대로 쓰지 않는다
        d["_unverified_region"] = d["region"]
        d["region"] = None
        d["region_candidates"] = rule["region_candidates"]
    elif not d["region"] and not llm_region_ambiguous:
        d["region"] = rule["region"]
        d["region_candidates"] = rule["region_candidates"]

    if d["people"] is None:
        d["people"] = rule["people"]
    d["_people_mentions"] = rule.get("_people_mentions", [])

    # 제외 조건은 하나라도 놓치면 안 되므로 규칙 결과와 합친다
    d["exclusions"] = _dedup(llm["exclusions"] + rule["exclusions"])
    if not d["place_types"]:
        d["place_types"] = rule["place_types"]
    if mode == "date" and not d["course"]:
        d["course"] = rule["course"]
    d["members"] = rule["members"]
    return d


def _finalize(draft: dict, mode: str, messages: list[Message], raw_text: str,
              source: str, warnings: list[str]) -> ConditionResult:
    clar: list[dict] = []
    assumptions: list[dict] = []

    def ask(field, type_, question, options=None, blocking=False):
        clar.append({"field": field, "type": type_, "question": question,
                     "options": options or [], "blocking": blocking})

    prefs = list(draft["preferences"])
    excl = list(draft["exclusions"])
    atmos = list(draft["atmosphere"])
    places = list(draft["place_types"])
    course = [dict(s, preferences=list(s["preferences"])) for s in draft["course"]]
    members = draft["members"]
    people = draft["people"]
    region = draft["region"]

    if draft.get("_empty"):
        ask("input", "missing", "어떤 장소를 찾고 싶은지 조건을 입력해 주세요.", blocking=True)

    # 1) 선호와 제외가 겹치면 → 제외를 우선하고 확인 질문
    for item in [x for x in _dedup(prefs + atmos + places) if x in excl]:
        wants = [m["name"] for m in members if item in m["preferences"]]
        nos = [m["name"] for m in members if item in m["exclusions"]]
        if wants and nos:
            who = f"{', '.join(wants)}님은 {_josa(item, '을를')} 원하고 {', '.join(nos)}님은 빼고 싶어 해요."
        else:
            who = f"{_josa(item, '을를')} 원한다는 말과 빼자는 말이 함께 있어요."
        ask("preferences", "conflict", f"{who} 일단 제외했는데 괜찮을까요?", ["제외 유지", "포함하기"])
    prefs = [x for x in prefs if x not in excl]
    atmos = [x for x in atmos if x not in excl]
    places = [x for x in places if x not in excl]
    course = [s for s in course if s["place_type"] not in excl]
    for s in course:
        s["preferences"] = [x for x in s["preferences"] if x not in excl]

    # 2) AI가 남긴 확인 질문
    for a in draft["ambiguities"]:
        ask(a["field"], "ambiguous", a["question"], a["options"], blocking=a["field"] == "region")

    # 3) 지역
    if draft.get("_unverified_region"):
        r = draft["_unverified_region"]
        ask("region", "unverified",
            f"AI가 '{r}' 지역을 찾았지만 입력에서 확인되지 않아요. 어느 지역에서 찾을까요?",
            draft["region_candidates"], blocking=True)
    elif region is None and not draft.get("_empty") and not any(c["field"] == "region" for c in clar):
        cands = draft["region_candidates"]
        if len(cands) >= 2:
            ask("region", "ambiguous", f"{', '.join(cands)} 중 어디로 할까요?", cands, blocking=True)
        else:
            ask("region", "missing", "어느 지역에서 찾을까요?", blocking=True)

    # 4) 인원
    speakers = [m["name"] for m in members]
    mentions = draft.get("_people_mentions", [])
    if mode == "group":
        if people is None and len(speakers) >= 2:
            people = len(speakers)
            assumptions.append({"field": "people", "value": people,
                                "reason": f"인원을 말하지 않아 대화에 참여한 {people}명으로 했어요."})
        elif people is None and not draft.get("_empty"):
            ask("people", "missing", "몇 명이 모이나요?")
        if people is not None and len(speakers) > people:
            ask("people", "ambiguous",
                f"대화에 {len(speakers)}명이 있는데 인원은 {people}명이에요. 몇 명이 맞나요?",
                [f"{people}명", f"{len(speakers)}명"])
        if len(set(mentions)) > 1:
            assumptions.append({"field": "people", "value": people,
                                "reason": f"인원이 여러 번 바뀌어서 마지막 기준 {people}명으로 했어요."})
    else:
        if people is None:
            people = DEFAULT_DATE_PEOPLE
            assumptions.append({"field": "people", "value": people, "reason": "데이트 모드 기본값 2명이에요."})
        elif people > 2:
            ask("mode", "ambiguous", f"데이트 모드인데 {people}명이에요. 단체 모임 모드로 바꿀까요?",
                ["데이트 유지", "단체 모임으로 변경"])

    # 5) 데이트 코스
    if mode == "date":
        if not course and places:
            course = [{"place_type": p, "preferences": []} for p in places]
        if not course and not draft.get("_empty"):
            course = [{"place_type": p, "preferences": []} for p in DEFAULT_DATE_COURSE]
            if prefs:
                for s in course:
                    if s["place_type"] == "식당":
                        s["preferences"] = list(prefs)
            label = " → ".join(DEFAULT_DATE_COURSE)
            assumptions.append({"field": "course", "value": list(DEFAULT_DATE_COURSE),
                                "reason": f"순서를 말하지 않아 기본 코스({label})로 했어요."})
            ask("course", "missing", f"코스 순서를 정하지 않아서 기본 코스({label})로 짰어요. 바꿀까요?",
                ["카페 → 식당", "식당 → 카페", "식당 → 술집"])
        course = [{"order": i + 1, **{k: s[k] for k in ("place_type", "preferences")}}
                  for i, s in enumerate(course)]
    else:
        course = []

    is_ready = (
        region is not None
        and not any(c["blocking"] for c in clar)
        and (mode != "date" or bool(course))
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "region": region,
        "people": people,
        "preferences": prefs,
        "exclusions": excl,
        "atmosphere": atmos,
        "place_types": places,
        "course": course,
        "members": members,
        "notes": draft.get("notes"),
        "clarifications": clar,
        "assumptions": assumptions,
        "warnings": warnings,
        "is_ready": is_ready,
        "source": source,
        "raw_text": raw_text,
    }
