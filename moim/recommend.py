"""참여자 선호를 합쳐 가게를 추천한다.

- 지역과 장소 종류(카페/식당/술집)는 참여자 투표로 정한다(직접 바꿀 수도 있음).
- 알레르기: 누구 하나라도 가진 알레르기의 위험이 '높음'인 가게는 제외, '보통·모름'은 주의 표시.
- 선호(종류·예산·분위기): 같은 선호를 고른 사람이 많을수록 점수가 높다.
"""

from __future__ import annotations

from collections import Counter

from .eatpl import EatplError, search_places
from .estimate import estimate_places
from .options import BUDGETS, PLACE_TYPES, REGIONS

TOP_N = 10
W_STYLE, W_BUDGET_FIT, W_BUDGET_OVER, W_ATMOS, W_MEDIUM_RISK = 3, 2, -2, 1, -2


def allergens_of(people: list[dict]) -> dict[str, list[str]]:
    """{알레르기: [이름...]}"""
    out: dict[str, list[str]] = {}
    for p in people:
        for a in p.get("allergies", []) + ([p["allergy_other"]] if p.get("allergy_other") else []):
            out.setdefault(a, []).append(p["name"])
    return out


def _winner(counter: Counter, order: list[str]):
    if not counter:
        return None
    best = max(counter.values())
    tied = [k for k in counter if counter[k] == best]
    return sorted(tied, key=lambda k: order.index(k) if k in order else len(order))[0]


def summarize(people: list[dict]) -> dict:
    regions = Counter(p["region"] for p in people)
    types = Counter(p["place_type"] for p in people)
    styles = {t: Counter(s for p in people if p["place_type"] == t for s in p["styles"]) for t in PLACE_TYPES}
    return {
        "count": len(people),
        "regions": dict(regions.most_common()),
        "place_types": {t: types.get(t, 0) for t in PLACE_TYPES},
        "styles": {t: dict(c.most_common()) for t, c in styles.items()},
        "budgets": {str(b): sum(1 for p in people if p.get("budget") == b) for b in BUDGETS},
        "atmospheres": dict(Counter(a for p in people for a in p["atmospheres"]).most_common()),
        "allergies": allergens_of(people),
        "region": _winner(regions, REGIONS),
        "place_type": _winner(types, list(PLACE_TYPES)),
    }


def score_place(place: dict, est: dict, people: list[dict], place_type: str, allergy_people: dict) -> dict:
    reasons, cautions, score = [], [], 0
    # 알레르기
    unknown = []
    for allergen, names in allergy_people.items():
        risk = est["allergy_risk"].get(allergen, "unknown")
        who = ", ".join(names)
        if risk == "high":
            return {"excluded": True, "reason": f"{allergen} 알레르기({who}) 위험이 높은 업종이에요."}
        if risk == "medium":
            score += W_MEDIUM_RISK
            cautions.append(f"{allergen} 포함 가능성 있음 ({who}) — 매장에 꼭 확인하세요.")
        elif risk == "unknown":
            unknown.append(allergen)
    if unknown:
        cautions.append(f"알레르기 정보 없음: {', '.join(unknown)} — 매장에 확인하세요.")
    # 종류
    voters = [p for p in people if p["place_type"] == place_type and p["styles"]]
    for style in est["styles"]:
        fans = [p for p in voters if style in p["styles"]]
        if fans:
            score += W_STYLE * len(fans)
            reasons.append(f"{len(voters)}명 중 {len(fans)}명이 원하는 {style}")
    # 예산
    band = est["price_band"]
    budget_people = [p for p in people if p.get("budget")]
    if band and budget_people:
        fit = [p for p in budget_people if band <= p["budget"]]
        over = [p for p in budget_people if band > p["budget"] + 1]
        score += W_BUDGET_FIT * len(fit) + W_BUDGET_OVER * len(over)
        reasons.append(f"1인 {BUDGETS[band]} 추정 · 예산 맞는 사람 {len(fit)}/{len(budget_people)}")
    elif budget_people:
        cautions.append("가격대 정보 없음")
    # 분위기
    for a in est["atmospheres"]:
        fans = [p for p in people if a in p["atmospheres"]]
        if fans:
            score += W_ATMOS * len(fans)
            reasons.append(f"분위기 '{a}' 원하는 사람 {len(fans)}명")
    return {"excluded": False, "score": score, "reasons": reasons, "cautions": cautions}


def recommend(people: list[dict], client, store=None, *, region: str | None = None,
              place_type: str | None = None, api_key: str | None = None) -> dict:
    if not people:
        raise ValueError("아직 참여한 사람이 없어요.")
    summary = summarize(people)
    region = (region or summary["region"] or "").strip()
    place_type = place_type or summary["place_type"]
    if not region or place_type not in PLACE_TYPES:
        raise ValueError("지역과 장소 종류를 확인해 주세요.")

    out = {"region": region, "place_type": place_type, "summary": summary, "source": client.source,
           "results": [], "excluded": [], "warnings": [], "status": "ok"}
    try:
        places = search_places(client, region, place_type)
    except EatplError as e:
        out.update(status="error", message=str(e))
        return out
    if not places:
        out.update(status="empty", message=f"{region}에서 {PLACE_TYPES[place_type]}을(를) 찾지 못했어요. 지역을 바꿔 보세요.")
        return out

    allergy_people = summary["allergies"]
    estimates, warnings = estimate_places(places, place_type, list(allergy_people), store=store, api_key=api_key)
    out["warnings"] = warnings
    scored = []
    for p in places:
        est = estimates[p["id"]]
        s = score_place(p, est, people, place_type, allergy_people)
        if s["excluded"]:
            out["excluded"].append({"name": p["name"], "reason": s["reason"]})
            continue
        scored.append({**p, "estimate": est, **{k: s[k] for k in ("score", "reasons", "cautions")}})
    scored.sort(key=lambda x: (-x["score"], x["sales_rank"] if x["sales_rank"] is not None else 10 ** 9, x["name"]))
    out["results"] = scored[:TOP_N]
    if not out["results"]:
        out.update(status="empty", message="알레르기 조건 때문에 추천할 수 있는 곳이 없어요. 장소 종류를 바꿔 보세요.")
    return out
