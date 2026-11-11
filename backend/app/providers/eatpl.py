"""BC Card's partner search API. No implicit sample-mode fallback.

The caller supplies the partner-issued institution and a unique trace number;
credential issuance, IP allowlisting and trace-sequence storage are external.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
from urllib import error, request
from urllib.parse import urlsplit

from .models import Fact, Place


DEV_URL = "https://dev-api.paybooc.ai/api/mer"
PROD_URL = "https://api.paybooc.ai/api/mer"


class EatplError(Exception):
    """Base class for failures distinct from a successful empty result."""


class EatplAuthenticationError(EatplError):
    pass


class EatplTimeoutError(EatplError):
    pass


class EatplResponseError(EatplError):
    pass


class EatplNetworkError(EatplError):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_detail_url(value: object) -> str | None:
    if not isinstance(value, str) or any(ord(ch) < 32 or ch.isspace() for ch in value):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme == "https" and parsed.netloc == "web.paybooc.ai"
                and re.fullmatch(r"/mer/web/profile/[^/?#]+", parsed.path)
                and not parsed.query and not parsed.fragment):
            return value
    except ValueError:
        pass
    return None


# Only labels whose meaning is sufficiently specific are mapped. Ambiguous
# taxonomy values stay unknown rather than becoming invented restaurant data.
_RESTAURANT_CATEGORIES = {
    "일반한식", "서양음식", "중국음식", "일식회집", "갈비전문점", "한정식",
    "고기구이", "찜/탕/찌개", "치킨", "국수/면/만두", "해산물구이/찜",
    "김밥전문점", "분식", "기타외국식", "곱창전골/구이", "피자", "족발/보쌈",
    "버거", "스시/초밥", "떡볶이전문점", "도시락/죽", "일식돈가스", "뷔페",
    "마라탕", "이탈리아음식", "양꼬치", "아시안", "전/부침개", "일식라멘",
    "멕시칸", "프랑스음식", "비건/채식/사찰",
}


def map_place(row: object) -> Place:
    """Convert a documented data[] record without inferring missing fields."""
    if not isinstance(row, dict):
        raise EatplResponseError("invalid merchant record")
    name, address = row.get("merNm"), row.get("merAddr")
    if not isinstance(name, str) or not name.strip():
        raise EatplResponseError("merchant name missing")
    if address is not None and not isinstance(address, str):
        raise EatplResponseError("invalid merchant address")
    detail_url = _safe_detail_url(row.get("merUrl"))
    # The documented response does not provide a separate merchant ID. Prefer
    # the detail URL as identity; without it, name+address is a best-effort key.
    if not detail_url and not address:
        raise EatplResponseError("merchant lacks both stable detail URL and address")
    identity = detail_url or json.dumps([name, address], ensure_ascii=False, separators=(",", ":"))
    place_id = "eatpl:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    business_type = row.get("merTpbuzNm")
    if not isinstance(business_type, str):
        business_type = None
    category = "cafe" if business_type == "카페" else (
        "restaurant" if business_type in _RESTAURANT_CATEGORIES else "unknown")
    attributes = {}
    for raw_key, key in (("merTpbuzNm", "business_type"), ("allSaleRnk", "national_sales_percentile"),
                         ("ccgSaleRnk", "regional_sales_percentile"),
                         ("srtTime", "estimated_open_time"), ("endTime", "estimated_close_time")):
        value = row.get(raw_key)
        if value is not None and isinstance(value, (str, int, float)) and not isinstance(value, bool):
            attributes[key] = Fact(value=value, source="eatpl")
    # xaxsVal/yaxsVal are TM128, not latitude/longitude. Leave both unset.
    return Place(id=place_id, name=name, category=category, address=address,
                 latitude=None, longitude=None, attributes=attributes,
                 eatpl_url=detail_url, source="eatpl")


class EatplPlaceProvider:
    source = "eatpl"

    def __init__(self, institution: str, *, base_url: str = DEV_URL, timeout: float = 10.0):
        if not isinstance(institution, str) or not institution.strip():
            raise ValueError("partner institution is required")
        if base_url not in (DEV_URL, PROD_URL):
            raise ValueError("only documented HTTPS endpoints are supported")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.institution = institution
        self.base_url = base_url
        self.timeout = timeout

    def search(self, *, trace_number: str, location: str | None = None,
               business_type: str | None = None, merchant_name: str | None = None) -> list[Place]:
        """Return a list (including [] for successful zero results).

        trace_number must use institution + YYYYMMDD + a ten-digit sequence.
        The caller is responsible for ensuring its uniqueness across processes.
        """
        if not re.fullmatch(re.escape(self.institution) + r"\d{18}", trace_number):
            raise ValueError("trace number must be institution + YYYYMMDD + 10-digit sequence")
        params = {"location": location, "merTpbuzNm": business_type, "merNm": merchant_name}
        if not any(isinstance(value, str) and value.strip() for value in params.values()):
            raise ValueError("at least one nonempty search field is required")
        if any(value is not None and not isinstance(value, str) for value in params.values()):
            raise ValueError("search fields must be strings")
        payload = {"trnsTrceNo": trace_number, "instNm": self.institution}
        payload.update({key: value for key, value in params.items() if value and value.strip()})
        req = request.Request(self.base_url + "/v1/search", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        try:
            with request.build_opener(_NoRedirect()).open(req, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
        except error.HTTPError as exc:
            if exc.code in (401, 403):
                raise EatplAuthenticationError("partner authorization or IP registration failed") from exc
            raise EatplNetworkError(f"eatpl HTTP error {exc.code}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise EatplTimeoutError("eatpl request timed out") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise EatplTimeoutError("eatpl request timed out") from exc
            raise EatplNetworkError("eatpl network request failed") from exc
        if len(raw) > 2_000_000:
            raise EatplResponseError("eatpl response exceeds size limit")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise EatplResponseError("invalid JSON response") from exc
        if not isinstance(body, dict) or body.get("rspCode") != "00000" or not isinstance(body.get("data"), list):
            raise EatplResponseError("unsuccessful or malformed eatpl response")
        return [map_place(row) for row in body["data"]]
