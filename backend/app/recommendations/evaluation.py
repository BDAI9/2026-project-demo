"""Deterministic three-valued candidate evaluation, independent of storage."""

from dataclasses import dataclass
from typing import Any, Iterable
from math import isfinite
from backend.app.providers.models import Fact, Place


@dataclass(frozen=True)
class Constraint:
    id: str
    owner_id: str
    field: str
    operator: str
    value: Any
    strength: str = "hard"
    scope: str = "room"
    stop_index: int | None = None
    active: bool = True

    def __post_init__(self):
        if self.strength not in ("hard", "soft") or self.scope not in ("room", "stop"):
            raise ValueError("Invalid constraint strength or scope")
        if self.scope == "stop" and (not isinstance(self.stop_index, int) or self.stop_index < 0):
            raise ValueError("Stop constraints need a nonnegative stop_index")
        if self.operator not in ("eq", "neq", "lte", "gte", "contains", "excludes"):
            raise ValueError("Unsupported operator")


@dataclass(frozen=True)
class Candidate:
    place: Place
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CandidateResult:
    eligible: tuple[Candidate, ...]
    needs_review: tuple[Candidate, ...]
    excluded: tuple[Candidate, ...]


def _fact(place: Place, field: str) -> Fact | None:
    if field in ("name", "category", "address"):
        value = getattr(place, field)
        if field == "category" and value == "unknown":
            return None
        return Fact(value, place.source, True) if value is not None else None
    return place.attributes.get(field)


def _check(fact: Fact | None, op: str, wanted: Any) -> bool | None:
    if fact is None or not fact.source or fact.value is None or wanted is None:
        return None
    actual = fact.value
    try:
        if op in ("eq", "neq"):
            # A collection is not a scalar: comparing it to a single ingredient
            # using != would falsely prove an exclusion even when it contains it.
            # Use contains/excludes for list membership and completeness checks.
            if isinstance(actual, bool) or isinstance(wanted, bool):
                if not isinstance(actual, bool) or not isinstance(wanted, bool): return None
            elif isinstance(actual, (int, float)) and isinstance(wanted, (int, float)):
                if not isfinite(actual) or not isfinite(wanted): return None
            elif not (isinstance(actual, str) and isinstance(wanted, str)):
                return None
            return actual == wanted if op == "eq" else actual != wanted
        if op in ("lte", "gte"):
            if isinstance(actual, bool) or isinstance(wanted, bool) or not isinstance(actual, (int, float)) or not isinstance(wanted, (int, float)) or not isfinite(actual) or not isfinite(wanted): return None
            return actual <= wanted if op == "lte" else actual >= wanted
        if not isinstance(actual, (list, tuple, set, frozenset, str)): return None
        found = wanted in actual
        if op == "contains": return True if found else (False if fact.complete else None)
        if op == "excludes": return False if found else (True if fact.complete else None)
    except (TypeError, ValueError, OverflowError):
        return None
    return None


def evaluate_candidates(places: Iterable[Place], constraints: Iterable[Constraint], excluded_place_ids: Iterable[str] = (), stop_index: int | None = None, party_size: int | None = None) -> CandidateResult:
    """Reevaluate the entire supplied baseline on every call; never mutate it."""
    if party_size is not None and (isinstance(party_size, bool) or not isinstance(party_size, int) or party_size < 1):
        raise ValueError("party_size must be a positive integer")
    rules = [c for c in constraints if c.active and (c.scope == "room" or (stop_index is not None and c.stop_index == stop_index))]
    direct = set(excluded_place_ids)
    buckets: dict[str, list[Candidate]] = {"eligible": [], "needs_review": [], "excluded": []}
    for place in places:
        failed, unknown, preferences = [], [], {}
        if place.id in direct:
            failed.append("참가자가 직접 제외")
        if party_size is not None:
            capacity = _check(_fact(place, "capacity"), "gte", party_size)
            if capacity is False: failed.append("수용 인원 부족")
            if capacity is None: unknown.append("수용 인원 확인 필요")
        for rule in rules:
            outcome = _check(_fact(place, rule.field), rule.operator, rule.value)
            if rule.strength == "hard":
                if outcome is False: failed.append(f"조건 불충족: {rule.id}")
                if outcome is None: unknown.append(f"조건 확인 필요: {rule.id}")
            else:
                preferences.setdefault(rule.owner_id, []).append(1.0 if outcome is True else 0.0)
        # Equal weight per participant, irrespective of their number of preferences.
        score = sum(sum(v) / len(v) for v in preferences.values()) / len(preferences) if preferences else 0.0
        status = "excluded" if failed else "needs_review" if unknown else "eligible"
        buckets[status].append(Candidate(place, score, tuple(failed + unknown)))
    for bucket in buckets.values(): bucket.sort(key=lambda c: (-c.score, c.place.id))
    return CandidateResult(*(tuple(buckets[k]) for k in ("eligible", "needs_review", "excluded")))
