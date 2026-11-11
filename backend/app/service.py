"""Translate the local demo's date-course input to places and courses."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextlib import closing
from math import isfinite
import os
import sqlite3
from urllib.error import HTTPError, URLError

from backend.app.providers.eatpl import (
    DEV_URL, PROD_URL, EatplAuthenticationError, EatplError, EatplNetworkError,
    EatplPlaceProvider, EatplResponseError, EatplTimeoutError,
)
from backend.app.providers.mock import sample_places
from backend.app.recommendations.courses import build_courses
from backend.app.recommendations.evaluation import Constraint
from backend import skill_probe


def next_trace_number(institution: str, database_path: str) -> str:
    """Allocate a date-scoped sequence transactionally across local processes."""
    date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
    with closing(sqlite3.connect(database_path, timeout=10, isolation_level=None)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS trace_sequence (institution TEXT NOT NULL, day TEXT NOT NULL, sequence INTEGER NOT NULL, PRIMARY KEY (institution, day))")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("INSERT OR IGNORE INTO trace_sequence VALUES (?, ?, 0)", (institution, date))
            db.execute("UPDATE trace_sequence SET sequence = sequence + 1 WHERE institution = ? AND day = ?", (institution, date))
            sequence = db.execute("SELECT sequence FROM trace_sequence WHERE institution = ? AND day = ?", (institution, date)).fetchone()[0]
            if sequence > 9_999_999_999:
                raise ValueError("daily trace sequence exhausted")
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    return f"{institution}{date}{sequence:010d}"


def _validate(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("요청 형식을 확인해 주세요.")
    allowed = {"mode", "region", "order", "max_total_per_person_krw", "max_leg_distance_m", "constraints"}
    if set(payload) - allowed:
        raise ValueError("지원하지 않는 요청 항목이 있습니다.")
    mode, region = payload.get("mode"), payload.get("region")
    order = payload.get("order")
    if mode not in ("sample", "eatpl", "skill-test"):
        raise ValueError("조회 데이터 종류를 선택해 주세요.")
    if not isinstance(region, str) or not region.strip() or len(region) > 120:
        raise ValueError("지역을 입력해 주세요. (120자 이내)")
    if not isinstance(order, list) or order not in (["cafe", "restaurant"], ["restaurant", "cafe"]):
        raise ValueError("카페와 식당 순서를 선택해 주세요.")
    result = {"mode": mode, "region": region.strip(), "order": order}
    for key in ("max_total_per_person_krw", "max_leg_distance_m"):
        value = payload.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 1_000_000_000 or not isfinite(value)):
            raise ValueError("예산과 최대 직선거리는 0 이상의 숫자로 입력해 주세요.")
        result[key] = value
    raw_constraints = payload.get("constraints", [])
    if not isinstance(raw_constraints, list) or len(raw_constraints) > 50:
        raise ValueError("조건은 최대 50개까지 입력할 수 있습니다.")
    constraints = []
    ids = set()
    for raw in raw_constraints:
        if not isinstance(raw, dict):
            raise ValueError("조건 형식을 확인해 주세요.")
        required = {"id", "owner_id", "field", "operator", "value"}
        allowed_fields = required | {"strength", "scope", "stop_index", "active"}
        if not required <= raw.keys() or set(raw) - allowed_fields:
            raise ValueError("조건의 필수 항목 또는 지원 여부를 확인해 주세요.")
        for key in ("id", "owner_id", "field"):
            if not isinstance(raw[key], str) or not raw[key].strip() or len(raw[key]) > 120:
                raise ValueError("조건 식별자, 작성자, 필드를 확인해 주세요.")
        if raw["id"] in ids:
            raise ValueError("중복된 조건 식별자가 있습니다.")
        ids.add(raw["id"])
        operator = raw["operator"]
        if not isinstance(operator, str) or operator not in ("eq", "neq", "lte", "gte", "contains", "excludes"):
            raise ValueError("지원하지 않는 조건 연산자입니다.")
        value = raw["value"]
        if isinstance(value, str):
            if not value.strip() or len(value) > 200:
                raise ValueError("조건 값을 확인해 주세요.")
        elif isinstance(value, bool):
            pass
        elif not isinstance(value, (int, float)) or not -1_000_000_000_000 <= value <= 1_000_000_000_000 or not isfinite(value):
            raise ValueError("조건 값은 유효한 단일 값이어야 합니다.")
        if operator in ("lte", "gte") and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError("크기 비교에는 숫자 값이 필요합니다.")
        if operator in ("contains", "excludes") and not isinstance(value, str):
            raise ValueError("포함 조건에는 문자열 값이 필요합니다.")
        strength = raw.get("strength", "hard")
        scope = raw.get("scope", "room")
        stop_index = raw.get("stop_index")
        active = raw.get("active", True)
        if strength not in ("hard", "soft") or scope not in ("room", "stop") or not isinstance(active, bool):
            raise ValueError("조건 적용 설정을 확인해 주세요.")
        if scope == "stop":
            if isinstance(stop_index, bool) or not isinstance(stop_index, int) or stop_index not in (0, 1):
                raise ValueError("장소별 조건의 순서를 확인해 주세요.")
        elif stop_index is not None:
            raise ValueError("전체 조건에는 장소 순서를 지정할 수 없습니다.")
        constraints.append(Constraint(id=raw["id"], owner_id=raw["owner_id"], field=raw["field"],
                                      operator=operator, value=value, strength=strength, scope=scope,
                                      stop_index=stop_index, active=active))
    # owner_id groups preferences; authorization belongs to the future room server.
    result["constraints"] = constraints
    return result


def search_courses(payload: object, *, provider=None, trace_factory=None) -> dict:
    """Raise ValueError for invalid input; return explicit service outcomes otherwise."""
    request = _validate(payload)
    source = {"sample": "mock", "eatpl": "eatpl", "skill-test": "skill-test"}[request["mode"]]
    output = {"source": source, "status": "error", "message": "", "courses": [], "truncated": False}
    if source == "mock":
        places = sample_places(region=request["region"])
    elif source == "skill-test":
        try:
            places, cache_hit = skill_probe.fetch_places(request["region"])
        except (TimeoutError, HTTPError, URLError, OSError, EatplError):
            output["message"] = "스킬 테스트 조회에 실패했습니다. 네트워크와 서비스 상태를 확인해 주세요."
            return output
        output["cache_hit"] = cache_hit
        output["truncated"] = len(places) >= 100
        # A narrow region may return only one kind of venue. Show the received
        # places and links even when a two-stop course cannot be constructed.
        output["place_options"] = [{"name": p.name, "address": p.address,
                                    "eatpl_url": p.eatpl_url} for p in places[:10]]
        output["place_count"] = len(places)
    else:
        institution = os.getenv("EATPL_INSTITUTION", "").strip()
        environment = os.getenv("EATPL_ENV", "dev")
        if provider is None and (not institution or environment not in ("dev", "prod")):
            output["message"] = "잇플 제휴 기관명과 서버 환경 설정을 확인해 주세요. 현재 실제 조회가 설정되지 않았습니다."
            return output
        if provider is None:
            provider = EatplPlaceProvider(institution, base_url=DEV_URL if environment == "dev" else PROD_URL)
        if trace_factory is None:
            trace_factory = lambda: next_trace_number(institution, os.getenv("EATPL_TRACE_DB", "eatpl_traces.sqlite3"))
        try:
            # The API has no general restaurant category. Search the region once,
            # then use only known, documented categories for composing courses.
            places = provider.search(trace_number=trace_factory(), location=request["region"])
        except EatplAuthenticationError:
            output["message"] = "잇플 인증에 실패했습니다. 기관명과 호출 서버 IP 등록을 확인해 주세요."
            return output
        except EatplTimeoutError:
            output["message"] = "잇플 응답 시간이 초과됐습니다. 잠시 후 다시 시도해 주세요."
            return output
        except EatplNetworkError:
            output["message"] = "잇플에 연결하지 못했습니다. 네트워크 상태를 확인하고 다시 시도해 주세요."
            return output
        except (EatplResponseError, EatplError):
            output["message"] = "잇플이 정상 응답을 반환하지 않았습니다. 잠시 후 다시 시도해 주세요."
            return output
        except (sqlite3.Error, OSError, ValueError):
            output["message"] = "잇플 요청 번호를 발급하지 못했습니다. 서버 설정과 저장소를 확인해 주세요."
            return output
        output["truncated"] = len(places) >= 100

    result = build_courses(places, request["constraints"], ordered_stops=request["order"],
                           max_leg_distance_m=request["max_leg_distance_m"],
                           max_total_per_person_krw=request["max_total_per_person_krw"])
    for status, options in (("eligible", result.eligible), ("needs_review", result.needs_review)):
        for option in options:
            output["courses"].append({
                "status": status,
                "places": [{"name": p.name, "address": p.address, "eatpl_url": p.eatpl_url} for p in option.places],
                "distance_m": option.legs[0].straight_line_distance_m,
                "total_per_person_krw": option.total_per_person_krw,
                "reasons": list(option.reasons),
            })
    if output["courses"]:
        output.update(status="ok", message="조건을 바탕으로 코스를 구성했습니다.")
    else:
        output.update(status="empty", message="조건에 맞는 카페·식당 조합이 없습니다. 지역이나 제한 조건을 바꿔 보세요.")
    return output
