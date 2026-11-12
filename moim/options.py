"""참여자가 고를 수 있는 선택지. 화면과 서버 검증, AI 프롬프트가 모두 이 목록을 쓴다."""

from __future__ import annotations

REGIONS = ["홍대", "합정", "연남", "성수", "건대", "강남", "신촌", "이태원", "종로", "을지로", "잠실", "여의도"]

PLACE_TYPES = {"cafe": "카페", "restaurant": "식당", "bar": "술집"}

# 장소 종류를 고르면 그에 맞는 '종류' 선택지가 바뀐다.
STYLES = {
    "cafe": ["커피 맛집", "디저트·케이크", "베이커리", "대형·뷰 카페", "공부·작업"],
    "restaurant": ["한식", "중식", "일식", "양식", "아시안", "고기·구이", "분식", "치킨·버거·피자", "채식"],
    "bar": ["호프·맥주", "이자카야", "와인·칵테일 바", "포차·소주", "전통주"],
}
STYLE_LABEL = {"cafe": "카페 스타일", "restaurant": "먹고 싶은 음식", "bar": "술집 종류"}

# 1인 예산 구간. 값이 클수록 비싸다.
BUDGETS = {1: "1만원 이하", 2: "1~2만원", 3: "2~3만원", 4: "3~5만원", 5: "5만원 이상"}

ATMOSPHERES = ["조용한", "대화하기 좋은", "활기찬", "감성·인테리어", "넓은·단체석", "가성비", "뷰 좋은", "야외·테라스"]

ALLERGIES = ["갑각류(새우·게)", "조개류", "생선", "오징어", "땅콩", "견과류", "우유·유제품", "달걀",
             "밀·글루텐", "대두", "메밀", "복숭아", "토마토", "돼지고기", "소고기", "닭고기"]

MAX_NAME = 20
MAX_CUSTOM = 40
MAX_PARTICIPANTS = 30


def catalog() -> dict:
    """화면에 내려줄 전체 선택지."""
    return {
        "regions": REGIONS,
        "place_types": PLACE_TYPES,
        "styles": STYLES,
        "style_label": STYLE_LABEL,
        "budgets": {str(k): v for k, v in BUDGETS.items()},
        "atmospheres": ATMOSPHERES,
        "allergies": ALLERGIES,
    }


def _text(value, field, max_len, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_len:
        raise ValueError(f"{field}: {max_len}자 이내로 입력해 주세요.")
    return value.strip()


def _pick_many(value, allowed, field, limit=None):
    if value is None:
        return []
    if not isinstance(value, list) or any(v not in allowed for v in value):
        raise ValueError(f"{field}: 목록에 있는 값만 고를 수 있어요.")
    out = list(dict.fromkeys(value))
    if limit and len(out) > limit:
        raise ValueError(f"{field}: 최대 {limit}개까지 고를 수 있어요.")
    return out


def validate_preference(payload: object) -> dict:
    """참여자 한 명의 입력을 검사하고 정리한다."""
    if not isinstance(payload, dict):
        raise ValueError("입력 형식이 올바르지 않아요.")
    allowed = {"name", "region", "place_type", "styles", "budget", "atmospheres", "allergies", "allergy_other"}
    if set(payload) - allowed:
        raise ValueError("알 수 없는 입력 항목이 있어요.")

    name = _text(payload.get("name"), "이름", MAX_NAME)
    region = _text(payload.get("region"), "지역", MAX_CUSTOM)
    place_type = payload.get("place_type")
    if place_type not in PLACE_TYPES:
        raise ValueError("카페·식당·술집 중 하나를 골라 주세요.")
    styles = _pick_many(payload.get("styles"), STYLES[place_type], STYLE_LABEL[place_type])
    budget = payload.get("budget")
    if budget is not None and (isinstance(budget, bool) or budget not in BUDGETS):
        raise ValueError("예산 구간을 다시 골라 주세요.")
    atmospheres = _pick_many(payload.get("atmospheres"), ATMOSPHERES, "분위기", limit=3)
    allergies = _pick_many(payload.get("allergies"), ALLERGIES, "알레르기")
    other = payload.get("allergy_other")
    if other is not None and other != "":
        other = _text(other, "기타 알레르기", MAX_CUSTOM)
    else:
        other = None

    return {"name": name, "region": region, "place_type": place_type, "styles": styles, "budget": budget,
            "atmospheres": atmospheres, "allergies": allergies, "allergy_other": other}
