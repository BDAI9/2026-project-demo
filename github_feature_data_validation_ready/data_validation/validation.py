"""Data QA core for group/date meeting recommendation MVP.

Pure Python standard library. DOES NOT call Eat.pl or Kakao APIs.
All demo data are fictional; coordinates in demo are NOT real merchant locations.
"""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

CATEGORIES = {"restaurant", "cafe", "bar"}


def _unique_strings(value, field, errors):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        errors.append(f"{field}: 문자열 배열이어야 합니다")
        return []
    return list(dict.fromkeys(x.strip() for x in value if x.strip()))


def validate_conditions(payload: dict) -> dict:
    """Validate AI-parsed request and emit a stable normalized contract."""
    errors = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["입력은 JSON 객체여야 합니다"], "normalized": None}
    mode = payload.get("mode")
    if mode not in {"group", "date"}:
        errors.append("mode: group 또는 date여야 합니다")
    region = payload.get("region")
    if not isinstance(region, str) or not region.strip():
        errors.append("region: 지역을 입력해야 합니다")
        region = ""
    else:
        region = region.strip()
    party_size = payload.get("party_size", 2 if mode == "date" else None)
    if isinstance(party_size, bool) or not isinstance(party_size, int) or not (1 <= party_size <= 30):
        errors.append("party_size: 1~30 사이의 정수여야 합니다")
    preferred_cuisines = _unique_strings(payload.get("preferred_cuisines", []), "preferred_cuisines", errors)
    excluded_terms = _unique_strings(payload.get("excluded_terms", []), "excluded_terms", errors)
    required_tags = _unique_strings(payload.get("required_tags", []), "required_tags", errors)
    category_order = _unique_strings_keep_duplicates(payload.get("category_order", []), errors)
    if mode == "date" and len(category_order) < 2:
        errors.append("date 모드는 category_order에 장소 2개 이상이 필요합니다")
    if any(c not in CATEGORIES for c in category_order):
        errors.append("category_order: restaurant/cafe/bar만 허용됩니다")
    budget = payload.get("max_budget_per_person")
    if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0):
        errors.append("max_budget_per_person: 양의 정수 또는 null이어야 합니다")
    max_leg = payload.get("max_leg_straight_km", 1.5)
    if isinstance(max_leg, bool) or not isinstance(max_leg, (int, float)) or not (0 < max_leg <= 30):
        errors.append("max_leg_straight_km: 0 초과 30 이하의 숫자여야 합니다")
    normalized = {
        "mode": mode, "region": region, "party_size": party_size,
        "preferred_cuisines": preferred_cuisines,
        "excluded_terms": excluded_terms, "required_tags": required_tags,
        "category_order": category_order, "max_budget_per_person": budget,
        "max_leg_straight_km": max_leg,
    }
    return {"ok": not errors, "errors": errors, "normalized": normalized if not errors else None}


def _unique_strings_keep_duplicates(value, errors):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        errors.append("category_order: 문자열 배열이어야 합니다")
        return []
    return [x.strip() for x in value]


def _none_if_empty(s):
    if s is None or str(s).strip() == "":
        return None
    return s


def _to_number(s, integer=False):
    s = _none_if_empty(s)
    if s is None:
        return None
    try:
        result = int(s) if integer else float(s)
    except (ValueError, TypeError):
        return "INVALID"
    return result if math.isfinite(float(result)) else "INVALID"


def _pipe(s):
    return [x.strip() for x in (s or "").split("|") if x.strip()]


def _bool(s):
    return str(s).strip().lower() in {"true", "1", "yes"}


def load_places_csv(path: str | Path) -> list[dict]:
    """Read team's agreed CSV. Blank unknowns stay None (no fabricated values)."""
    result = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            result.append({
                "place_id": row.get("place_id", "").strip(),
                "name": row.get("name", "").strip(),
                "address": row.get("address", "").strip(),
                "region": row.get("region", "").strip(),
                "category": row.get("category", "").strip(),
                "cuisine": row.get("cuisine", "").strip(),
                "price_per_person_krw": _to_number(row.get("price_per_person_krw"), integer=True),
                "capacity": _to_number(row.get("capacity"), integer=True),
                "lat_wgs84": _to_number(row.get("lat_wgs84")),
                "lon_wgs84": _to_number(row.get("lon_wgs84")),
                "coordinate_source": row.get("coordinate_source", "").strip(),
                "coordinate_verified": _bool(row.get("coordinate_verified", "false")),
                "coordinate_evidence": row.get("coordinate_evidence", "").strip(),
                "contains_terms": _pipe(row.get("contains_terms")),
                "safe_for_terms": _pipe(row.get("safe_for_terms")),
                "menu_verified": _bool(row.get("menu_verified", "false")),
                "menu_evidence": row.get("menu_evidence", "").strip(),
                "tags": _pipe(row.get("tags")),
                "tags_evidence": row.get("tags_evidence", "").strip(),
                "merchant_url": row.get("merchant_url", "").strip(),
                "all_sale_rank_pct": _to_number(row.get("all_sale_rank_pct")),
                "estimated_hours": row.get("estimated_hours", "").strip(),
                "source": row.get("source", "").strip(),
                "is_demo": _bool(row.get("is_demo", "false")),
            })
    return result


