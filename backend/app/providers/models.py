"""Internal place model; unknown information is represented explicitly."""

from dataclasses import dataclass, field
from typing import Any
from math import isfinite


@dataclass(frozen=True)
class Fact:
    value: Any
    source: str
    # Only a complete list supports the assertion that an item is absent.
    complete: bool = False


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    category: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    attributes: dict[str, Fact] = field(default_factory=dict)
    eatpl_url: str | None = None
    source: str = "mock"

    def __post_init__(self):
        for value, maximum in ((self.latitude, 90), (self.longitude, 180)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or abs(value) > maximum):
                raise ValueError("Coordinates must be valid WGS84 degrees or None")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Coordinates must be supplied as a pair")
