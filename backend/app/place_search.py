"""Fetch baseline places and evaluate one set of participants' conditions.

The caller retains the result's baseline_places and can reevaluate it whenever
the room's constraints or exclusions change. This module does not own room
membership, persistence, event delivery, or asynchronous revision handling.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from backend.app.providers.models import Place
from backend.app.recommendations.evaluation import Constraint
from backend.app.recommendations.group import (
    CandidateExclusion,
    GroupCandidateResult,
    evaluate_group_candidates,
)


class PlaceProvider(Protocol):
    def search(self, *, trace_number: str, location: str | None = None,
               business_type: str | None = None,
               merchant_name: str | None = None) -> list[Place]: ...


@dataclass(frozen=True)
class PlaceSearchResult:
    baseline_places: tuple[Place, ...]
    candidates: GroupCandidateResult
    source: str
    truncated: bool


def search_group_places(*, region: str, constraints: Iterable[Constraint],
                        exclusions: Iterable[CandidateExclusion] = (),
                        party_size: int | None = None,
                        business_type: str | None = None,
                        merchant_name: str | None = None,
                        provider: PlaceProvider, trace_number: str) -> PlaceSearchResult:
    """Search official-provider results; do not replace failures with samples.

    ``truncated`` flags a potential 100-record cap, not a guarantee that fewer
    results are exhaustive. The region is an address substring, not a radius.
    ``source`` reflects place provenance; empty official results remain eatpl.
    Any provider exception is deliberately propagated to the caller.
    """
    if not isinstance(region, str) or not region.strip():
        raise ValueError("region is required")
    if party_size is not None and (isinstance(party_size, bool) or not isinstance(party_size, int) or party_size < 1):
        raise ValueError("party_size must be a positive integer")
    for name, value in (("business_type", business_type), ("merchant_name", merchant_name)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{name} must be a nonempty string or None")
    if not isinstance(trace_number, str) or not trace_number.strip():
        raise ValueError("trace_number is required")

    baseline = tuple(provider.search(trace_number=trace_number, location=region.strip(),
                                     business_type=business_type, merchant_name=merchant_name))
    sources = {place.source for place in baseline}
    source = next(iter(sources)) if len(sources) == 1 else ("mixed" if sources else getattr(provider, "source", "unknown"))
    result = evaluate_group_candidates(baseline, constraints, exclusions, party_size=party_size)
    return PlaceSearchResult(baseline_places=baseline, candidates=result, source=source,
                             truncated=len(baseline) >= 100)
