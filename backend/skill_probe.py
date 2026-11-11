"""One-off personal k-skill lookup for verifying the documented proxy.

The local application's explicit personal test mode also uses this module.
It does not establish team-service rights.
"""

from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.app.providers.eatpl import EatplResponseError, map_place

SKILL_URL = "https://k-skill-proxy.nomadamas.org/v1/bccard-eatpl/search"
MAX_RESPONSE = 2_000_000


def parse_response(raw: bytes):
    """Map the proxy's items wrapper, which differs from the direct API."""
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise EatplResponseError("스킬 응답이 올바른 JSON이 아닙니다.") from exc
    if not isinstance(body, dict) or not isinstance(body.get("items"), list):
        raise EatplResponseError("스킬 응답에 유효한 items 목록이 없습니다.")
    upstream = body.get("upstream")
    if not isinstance(upstream, dict) or upstream.get("status_code") != 200:
        raise EatplResponseError("잇플 상위 응답의 성공 상태를 확인할 수 없습니다.")
    proxy = body.get("proxy")
    cache = proxy.get("cache") if isinstance(proxy, dict) else None
    hit = cache.get("hit") if isinstance(cache, dict) and isinstance(cache.get("hit"), bool) else None
    return [map_place(item) for item in body["items"]], hit


def fetch_places(location: str, business_type: str | None = None):
    """Perform exactly one explicit personal lookup; propagate all failures."""
    if not isinstance(location, str) or not location.strip():
        raise ValueError("지역을 입력해 주세요.")
    params = {"location": location.strip()}
    if business_type is not None:
        if not isinstance(business_type, str) or not business_type.strip():
            raise ValueError("업종을 확인해 주세요.")
        params["merTpbuzNm"] = business_type.strip()
    url = SKILL_URL + "?" + urlencode(params)
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=20) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise EatplResponseError("스킬 응답이 너무 큽니다.")
    return parse_response(raw)


def main():
    parser = argparse.ArgumentParser(description="개인 단발 잇플 스킬 조회 확인")
    parser.add_argument("--location", default="서울 중구 을지로30길 20", help="검색 지역 또는 주소")
    parser.add_argument("--business-type", default="카페", help="잇플 업종명")
    args = parser.parse_args()
    if not args.location.strip() or not args.business_type.strip():
        parser.error("지역과 업종을 입력해 주세요")
    try:
        places, cache_hit = fetch_places(args.location, args.business_type)
    except Exception as exc:
        print(f"조회 실패: {type(exc).__name__}. 네트워크와 스킬 서비스 상태를 확인해 주세요.")
        return 1
    print("스킬 프록시 조회 성공. eat.pl 잇플 · BC카드 결제 데이터 기반")
    print("캐시:", "사용" if cache_hit is True else "사용 안 함" if cache_hit is False else "미확인")
    print(f"가맹점 {len(places)}건 (주소 부분 일치 검색)")
    for place in places:
        print(f"- {place.name} | {place.address or '주소 미확인'} | {place.eatpl_url or '상세 링크 미확인'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
