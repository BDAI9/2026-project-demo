"""BC카드 잇플 가맹점 검색 API(직접 제휴) 클라이언트와 샘플 데이터.

- 실제 모드: 환경 변수 EATPL_INSTITUTION(기관명)이 있으면 사용. 서버 IP를 잇플에 미리 등록해야 한다.
  EATPL_ENV=prod면 운영 서버, 그 외에는 개발 서버.
- 샘플 모드: 기관명이 없으면 moim/data/sample_places.json(가상 가게)을 쓴다. 화면에 '가상'이라고 표시한다.

API 정의: POST {base}/v1/search, 본문 {trnsTrceNo, instNm, location?, merTpbuzNm?, merNm?}
응답: {rspCode: "00000", data: [{merNm, merAddr, merUrl, merTpbuzNm, allSaleRnk, ccgSaleRnk, srtTime, endTime, ...}]}
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit

DEV_URL = "https://dev-api.paybooc.ai/api/mer"
PROD_URL = "https://api.paybooc.ai/api/mer"
SAMPLE_PATH = Path(__file__).resolve().parent / "data" / "sample_places.json"
MAX_BYTES = 2_000_000

CAFE_TYPES = {"카페"}
BAR_TYPES = {"기타주점", "호프", "이자카야", "바(bar)"}
RESTAURANT_TYPES = {
    "일반한식", "서양음식", "중국음식", "일식회집", "갈비전문점", "한정식", "고기구이", "찜/탕/찌개", "치킨",
    "국수/면/만두", "해산물구이/찜", "김밥전문점", "분식", "기타외국식", "곱창전골/구이", "피자", "족발/보쌈",
    "버거", "스시/초밥", "떡볶이전문점", "도시락/죽", "일식돈가스", "뷔페", "마라탕", "이탈리아음식", "양꼬치",
    "아시안", "전/부침개", "일식라멘", "멕시칸", "프랑스음식", "비건/채식/사찰",
}


class EatplError(Exception):
    """사용자에게 보여줘도 되는 한국어 메시지를 담는다."""


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def category_of(business_type) -> str:
    if business_type in CAFE_TYPES:
        return "cafe"
    if business_type in BAR_TYPES:
        return "bar"
    if business_type in RESTAURANT_TYPES:
        return "restaurant"
    return "unknown"


def safe_detail_url(value) -> str | None:
    """잇플 상세 페이지 주소만 통과시킨다 (다른 사이트로 새는 링크 방지)."""
    if not isinstance(value, str) or any(ch.isspace() or ord(ch) < 32 for ch in value):
        return None
    try:
        u = urlsplit(value)
    except ValueError:
        return None
    if (u.scheme == "https" and u.netloc == "web.paybooc.ai" and re.fullmatch(r"/mer/web/profile/[^/?#]+", u.path)
            and not u.query and not u.fragment):
        return value
    return None


def map_place(row, *, is_sample: bool = False) -> dict | None:
    """응답의 가게 한 건을 내부 형식으로. 이름이 없거나 식별할 수 없으면 None."""
    if not isinstance(row, dict):
        return None
    name, address = row.get("merNm"), row.get("merAddr")
    if not isinstance(name, str) or not name.strip():
        return None
    address = address.strip() if isinstance(address, str) and address.strip() else None
    url = safe_detail_url(row.get("merUrl"))
    if not url and not address:
        return None
    identity = url or json.dumps([name.strip(), address], ensure_ascii=False)
    btype = row.get("merTpbuzNm") if isinstance(row.get("merTpbuzNm"), str) else None
    rank = row.get("allSaleRnk")
    rank = rank if isinstance(rank, (int, float)) and not isinstance(rank, bool) else None
    return {
        "id": "eatpl:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
        "name": name.strip(),
        "address": address,
        "business_type": btype,
        "category": category_of(btype),
        "eatpl_url": None if is_sample else url,
        "sales_rank": rank,
        "open": row.get("srtTime") if isinstance(row.get("srtTime"), str) else None,
        "close": row.get("endTime") if isinstance(row.get("endTime"), str) else None,
        "is_sample": is_sample,
    }


class EatplClient:
    source = "eatpl"

    def __init__(self, institution: str, trace_factory, *, prod: bool = False, timeout: float = 10.0):
        if not institution or not institution.strip():
            raise ValueError("기관명이 필요해요.")
        self.institution = institution.strip()
        self.trace_factory = trace_factory
        self.base_url = PROD_URL if prod else DEV_URL
        self.timeout = timeout

    def search(self, location: str, business_type: str | None = None) -> list[dict]:
        payload = {"trnsTrceNo": self.trace_factory(self.institution), "instNm": self.institution,
                   "location": location}
        if business_type:
            payload["merTpbuzNm"] = business_type
        req = request.Request(self.base_url + "/v1/search",
                              data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              headers={"Content-Type": "application/json", "Accept": "application/json"},
                              method="POST")
        try:
            with request.build_opener(_NoRedirect()).open(req, timeout=self.timeout) as resp:
                raw = resp.read(MAX_BYTES + 1)
        except error.HTTPError as e:
            if e.code in (401, 403):
                raise EatplError("잇플 인증에 실패했어요. 기관명과 서버 IP 등록을 확인해 주세요.") from e
            raise EatplError(f"잇플 서버 오류가 났어요. (HTTP {e.code})") from e
        except (TimeoutError, socket.timeout) as e:
            raise EatplError("잇플 응답이 너무 늦어요.") from e
        except error.URLError as e:
            raise EatplError("잇플 서버에 연결하지 못했어요.") from e
        if len(raw) > MAX_BYTES:
            raise EatplError("잇플 응답이 너무 커요.")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as e:
            raise EatplError("잇플 응답을 읽지 못했어요.") from e
        if not isinstance(body, dict) or body.get("rspCode") != "00000" or not isinstance(body.get("data"), list):
            code = body.get("rspCode") if isinstance(body, dict) else None
            raise EatplError(f"잇플 검색이 실패했어요. (응답 코드 {code})")
        return [p for p in (map_place(r) for r in body["data"]) if p]


class SampleClient:
    """기관명이 없을 때 쓰는 가상 데이터. 지역 이름이 주소에 들어간 가게만 돌려준다."""

    source = "sample"

    def __init__(self, path: Path = SAMPLE_PATH):
        self.rows = json.loads(path.read_text(encoding="utf-8"))["data"]

    def search(self, location: str, business_type: str | None = None) -> list[dict]:
        out = []
        for row in self.rows:
            if location not in (row.get("merAddr") or "") and location not in row.get("merNm", ""):
                continue
            if business_type and row.get("merTpbuzNm") != business_type:
                continue
            place = map_place(row, is_sample=True)
            if place:
                out.append(place)
        return out


def make_client(store):
    institution = os.getenv("EATPL_INSTITUTION", "").strip()
    if institution:
        return EatplClient(institution, store.next_trace_number, prod=os.getenv("EATPL_ENV", "").strip() == "prod")
    return SampleClient()


def search_places(client, region: str, place_type: str) -> list[dict]:
    """지역과 장소 종류로 후보를 모은다. 카페는 업종으로 바로 검색, 나머지는 지역 검색 후 분류."""
    seen, out = set(), []
    calls = [("카페",)] if place_type == "cafe" else [(None,)]
    for (btype,) in calls:
        for p in client.search(region, btype):
            if p["category"] == place_type and p["id"] not in seen:
                seen.add(p["id"])
                out.append(p)
    return out
