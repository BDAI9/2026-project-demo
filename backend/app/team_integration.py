"""Explicitly confirmed, local-only bridge for the team's separate modules.

There is no shared room, participant authentication, or automatic confirmation.
The rule parser is a proposal; the client must show the original text and let
the user edit every field before it sends a confirmed recommendation request.
"""
from __future__ import annotations

import math
from pathlib import Path

from condition_ai import parse_conditions
from backend import skill_probe
from backend.app.providers.models import Place
from backend.app.providers.team_contract import to_team_place
from backend.app.recommendations.courses import build_courses
from github_feature_data_validation_ready.data_validation import validation


_SAMPLES = (Path(__file__).resolve().parents[2] / "github_feature_data_validation_ready"
            / "data_validation" / "data" / "sample_places_v2_30.csv")
_MAX_QUERY = 2000


def _object(payload, allowed, required):
    if not isinstance(payload, dict) or set(payload) - allowed or not required <= payload.keys():
        raise ValueError("요청 형식과 필수 입력 항목을 확인해 주세요.")


def interpret(payload: object) -> dict:
    _object(payload, {"text", "product_mode"}, {"text", "product_mode"})
    text, mode = payload["text"], payload["product_mode"]
    if not isinstance(text, str) or not text.strip() or len(text) > _MAX_QUERY:
        raise ValueError("조건 문장을 입력해 주세요. (2,000자 이내)")
    if mode not in ("group", "date"):
        raise ValueError("단체 또는 데이트 모드를 선택해 주세요.")
    proposal = parse_conditions(text, mode, use_llm=False)
    return {"status": "ok", "proposal": proposal,
            "message": "해석이 일부 누락될 수 있습니다. 원문과 각 조건을 확인하고 빠진 내용을 직접 입력해 주세요."}


def _string_list(value, name):
    if not isinstance(value, list) or len(value) > 50:
        raise ValueError(f"{name}: 문자열 목록을 확인해 주세요.")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 100:
            raise ValueError(f"{name}: 빈 값 없이 100자 이내로 입력해 주세요.")
        text = item.strip()
        if text not in result:
            result.append(text)
    return result


def _request(payload):
    allowed = {"product_mode", "source", "region", "party_size", "excluded_terms", "preferred_cuisines",
               "required_tags", "category_order", "max_budget_per_person", "max_leg_distance_m", "confirmed"}
    _object(payload, allowed, {"product_mode", "source", "region", "party_size", "confirmed"})
    mode, source = payload["product_mode"], payload["source"]
    if mode not in ("group", "date") or source not in ("sample", "skill-test"):
        raise ValueError("모드와 데이터 종류를 확인해 주세요.")
    if payload["confirmed"] is not True:
        raise ValueError("원문과 조건을 확인한 뒤 검색해 주세요.")
    region = payload["region"]
    if not isinstance(region, str) or not region.strip() or len(region) > 120:
        raise ValueError("지역을 입력해 주세요. (120자 이내)")
    region = region.strip()
    party = payload["party_size"]
    if isinstance(party, bool) or not isinstance(party, int) or not 1 <= party <= 30:
        raise ValueError("모임 인원은 1~30명으로 입력해 주세요.")
    excluded = _string_list(payload.get("excluded_terms", []), "제외 조건")
    preferred = _string_list(payload.get("preferred_cuisines", []), "선호 음식")
    tags = _string_list(payload.get("required_tags", []), "필수 분위기")
    order = payload.get("category_order", [])
    if (not isinstance(order, list) or (mode == "group" and order != []) or
            (mode == "date" and (len(order) != 2 or
                                 any(item not in ("cafe", "restaurant", "bar") for item in order) or
                                 order[0] == order[1]))):
        raise ValueError("데이트는 식당·카페·술집 중 서로 다른 두 곳의 순서를 선택해 주세요.")
    budget = payload.get("max_budget_per_person")
    if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 1_000_000_000):
        raise ValueError("한 장소의 1인 예산은 양의 정수여야 합니다.")
    distance = payload.get("max_leg_distance_m")
    if distance is not None and (isinstance(distance, bool) or not isinstance(distance, (int, float)) or not 0 < distance <= 30_000 or not math.isfinite(distance)):
        raise ValueError("장소 간 최대 직선거리는 0 초과 30,000m 이하여야 합니다.")
    if mode == "group" and distance is not None:
        raise ValueError("장소 간 거리 제한은 데이트 모드에서만 적용할 수 있습니다.")
    # The team's validator defaults to 1.5km and treats food preferences as
    # hard exclusions. Supply no preference filter and neutralize the default
    # after validation whenever the user did not request a distance limit.
    team_payload = {"mode": mode, "region": region, "party_size": party,
                    "excluded_terms": excluded, "preferred_cuisines": [], "required_tags": tags,
                    "category_order": order, "max_budget_per_person": budget,
                    "max_leg_straight_km": distance / 1000 if distance is not None else 30}
    checked = validation.validate_conditions(team_payload)
    if not checked["ok"]:
        raise ValueError("조건 검증에 실패했습니다: " + "; ".join(checked["errors"]))
    conditions = checked["normalized"]
    if distance is None:
        conditions["max_leg_straight_km"] = math.inf
    return {"mode": mode, "source": source, "region": region, "party": party,
            "preferred": preferred, "order": order, "distance": distance, "conditions": conditions}