def is_trusted_eatpl_url(url: str) -> bool:
    """Never construct or guess an Eat.pl merchant link."""
    if not url:
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname == "web.paybooc.ai"
                and parts.username is None and parts.password is None
                and parts.port in (None, 443))
    except ValueError:
        return False


def validate_place(place: dict) -> dict:
    errors, warnings = [], []
    if not place.get("place_id") or not place.get("name"):
        errors.append("place_id/name 누락")
    if place.get("category") not in CATEGORIES:
        errors.append("지원하지 않는 category 또는 category 누락")
    if not place.get("region"):
        warnings.append("region 미확인: 해당 지역이라고 단정할 수 없음")
    for field in ("capacity", "price_per_person_krw"):
        value = place.get(field)
        if value == "INVALID" or (value is not None and (not isinstance(value, (int, float)) or value < 0)):
            errors.append(f"{field}: 잘못된 숫자")
    cap = place.get("capacity")
    if cap is not None and cap != "INVALID" and (not isinstance(cap, int) or cap <= 0):
        errors.append("capacity: 양의 정수만 허용")
    rank = place.get("all_sale_rank_pct")
    if rank is not None and (rank == "INVALID" or not isinstance(rank, (int, float)) or not 0 <= rank <= 100):
        errors.append("all_sale_rank_pct: 0~100 범위만 허용")
    lat, lon = place.get("lat_wgs84"), place.get("lon_wgs84")
    if (lat is None) != (lon is None):
        errors.append("위도·경도는 둘 다 있거나 둘 다 없어야 함")
    if lat == "INVALID" or lon == "INVALID":
        errors.append("좌표값이 숫자가 아님")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            errors.append("WGS84 좌표 범위 오류 (TM128을 위경도로 사용할 수 없음)")
        if not (33 <= lat <= 39 and 124 <= lon <= 132):
            warnings.append("대한민국 좌표 범위를 벗어난 값: 재확인 필요")
    if place.get("coordinate_verified") and (
        place.get("coordinate_source") not in {"kakao_local", "manual_map_check"}
        or not place.get("coordinate_evidence") or lat is None or lon is None
    ):
        errors.append("coordinate_verified=true라면 검증된 출처·근거·WGS84 좌표가 필요")
    if place.get("menu_verified") and not place.get("menu_evidence"):
        errors.append("menu_verified=true라면 확인 근거(menu_evidence)가 필요")
    if place.get("source") == "eatpl" and not is_trusted_eatpl_url(place.get("merchant_url", "")):
        warnings.append("잇플 상세 링크 미검증: 공식 상세 링크로 노출하지 말 것")
    if place.get("is_demo"):
        warnings.append("가상 데이터: 실존 매장/실제 거리/영업 여부가 아님")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def evaluate_candidate(place: dict, conditions: dict) -> dict:
    """Pass / reject / needs_verification; unknowns are NEVER converted to safe."""
    if not validate_place(place)["valid"]:
        return {"status": "reject", "reasons": ["장소 데이터 자체가 유효하지 않음"]}
    rejected, unknown = [], []
    region = place.get("region")
    if not region:
        unknown.append("실제 지역 미확인")
    elif conditions["region"] not in region and region not in conditions["region"]:
        rejected.append("요청 지역 불일치")
    if conditions["mode"] == "group" and place["category"] != "restaurant":
        rejected.append("단체 모임 MVP는 식당만 추천")
    if conditions["mode"] == "date" and place["category"] not in conditions["category_order"]:
        rejected.append("요청한 코스 업종에 포함되지 않음")
    if conditions["preferred_cuisines"]:
        cuisine = place.get("cuisine")
        if not cuisine:
            unknown.append("음식 종류 미확인")
        elif cuisine not in conditions["preferred_cuisines"]:
            rejected.append("선호 음식 종류 불일치")
    capacity = place.get("capacity")
    if capacity is None:
        unknown.append("수용 가능 인원 미확인")
    elif capacity < conditions["party_size"]:
        rejected.append("인원 수용 불가")
    budget = conditions.get("max_budget_per_person")
    if budget is not None:
        price = place.get("price_per_person_krw")
        if price is None:
            unknown.append("1인당 예상 금액 미확인")
        elif price > budget:
            rejected.append("1인당 예산 초과")
    for term in conditions["excluded_terms"]:
        if term in place.get("contains_terms", []):
            rejected.append(f"제외 조건 포함: {term}")
        elif not (place.get("menu_verified") and place.get("menu_evidence") and term in place.get("safe_for_terms", [])):
            unknown.append(f"제외 조건 '{term}' 충족 여부 미확인")
    for tag in conditions["required_tags"]:
        if tag not in place.get("tags", []) or not place.get("tags_evidence"):
            unknown.append(f"분위기/편의 조건 '{tag}' 미확인")
    status = "reject" if rejected else "needs_verification" if unknown else "pass"
    return {"status": status, "reasons": rejected + unknown, "is_demo": bool(place.get("is_demo"))}


