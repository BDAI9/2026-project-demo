"""API 없이 돌아가는 규칙 기반 조건 추출기.

AI(OpenRouter)를 쓸 수 없을 때의 대체 수단이자, AI 결과를 검증하는 기준으로도 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Union

from .schema import empty_draft
from .vocab import (
    EXCEPT_RE,
    NEG_CUE_RE,
    OK_CUE_RE,
    PEOPLE_ABS_RES,
    PEOPLE_DELTA_MINUS_RE,
    PEOPLE_DELTA_PLUS_RE,
    SPLIT_RE,
    find_terms,
    to_int,
)


@dataclass
class Message:
    speaker: Optional[str]
    text: str


@dataclass
class Event:
    """문장에서 찾은 조건 하나."""

    key: tuple[int, int]  # (메시지 번호, 글자 위치) → 등장 순서
    speaker: Optional[str]
    canonical: str
    kind: str  # food | atmosphere | place | region
    polarity: str  # pos | neg | ok


MessageInput = Union[str, Iterable[str], Iterable[dict]]

# "민수: 매운 거 싫어" / 카카오톡 내보내기 "[민수] [오후 3:02] 매운 거 싫어"
_SPEAKER_RE = re.compile(r"^\s*([가-힣A-Za-z_][가-힣A-Za-z_ ]{0,11}?)\s*[:：]\s*(.+)$")
_KAKAO_RE = re.compile(r"^\s*\[([^\]]+)\]\s*\[[^\]]+\]\s*(.+)$")


def normalize_messages(user_input: MessageInput) -> list[Message]:
    """문자열 / 문자열 리스트 / {"speaker","text"} 리스트를 메시지 리스트로 통일한다."""
    if user_input is None:
        return []
    if isinstance(user_input, str):
        lines: list = [ln for ln in user_input.splitlines() if ln.strip()]
    else:
        lines = list(user_input)

    messages: list[Message] = []
    for item in lines:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            speaker = item.get("speaker") or item.get("name")
            if text:
                messages.append(Message(str(speaker).strip() if speaker else None, text))
            continue
        line = str(item).strip()
        if not line:
            continue
        m = _KAKAO_RE.match(line) or _SPEAKER_RE.match(line)
        if m:
            messages.append(Message(m.group(1).strip(), m.group(2).strip()))
        else:
            messages.append(Message(None, line))
    return messages


def _segments(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in SPLIT_RE.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _polarity(part: str) -> str:
    """조건 단어를 지운 나머지에서 부정/무관 표현을 찾는다."""
    cleaned = part
    for s, e, _ in reversed(find_terms(part)):
        cleaned = cleaned[:s] + " " + cleaned[e:]
    if NEG_CUE_RE.search(cleaned):
        return "neg"
    if OK_CUE_RE.search(cleaned):
        return "ok"
    return "pos"


def _analyze_part(text: str, offset: int, forced: Optional[str]) -> list[tuple[int, str, str, str]]:
    polarity = forced or _polarity(text)
    terms = find_terms(text)
    out = []
    for s, e, term in terms:
        term_polarity = term.force or polarity
        if term.kind == "region" and term_polarity == "neg":
            # A location phrase followed by a different recognized subject,
            # as in "강남에서 해산물 제외", does not itself refer to the
            # excluded item.  Without both clues retain the conservative
            # negative interpretation, e.g. "강남은 싫어" and "강남 말고".
            suffix = text[e:]
            location_phrase = re.match(r"\s*(?:역\s*)?(?:에서|근처|인근|주변|쪽)(?:에서|으로|는|에|의)?(?:\s|$)", suffix)
            other_subject = any(start >= e and other.kind != "region" for start, _, other in terms)
            if location_phrase and other_subject:
                term_polarity = "pos"
        out.append((offset + s, term.canonical, term.kind, term_polarity))
    return out


def _analyze_segment(text: str, offset: int) -> list[tuple[int, str, str, str]]:
    m = EXCEPT_RE.search(text)
    if not m:
        return _analyze_part(text, offset, None)
    left, right = text[: m.start()], text[m.end():]
    return _analyze_part(left, offset, "neg") + _analyze_segment(right, offset + m.end())


def extract_events(messages: list[Message]) -> list[Event]:
    events: list[Event] = []
    for i, msg in enumerate(messages):
        for s, e in _segments(msg.text):
            for pos, canonical, kind, pol in _analyze_segment(msg.text[s:e], s):
                events.append(Event((i, pos), msg.speaker, canonical, kind, pol))
    return events


def extract_people(messages: list[Message]) -> tuple[Optional[int], list[int]]:
    """인원 수. 나중 메시지가 앞의 값을 덮어쓰고, "한 명 더"는 더한다.

    반환: (최종 인원, 문장에 나온 절대값들)
    """
    found: list[tuple[tuple[int, int], str, int]] = []
    for i, msg in enumerate(messages):
        taken: list[tuple[int, int]] = []

        def free(s: int, e: int) -> bool:
            return all(e <= ts or s >= te for ts, te in taken)

        for regex, kind in ((PEOPLE_DELTA_PLUS_RE, "+"), (PEOPLE_DELTA_MINUS_RE, "-")):
            for m in regex.finditer(msg.text):
                taken.append(m.span())
                found.append(((i, m.start()), kind, to_int(m.group(1))))
        for regex in PEOPLE_ABS_RES:
            for m in regex.finditer(msg.text):
                if free(*m.span()):
                    taken.append(m.span())
                    found.append(((i, m.start()), "=", to_int(m.group(1))))

    found.sort()
    people: Optional[int] = None
    absolutes: list[int] = []
    for _, kind, n in found:
        if kind == "=":
            people = n
            absolutes.append(n)
        elif people is not None:
            people = people + n if kind == "+" else max(people - n, 1)
    return people, absolutes


def _dedup(items: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def build_course(events: list[Event]) -> list[dict]:
    """데이트 코스: 장소 종류를 등장 순서대로 나열. 음식만 말했으면 '식당' 단계를 만든다."""
    ordered = sorted((e for e in events if e.polarity == "pos"), key=lambda e: e.key)
    steps: list[dict] = []
    foods = [e for e in ordered if e.kind == "food"]
    for e in ordered:
        if e.kind != "place":
            continue
        if steps and steps[-1]["place_type"] == e.canonical:
            continue  # "카페 카페" 같은 연속 중복
        steps.append({"place_type": e.canonical, "preferences": []})

    if foods and not any(s["place_type"] == "식당" for s in steps):
        # 첫 음식이 나온 위치에 식당 단계를 끼워 넣는다
        first_food = foods[0].key
        places_before = sum(1 for e in ordered if e.kind == "place" and e.key < first_food)
        steps.insert(min(places_before, len(steps)), {"place_type": "식당", "preferences": []})

    for s in steps:
        if s["place_type"] == "식당":
            s["preferences"] = _dedup(f.canonical for f in foods)
            break
    return [{"order": i + 1, **s} for i, s in enumerate(steps)]


def parse_rule(messages: list[Message], mode: str) -> dict:
    """규칙 기반으로 조건 초안을 만든다."""
    draft = empty_draft()
    events = extract_events(messages)

    # Never silently restore a location explicitly rejected elsewhere in the
    # same snapshot, even if it was also mentioned as a positive candidate.
    rejected_regions = {e.canonical for e in events if e.kind == "region" and e.polarity == "neg"}
    # Retain this independently of candidates so the LLM merger can reject a
    # proposed region even when its name appears in the user's original text.
    draft["_rejected_regions"] = sorted(rejected_regions)
    regions = _dedup(e.canonical for e in sorted(events, key=lambda e: e.key)
                     if e.kind == "region" and e.polarity != "neg" and e.canonical not in rejected_regions)
    draft["region_candidates"] = regions
    draft["region"] = regions[0] if len(regions) == 1 else None

    draft["people"], draft["_people_mentions"] = extract_people(messages)

    pos = [e for e in events if e.polarity == "pos" and e.kind != "region"]
    neg = [e for e in events if e.polarity == "neg" and e.kind != "region"]
    draft["preferences"] = _dedup(e.canonical for e in pos if e.kind == "food")
    draft["atmosphere"] = _dedup(e.canonical for e in pos if e.kind == "atmosphere")
    draft["place_types"] = _dedup(e.canonical for e in pos if e.kind == "place")
    draft["exclusions"] = _dedup(e.canonical for e in neg)

    if mode == "date":
        draft["course"] = build_course(events)

    speakers = _dedup(m.speaker for m in messages if m.speaker)
    draft["members"] = [
        {
            "name": name,
            "preferences": _dedup(e.canonical for e in pos
                                  if e.speaker == name and e.kind in ("food", "atmosphere", "place")),
            "exclusions": _dedup(e.canonical for e in neg if e.speaker == name),
        }
        for name in speakers
    ]
    return draft
