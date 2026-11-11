"""Conservative adapter to the team's proposed validation Place dictionary.

The team contract is provisional; this does not call its validation module or
establish that an externally sourced field is correct. Coordinate, menu and
tag verification require evidence not currently represented in Place.
"""
from __future__ import annotations

from math import isfinite
import re

from .eatpl import _safe_detail_url
from .models import Fact, Place


def _value(place: Place, field: str):
    fact = place.attributes.get(field)
    return fact.value if isinstance(fact, Fact) and isinstance(fact.source, str) and fact.source.strip() else None


def _number(value, *, minimum=0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not isfinite(value) or value < minimum or (maximum is not None and value > maximum):
            return None
    except OverflowError:
        return None
    return value


def _hours(start, end):
    def hhmm(value):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}", value):
            return None
        hour, minute = int(value[:2]), int(value[2:])
        return (hour, minute) if hour < 24 and minute < 60 else None

    start_time, end_time = hhmm(start), hhmm(end)
    if start_time is None or end_time is None:
        return ""
    suffix = "익일 " if end_time < start_time else ""
    return f"예상 {start_time[0]:02}:{start_time[1]:02}–{suffix}{end_time[0]:02}:{end_time[1]:02} (공식 영업시간 아님)"


def to_team_place(place: Place, *, region_hint: str | None = None) -> dict:
    """Return a team-format dict without inventing verification evidence.

    The input source must be explicitly classified. A region hint is accepted
    only when it appears literally in the venue's supplied address. Coordinates
    are omitted until their source and match evidence have a shared contract.
    """
    if place.source not in ("eatpl", "mock", "demo"):
        raise ValueError("unsupported place source")
    is_demo = place.source in ("mock", "demo")
    address = place.address if isinstance(place.address, str) else ""
    if region_hint is not None and not isinstance(region_hint, str):
        raise ValueError("region_hint must be a string or None")
    supplied_region = _value(place, "region")
    region = supplied_region.strip() if isinstance(supplied_region, str) else ""
    if not region or region not in address:
        hint = region_hint.strip() if region_hint else ""
        region = hint if hint and hint in address else ""
    capacity = _value(place, "capacity")
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        capacity = None
    category = place.category if place.category in ("cafe", "restaurant", "bar") else ""
    business_type = _value(place, "business_type")
    if not isinstance(business_type, str):
        business_type = ""
    return {
        "place_id": place.id,
        "name": place.name,
        "address": address,
        "region": region,
        "category": category,
        "cuisine": "",
        "price_per_person_krw": _number(_value(place, "price_per_person_krw")),
        "capacity": capacity,
        "lat_wgs84": None,
        "lon_wgs84": None,
        "coordinate_source": "",
        "coordinate_verified": False,
        "coordinate_evidence": "",
        "contains_terms": [],
        "safe_for_terms": [],
        "menu_verified": False,
        "menu_evidence": "",
        "tags": [],
        "tags_evidence": "",
        "merchant_url": (_safe_detail_url(place.eatpl_url) or "") if not is_demo else "",
        "all_sale_rank_pct": _number(_value(place, "national_sales_percentile"), maximum=100),
        "estimated_hours": _hours(_value(place, "estimated_open_time"), _value(place, "estimated_close_time")),
        "source": "demo" if is_demo else "eatpl",
        "is_demo": is_demo,
        "_extra": {
            "ccg_sale_rank_pct": _number(_value(place, "regional_sales_percentile"), maximum=100),
            "raw_kind": business_type,
        },
    }