def _candidate_payload(place, status, reasons):
    return {"id": place["place_id"], "name": place["name"], "address": place.get("address") or None,
            "category": place.get("category") or "unknown", "price_per_person_krw": place.get("price_per_person_krw"),
            "eatpl_url": None if place.get("is_demo") else place.get("merchant_url") or None,
            "status": status, "reasons": list(reasons)}


def recommend(payload: object) -> dict:
    request = _request(payload)
    source = request["source"]
    output = {"status": "error", "source": source, "message": "", "candidates": [], "courses": [],
              "truncated": False, "cache_hit": None}
    if source == "sample":
        try:
            places = validation.load_places_csv(_SAMPLES)
        except (OSError, ValueError):
            output["message"] = "샘플 장소를 읽지 못했습니다."
            return output
    else:
        try:
            external, cache_hit = skill_probe.fetch_places(request["region"])
            # The upstream skill may itself limit its response to 100 results;
            # indicate that this can be incomplete and cap work locally too.
            output["truncated"] = len(external) >= 100
            places = [to_team_place(place, region_hint=request["region"]) for place in external[:100]]
        except Exception:
            # External failures and malformed upstream records are shown as
            # errors, never converted into a fictional success or empty list.
            output["message"] = "잇플 스킬 조회에 실패했습니다. 잠시 후 다시 시도해 주세요."
            return output
        output["cache_hit"] = cache_hit

    if any(not p.get("place_id") for p in places) or len({p["place_id"] for p in places}) != len(places):
        output["message"] = "조회된 장소의 식별 정보를 확인할 수 없습니다."
        return output

    # Unknown category is information missing, not proof of exclusion. Evaluate
    # other constraints with a provisional requested category and then retain
    # 'needs_verification'; such items are never used to construct courses.
    evaluable = []
    unknown_ids = set()
    for place in places:
        if place.get("category") not in validation.CATEGORIES:
            candidate = dict(place)
            candidate["category"] = "restaurant" if request["mode"] == "group" else request["order"][0]
            unknown_ids.add(place["place_id"])
            evaluable.append(candidate)
        else:
            evaluable.append(place)
    classified = validation.filter_places(evaluable, request["conditions"])
    by_id = {p["place_id"]: p for p in places}
    verdicts = {}
    for status in ("pass", "needs_verification", "reject"):
        for result in classified[status]:
            place_id = result["place_id"]
            reasons = list(result["reasons"])
            if place_id in unknown_ids and status != "reject":
                verdicts[place_id] = ("needs_verification", reasons + ["업종 확인 필요"])
            else:
                verdicts[place_id] = (status, reasons)
    # Stable within a status; a confirmed matching cuisine boosts ranking only.
    status_order = {"pass": 0, "needs_verification": 1, "reject": 2}
    preferred = set(request["preferred"])
    ranked = sorted(places, key=lambda p: (status_order[verdicts[p["place_id"]][0]],
                                            -(p.get("cuisine") in preferred), p["place_id"]))
    output["candidates"] = [_candidate_payload(p, *verdicts[p["place_id"]]) for p in ranked]

    if request["mode"] == "date":
        # Use the course composer's verified-coordinate calculation, then the
        # team's validation logic for each candidate pair. Sample coordinates
        # are illustrative; never enable them for actual Eatpl data.
        selected = [p for p in places if verdicts[p["place_id"]][0] != "reject" and p["place_id"] not in unknown_ids]
        course_places = [Place(id=p["place_id"], name=p["name"], category=p["category"],
                               address=p.get("address") or None, latitude=p.get("lat_wgs84"),
                               longitude=p.get("lon_wgs84"), eatpl_url=None if source == "sample" else p.get("merchant_url") or None,
                               source="mock" if source == "sample" else "eatpl") for p in selected]
        composed = build_courses(course_places, [], request["order"], max_leg_distance_m=request["distance"], limit=10_000)
        options = []
        for course in (*composed.eligible, *composed.needs_review):
            ids = [p.id for p in course.places]
            check = validation.validate_course(ids, by_id, request["conditions"], allow_demo_coordinates=(source == "sample"))
            if check["status"] == "fail":
                continue
            legs = course.legs
            distance = legs[0].straight_line_distance_m if legs else None
            reasons = list(check["unknown"]) + list(course.reasons if check["status"] == "needs_verification" else ())
            details = [{"id": p.id, "name": p.name, "address": p.address, "eatpl_url": p.eatpl_url} for p in course.places]
            matches = sum(1 for pid in ids if by_id[pid].get("cuisine") in preferred)
            options.append((matches, {"places": details, "status": check["status"],
                                     "distance_m": distance, "reasons": reasons}))
        options.sort(key=lambda item: (item[1]["status"] != "pass", -item[0],
                                       item[1]["distance_m"] is None,
                                       item[1]["distance_m"] if item[1]["distance_m"] is not None else 0,
                                       tuple(p["id"] for p in item[1]["places"])))
        output["courses"] = [item[1] for item in options[:10]]

    has_results = bool(output["courses"]) if request["mode"] == "date" else any(
        c["status"] != "reject" for c in output["candidates"])
    if has_results:
        output.update(status="ok", message="조회한 장소를 평가했습니다. 정보가 없는 조건은 확인이 필요합니다.")
    else:
        output.update(status="empty", message="조회한 후보 중 조건에 맞는 장소가 없습니다. 지역이나 조건을 확인해 주세요.")
    if preferred:
        output["message"] += " 확인된 음식 종류가 선호와 일치하면 같은 판정 안에서 우선 표시합니다."
    if source == "sample":
        output["message"] += " 샘플 장소와 거리는 가상 데이터입니다."
    return output