def filter_places(places: list[dict], conditions: dict) -> dict:
    """Returns auditable groupings, no hidden recommendation ranking."""
    result = {"pass": [], "needs_verification": [], "reject": []}
    for p in places:
        decision = evaluate_candidate(p, conditions)
        result[decision["status"]].append({"place_id": p["place_id"], "name": p["name"], **decision})
    return result


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line geographic distance, NOT walking route distance."""
    r = 6371.0088
    a1, a2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = a2 - a1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def validate_course(place_ids: list[str], places_by_id: dict, conditions: dict, *, allow_demo_coordinates=False) -> dict:
    """QA of Backend #3's proposed course, not its route optimization algorithm."""
    failures, unknown, legs = [], [], []
    if conditions["mode"] != "date":
        return {"status": "fail", "failures": ["date 모드에서만 코스를 검사합니다"], "unknown": [], "legs": []}
    if len(place_ids) != len(conditions["category_order"]):
        failures.append("코스 길이와 category_order의 길이가 다름")
    if len(set(place_ids)) != len(place_ids):
        failures.append("동일 장소 중복 방문")
    places = []
    for idx, pid in enumerate(place_ids):
        p = places_by_id.get(pid)
        if not p:
            failures.append(f"없는 장소 ID: {pid}")
            continue
        places.append(p)
        if idx < len(conditions["category_order"]) and p["category"] != conditions["category_order"][idx]:
            failures.append(f"{idx + 1}번째 장소 업종 순서 불일치")
        result = evaluate_candidate(p, conditions)
        if result["status"] == "reject":
            failures.append(f"{pid}: " + "; ".join(result["reasons"]))
        elif result["status"] == "needs_verification":
            unknown.append(f"{pid}: " + "; ".join(result["reasons"]))
    if len(places) == len(place_ids):
        for first, second in zip(places, places[1:]):
            if not (first.get("lat_wgs84") is not None and second.get("lat_wgs84") is not None
                    and first.get("lon_wgs84") is not None and second.get("lon_wgs84") is not None):
                unknown.append(f"{first['place_id']} → {second['place_id']}: 위경도 미확인")
                continue
            if not all(validate_place(p)["valid"] for p in (first, second)):
                failures.append("좌표 또는 장소 데이터 형식 오류")
                continue
            if not allow_demo_coordinates and not all(p.get("coordinate_verified") for p in (first, second)):
                unknown.append(f"{first['place_id']} → {second['place_id']}: 지도 좌표 검증 전")
                continue
            d = haversine_km(first["lat_wgs84"], first["lon_wgs84"], second["lat_wgs84"], second["lon_wgs84"])
            legs.append({"from": first["place_id"], "to": second["place_id"],
                         "straight_line_km": round(d, 3), "distance_type": "straight_line_not_walking"})
            if d > conditions["max_leg_straight_km"]:
                failures.append(f"{first['place_id']} → {second['place_id']}: 직선거리 {d:.2f}km 초과")
    status = "fail" if failures else "needs_verification" if unknown else "pass"
    return {"status": status, "failures": failures, "unknown": unknown, "legs": legs,
            "distance_note": "직선거리일 뿐, 실제 도보거리/소요시간이 아닙니다", "demo_mode": allow_demo_coordinates}


def quality_report(places: list[dict]) -> dict:
    seen_ids, seen_names, duplicates, invalid = set(), set(), [], []
    missing = {"coordinates": 0, "capacity": 0, "price": 0, "menu_evidence": 0, "merchant_url": 0}
    for p in places:
        if p.get("place_id") in seen_ids:
            duplicates.append(f"ID 중복: {p.get('place_id')}")
        seen_ids.add(p.get("place_id"))
        name_key = (p.get("name"), p.get("address"))
        if name_key in seen_names:
            duplicates.append(f"동일 상호·주소 중복: {p.get('name')}")
        seen_names.add(name_key)
        errors = validate_place(p)["errors"]
        if errors:
            invalid.append({"place_id": p.get("place_id"), "errors": errors})
        missing["coordinates"] += not p.get("coordinate_verified")
        missing["capacity"] += p.get("capacity") is None
        missing["price"] += p.get("price_per_person_krw") is None
        missing["menu_evidence"] += not (p.get("menu_verified") and p.get("menu_evidence"))
        missing["merchant_url"] += not is_trusted_eatpl_url(p.get("merchant_url", ""))
    return {"total": len(places), "invalid_records": invalid,
            "potential_duplicates": duplicates, "missing_or_unverified_counts": missing,
            "note": "가상 샘플과 실제 수집 데이터의 품질 수치는 구분하여 사용하세요"}
