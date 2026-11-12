"""Compose ordered two-stop courses from independently evaluated places.

Distances are great-circle estimates, never walking routes. Inputs are evaluated
from scratch on every call so a change or replacement cannot retain stale results.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Mapping, Sequence

from ..providers.models import Place
from .evaluation import Constraint, _check, _fact, evaluate_candidates


@dataclass(frozen=True)
class CourseLeg:
    from_place_id: str
    to_place_id: str
    straight_line_distance_m: float | None


@dataclass(frozen=True)
class CourseOption:
    places: tuple[Place, ...]
    legs: tuple[CourseLeg, ...]
    total_per_person_krw: float | None
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CourseResult:
    eligible: tuple[CourseOption, ...]
    needs_review: tuple[CourseOption, ...]
    rejected_count: int


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if isfinite(value) else None


def straight_line_distance_m(first: Place, second: Place) -> float | None:
    """Return a WGS84-coordinate great-circle distance, or None if unavailable."""
    lat1, lon1 = _number(first.latitude), _number(first.longitude)
    lat2, lon2 = _number(second.latitude), _number(second.longitude)
    if any(v is None for v in (lat1, lon1, lat2, lon2)):
        return None
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and
            -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        return None
    a = (sin(radians(lat2 - lat1) / 2) ** 2 +
         cos(radians(lat1)) * cos(radians(lat2)) *
         sin(radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_008.8 * asin(sqrt(min(1.0, max(0.0, a))))


def _price(place: Place) -> float | None:
    fact = place.attributes.get("price_per_person_krw")
    if fact is None or not fact.source:
        return None
    value = _number(fact.value)
    return value if value is not None and value >= 0 else None


def _course_preference_score(places: tuple[Place, ...], constraints: Sequence[Constraint]) -> float:
    """Average each participant's applicable preferences, then participants."""
    preferences: dict[str, list[float]] = {}
    for constraint in constraints:
        if not constraint.active or constraint.strength != "soft":
            continue
        for index, place in enumerate(places):
            if constraint.scope == "stop" and constraint.stop_index != index:
                continue
            outcome = _check(_fact(place, constraint.field), constraint.operator, constraint.value)
            preferences.setdefault(constraint.owner_id, []).append(1.0 if outcome is True else 0.0)
    return sum(sum(values) / len(values) for values in preferences.values()) / len(preferences) if preferences else 0.0


def build_courses(
    places: Sequence[Place],
    constraints: Sequence[Constraint],
    ordered_stops: Sequence[str] = ("cafe", "restaurant"),
    *,
    excluded_place_ids: Sequence[str] = (),
    party_size: int | None = None,
    max_leg_distance_m: float | None = None,
    max_total_per_person_krw: float | None = None,
    fixed_stops: Mapping[int, str] | None = None,
    limit: int = 10,
) -> CourseResult:
    """Construct two-stop courses; limits are hard constraints when provided.

    Place prices mean a confirmed *per-person* amount for each stop. Unknown
    prices and distances never satisfy limits, and are marked needs_review.
    fixed_stops maps a stop index to a selected place ID. An unavailable or
    excluded selection produces no courses, rather than silently replacing it.
    """
    ordered_stops = tuple(ordered_stops)
    if (len(ordered_stops) != 2 or any(category not in ("cafe", "restaurant", "bar") for category in ordered_stops)
            or ordered_stops[0] == ordered_stops[1]):
        raise ValueError("ordered_stops must contain two different cafe, restaurant or bar categories")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    for name, val in (("max_leg_distance_m", max_leg_distance_m),
                      ("max_total_per_person_krw", max_total_per_person_krw)):
        if val is not None and (_number(val) is None or val < 0):
            raise ValueError(f"{name} must be a finite non-negative number")
    fixed_stops = dict(fixed_stops or {})
    if any(isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= len(ordered_stops)
           or not isinstance(place_id, str) or not place_id
           for i, place_id in fixed_stops.items()):
        raise ValueError("fixed_stops must map valid stop indices to place IDs")

    pools = []
    for index, category in enumerate(ordered_stops):
        selected = [p for p in places if p.category == category and
                    (index not in fixed_stops or p.id == fixed_stops[index])]
        result = evaluate_candidates(selected, constraints,
                                     excluded_place_ids=excluded_place_ids,
                                     stop_index=index, party_size=party_size)
        pools.append([(candidate, False) for candidate in result.eligible] +
                     [(candidate, True) for candidate in result.needs_review])

    eligible, needs_review = [], []
    rejected_count = 0
    for pair in product(*pools):
        first, second = (pair[0][0].place, pair[1][0].place)
        if first.id == second.id:
            rejected_count += 1
            continue
        distance = straight_line_distance_m(first, second)
        prices = [_price(first), _price(second)]
        total = sum(prices) if all(price is not None for price in prices) else None
        reasons = []
        review = any(item[1] for item in pair)
        if review:
            reasons.append("장소의 필수 조건 확인 필요")
        if max_leg_distance_m is not None:
            if distance is None:
                review = True
                reasons.append("거리 제한 확인에 필요한 좌표 없음")
            elif distance > max_leg_distance_m:
                rejected_count += 1
                continue
        if max_total_per_person_krw is not None:
            # Non-negative verified prices can already exceed the budget even
            # if another stop's price is missing.
            if sum(price for price in prices if price is not None) > max_total_per_person_krw:
                rejected_count += 1
                continue
            if total is None:
                review = True
                reasons.append("코스 1인 예산 확인에 필요한 가격 없음")
        if not review:
            reasons.append("입력한 필수 조건을 기준으로 구성한 코스")
        course = CourseOption(
            places=(first, second),
            legs=(CourseLeg(first.id, second.id, distance),),
            total_per_person_krw=total,
            score=_course_preference_score((first, second), constraints),
            reasons=tuple(reasons),
        )
        (needs_review if review else eligible).append(course)

    def rank(course: CourseOption):
        distance = course.legs[0].straight_line_distance_m
        return (-course.score, distance is None, distance if distance is not None else 0,
                tuple(p.id for p in course.places))
    eligible.sort(key=rank)
    needs_review.sort(key=rank)
    return CourseResult(tuple(eligible[:limit]), tuple(needs_review[:limit]), rejected_count)
