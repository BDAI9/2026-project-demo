"""Stateless group-place evaluation for integration with the room service.

The room server owns authorization, persistence and revision handling.  This
module evaluates a supplied snapshot against the full baseline and does not
update conditions, exclusions, or places.
"""

from dataclasses import dataclass
from typing import Iterable

from backend.app.providers.models import Place
from backend.app.recommendations.evaluation import Constraint, evaluate_candidates


@dataclass(frozen=True)
class CandidateExclusion:
    place_id: str
    participant_id: str
    reason: str | None = None
    active: bool = True

    def __post_init__(self):
        if not isinstance(self.place_id, str) or not self.place_id.strip():
            raise ValueError("place_id must be a nonempty string")
        if not isinstance(self.participant_id, str) or not self.participant_id.strip():
            raise ValueError("participant_id must be a nonempty string")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValueError("reason must be a string or None")
        if not isinstance(self.active, bool):
            raise ValueError("active must be a boolean")


@dataclass(frozen=True)
class GroupCandidate:
    place: Place
    score: float
    reasons: tuple[str, ...]
    direct_exclusions: tuple[CandidateExclusion, ...]


@dataclass(frozen=True)
class GroupCandidateResult:
    eligible: tuple[GroupCandidate, ...]
    needs_review: tuple[GroupCandidate, ...]
    excluded: tuple[GroupCandidate, ...]


def evaluate_group_candidates(
    baseline_places: Iterable[Place],
    constraints: Iterable[Constraint],
    exclusions: Iterable[CandidateExclusion] = (),
    *,
    party_size: int | None = None,
) -> GroupCandidateResult:
    """Evaluate the entire baseline against one current group snapshot.

    `exclusions` contains the current record for each (place, participant),
    including inactive records if desired.  Duplicate records are rejected so
    the function cannot guess which version is current.  An active exclusion
    by any participant excludes the place until every participant's record is
    inactive or removed.  A previously excluded place is reevaluated normally
    when conditions or exclusions are removed.

    Conditions scoped to a course stop cannot be applied to a single-place
    group result; active ones are rejected rather than silently discarded.
    """
    current_constraints = tuple(constraints)
    if any(rule.active and rule.scope != "room" for rule in current_constraints):
        raise ValueError("group candidates require room-scoped active conditions")

    by_place: dict[str, list[CandidateExclusion]] = {}
    seen: set[tuple[str, str]] = set()
    for exclusion in exclusions:
        if not isinstance(exclusion, CandidateExclusion):
            raise ValueError("exclusions must contain CandidateExclusion records")
        identity = (exclusion.place_id, exclusion.participant_id)
        if identity in seen:
            raise ValueError("duplicate exclusion record for place and participant")
        seen.add(identity)
        if exclusion.active:
            by_place.setdefault(exclusion.place_id, []).append(exclusion)

    result = evaluate_candidates(
        baseline_places, current_constraints,
        excluded_place_ids=by_place.keys(), party_size=party_size,
    )

    def convert(candidates):
        return tuple(GroupCandidate(c.place, c.score, c.reasons,
                                    tuple(by_place.get(c.place.id, ())))
                     for c in candidates)

    return GroupCandidateResult(convert(result.eligible), convert(result.needs_review),
                                convert(result.excluded))
