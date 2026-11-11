"""Read-only adapter: maps selected documented Eat.pl fields to our team's Place contract.

Does not make live network calls. The team member responsible for Eat.pl connection
should pass a single merchant record dict here. Fields not established by Eat.pl
(capacity/menu safety/WGS84) intentionally remain UNKNOWN.
"""
import hashlib
from .validation import is_trusted_eatpl_url


def _clean_rank(value):
    try:
        r = float(value)
        return r if 0 <= r <= 100 else None
    except (TypeError, ValueError):
        return None


def _expected_hours(start, end):
    """Documented HHMM APPROXIMATE times, not official business hours."""
    a, b = str(start or "").zfill(4), str(end or "").zfill(4)
    if not (a.isdigit() and b.isdigit() and len(a) == len(b) == 4):
        return ""
    h1, m1, h2, m2 = int(a[:2]), int(a[2:]), int(b[:2]), int(b[2:])
    if not (h1 < 24 and h2 < 24 and m1 < 60 and m2 < 60):
        return ""
    suffix = "익일 " if (h2, m2) < (h1, m1) else ""
    return f"예상 {h1:02}:{m1:02}–{suffix}{h2:02}:{m2:02} (공식 영업시간 아님)"


def normalize_eatpl_merchant(record: dict, *, region_hint: str = "") -> dict:
    """Converts one merchant object; actual response wrapper must be agreed with Backend #3."""
    name = str(record.get("merNm") or "").strip()
    address = str(record.get("addr") or "").strip()
    kind = str(record.get("merTpbuzNm") or "").strip()
    digest = hashlib.sha256(f"{name}|{address}".encode()).hexdigest()[:12]
    category = ("cafe" if ("카페" in kind or "커피" in kind or "제과" in kind)
                else "bar" if ("주점" in kind or "술집" in kind or "바(" in kind)
                else "restaurant" if any(x in kind for x in ("음식", "식당", "한식", "중식", "일식", "양식", "고기"))
                else "")
    # Text/alias search does not by itself prove the venue is in the user's requested area.
    inferred_region = region_hint if region_hint and region_hint in address else ""
    link = str(record.get("merUrl") or "").strip()
    return {
        "place_id": "eatpl-" + digest, "name": name, "address": address,
        "region": inferred_region, "category": category, "cuisine": "",
        "price_per_person_krw": None, "capacity": None,
        "lat_wgs84": None, "lon_wgs84": None,
        "coordinate_source": "", "coordinate_verified": False, "coordinate_evidence": "",
        "contains_terms": [], "safe_for_terms": [], "menu_verified": False,
        "menu_evidence": "", "tags": [], "tags_evidence": "",
        "merchant_url": link if is_trusted_eatpl_url(link) else "",
        "all_sale_rank_pct": _clean_rank(record.get("allSaleRnk")),
        "estimated_hours": _expected_hours(record.get("srtTime"), record.get("endTime")),
        "source": "eatpl", "is_demo": False,
        "_extra": {"ccg_sale_rank_pct": _clean_rank(record.get("ccgSaleRnk")), "raw_kind": kind},
    }
