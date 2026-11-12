"""조건 해석 결과의 공통 형식.

프론트엔드(입력 화면)와 잇플 연결·코스 담당이 모두 이 형식을 기준으로 주고받는다.
모든 값은 JSON으로 그대로 바꿀 수 있는 기본 타입(str, int, list, dict, None)만 쓴다.
"""

from __future__ import annotations

from typing import Literal, Optional, TypedDict

SCHEMA_VERSION = "1.0"

Mode = Literal["group", "date"]

MODE_ALIASES = {
    "group": "group",
    "단체": "group",
    "단체모임": "group",
    "단체 모임": "group",
    "모임": "group",
    "date": "date",
    "데이트": "date",
    "소개팅": "date",
    "데이트·소개팅": "date",
    "데이트/소개팅": "date",
}

MODE_LABELS = {"group": "단체 모임", "date": "데이트·소개팅"}

# 데이트 모드에서 순서를 말하지 않았을 때 쓰는 기본 코스 (MVP: 카페 + 식당)
DEFAULT_DATE_COURSE = ["카페", "식당"]
DEFAULT_DATE_PEOPLE = 2


class CourseStep(TypedDict):
    order: int  # 1부터 시작
    place_type: str  # 카페, 식당, 술집, 디저트 ...
    preferences: list[str]  # 이 단계에만 해당하는 선호 (예: 식당 → ["파스타"])


class Member(TypedDict):
    name: str
    preferences: list[str]
    exclusions: list[str]


class Clarification(TypedDict):
    field: str  # region | people | preferences | course | mode ...
    type: str  # missing | ambiguous | conflict | unverified
    question: str  # 사용자에게 그대로 보여줄 수 있는 질문
    options: list[str]  # 선택지 버튼으로 쓸 수 있는 값 (없으면 [])
    blocking: bool  # True면 이 질문이 풀리기 전에는 장소 검색을 하지 않는다


class Assumption(TypedDict):
    field: str
    value: object
    reason: str


class ConditionResult(TypedDict):
    schema_version: str
    mode: Mode
    region: Optional[str]
    people: Optional[int]
    preferences: list[str]  # 원하는 음식 종류 등
    exclusions: list[str]  # 빼야 하는 음식·분위기·장소 종류 (알레르기 포함)
    atmosphere: list[str]  # 원하는 분위기 (조용한, 가성비 ...)
    place_types: list[str]  # 원하는 장소 종류 (순서 없음)
    course: list[CourseStep]  # 데이트 모드 전용, 순서 있음. 단체 모임은 []
    members: list[Member]  # 단톡 입력일 때 사람별 조건
    notes: Optional[str]  # 형식에 안 들어가는 기타 요청 (AI 해석 때만 채워짐)
    clarifications: list[Clarification]
    assumptions: list[Assumption]  # 사용자가 말하지 않아 기본값으로 채운 항목
    warnings: list[str]  # API 오류 등 개발자·사용자에게 알릴 내용
    is_ready: bool  # True면 바로 잇플 검색에 넘겨도 된다
    source: str  # "rule" | "llm"
    raw_text: str


def normalize_mode(mode: str) -> Mode:
    key = (mode or "").strip().lower()
    if key in MODE_ALIASES:
        return MODE_ALIASES[key]  # type: ignore[return-value]
    raise ValueError(f"알 수 없는 모드예요: {mode!r} (group 또는 date)")


def empty_draft() -> dict:
    """해석 중간 단계에서 쓰는 빈 초안."""
    return {
        "region": None,
        "region_candidates": [],
        "people": None,
        "preferences": [],
        "exclusions": [],
        "atmosphere": [],
        "place_types": [],
        "course": [],
        "members": [],
        "notes": None,
        "ambiguities": [],
    }
