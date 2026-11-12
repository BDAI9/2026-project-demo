"""가게별 추정: 가격대, 분위기, 종류(양식/이자카야 등), 알레르기 위험.

잇플 데이터에는 가격·메뉴·재료·분위기가 없다. 그래서
1) 업종(merTpbuzNm)으로 확실히 알 수 있는 것(종류, 대표적인 알레르기 위험)은 규칙으로 정하고,
2) 나머지(가격대, 분위기, 기타 알레르기)는 OpenRouter 무료 AI가 가게 이름·업종으로 추정한다.
AI 추정은 틀릴 수 있으므로 화면에 'AI 추정'으로 표시한다. 알레르기는 규칙과 AI 중 더 위험한 쪽을 쓴다.
"""

from __future__ import annotations

import json
import os
import re
import socket
from urllib import error, request

from .options import ATMOSPHERES, BUDGETS, STYLES

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODELS = ["google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free", "nvidia/nemotron-3.5-lightning:free"]
BATCH = 20
RISK = ("unknown", "low", "medium", "high")

# ---------------------------------------------------------------- 규칙
_STYLE_BY_TYPE = {}
for _style, _types in {
    "한식": ["일반한식", "한정식", "찜/탕/찌개", "도시락/죽", "전/부침개", "해산물구이/찜"],
    "중식": ["중국음식", "마라탕", "양꼬치"],
    "일식": ["일식회집", "스시/초밥", "일식돈가스", "일식라멘"],
    "양식": ["서양음식", "이탈리아음식", "프랑스음식", "멕시칸"],
    "아시안": ["아시안", "기타외국식"],
    "고기·구이": ["갈비전문점", "고기구이", "곱창전골/구이", "족발/보쌈"],
    "분식": ["분식", "김밥전문점", "떡볶이전문점", "국수/면/만두"],
    "치킨·버거·피자": ["치킨", "피자", "버거"],
    "채식": ["비건/채식/사찰"],
    "호프·맥주": ["호프"],
    "이자카야": ["이자카야"],
    "와인·칵테일 바": ["바(bar)"],
    "포차·소주": ["기타주점"],
}.items():
    for _t in _types:
        _STYLE_BY_TYPE[_t] = _style

_SEAFOOD = {"갑각류(새우·게)": "high", "조개류": "high", "생선": "high", "오징어": "high"}
_ALLERGY_BY_TYPE = {
    "일식회집": _SEAFOOD, "스시/초밥": _SEAFOOD, "해산물구이/찜": _SEAFOOD,
    "중국음식": {"갑각류(새우·게)": "medium", "대두": "medium", "밀·글루텐": "medium"},
    "마라탕": {"갑각류(새우·게)": "medium", "대두": "high", "땅콩": "medium", "밀·글루텐": "medium"},
    "일식돈가스": {"돼지고기": "high", "밀·글루텐": "high", "달걀": "medium"},
    "일식라멘": {"돼지고기": "high", "밀·글루텐": "high", "달걀": "medium"},
    "치킨": {"닭고기": "high", "밀·글루텐": "medium"},
    "피자": {"밀·글루텐": "high", "우유·유제품": "high", "토마토": "high"},
    "버거": {"밀·글루텐": "high", "소고기": "high", "우유·유제품": "medium", "달걀": "medium", "토마토": "medium"},
    "이탈리아음식": {"밀·글루텐": "high", "우유·유제품": "high", "토마토": "medium"},
    "국수/면/만두": {"밀·글루텐": "high"},
    "분식": {"밀·글루텐": "medium", "달걀": "medium"},
    "떡볶이전문점": {"밀·글루텐": "medium"},
    "김밥전문점": {"달걀": "medium"},
    "족발/보쌈": {"돼지고기": "high"},
    "갈비전문점": {"돼지고기": "medium", "소고기": "medium"},
    "고기구이": {"돼지고기": "medium", "소고기": "medium"},
    "곱창전골/구이": {"소고기": "medium", "돼지고기": "medium"},
    "카페": {"우유·유제품": "medium", "밀·글루텐": "medium", "달걀": "medium", "견과류": "medium"},
}


def rule_estimate(place: dict, allergens: list[str]) -> dict:
    btype = place.get("business_type")
    style = _STYLE_BY_TYPE.get(btype)
    risks = _ALLERGY_BY_TYPE.get(btype, {})
    return {"price_band": None, "atmospheres": [], "styles": [style] if style else [],
            "allergy_risk": {a: risks.get(a, "unknown") for a in allergens}, "source": "rule"}


# ---------------------------------------------------------------- AI
_SYSTEM = """너는 음식점·카페·술집 정보를 추정하는 도우미야. 가게 이름과 업종만 보고 일반적인 경우를 추정해.
반드시 JSON 하나로만 답해: {"places": [{"id": "...", "price_band": 1~5 또는 null, "atmospheres": [...], "styles": [...], "allergy_risk": {"알레르기": "high|medium|low|unknown"}}]}
- price_band: 1인 기준 1=1만원 이하, 2=1~2만원, 3=2~3만원, 4=3~5만원, 5=5만원 이상. 모르면 null.
- atmospheres: 아래 목록에서만, 그럴 가능성이 높은 것 최대 3개: %s
- styles: 아래 목록에서만, 해당하는 것: %s
- allergy_risk: 요청한 알레르기 각각에 대해 그 업종 메뉴에 들어갈 가능성. high=대표 메뉴에 거의 들어감, medium=자주 들어감, low=거의 없음, unknown=판단 불가.
  안전과 관련되므로 애매하면 low가 아니라 unknown 또는 medium으로 답해.
- 모든 가게의 id를 그대로 돌려줘. 설명은 쓰지 마."""


def _models() -> list[str]:
    raw = os.getenv("OPENROUTER_MODEL", "")
    return [m.strip() for m in raw.split(",") if m.strip()] or list(DEFAULT_MODELS)


def _post(api_key: str, model: str, messages: list[dict], timeout: float = 30) -> str:
    body = json.dumps({"model": model, "messages": messages, "temperature": 0,
                       "response_format": {"type": "json_object"}}, ensure_ascii=False).encode("utf-8")
    req = request.Request(OPENROUTER_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "X-Title": "BDAI moim"})
    with request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read(2_000_000))
    return data["choices"][0]["message"]["content"] or ""


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("JSON 없음")
        return json.loads(m.group(0))


def _clean_ai(item: dict, place_type: str, allergens: list[str]) -> dict:
    band = item.get("price_band")
    band = band if isinstance(band, int) and not isinstance(band, bool) and band in BUDGETS else None
    atmos = [a for a in item.get("atmospheres") or [] if a in ATMOSPHERES][:3]
    styles = [s for s in item.get("styles") or [] if s in STYLES[place_type]]
    raw_risk = item.get("allergy_risk") if isinstance(item.get("allergy_risk"), dict) else {}
    risk = {a: (raw_risk.get(a) if raw_risk.get(a) in RISK else "unknown") for a in allergens}
    return {"price_band": band, "atmospheres": list(dict.fromkeys(atmos)), "styles": list(dict.fromkeys(styles)),
            "allergy_risk": risk, "source": "ai"}


def ai_estimate(places: list[dict], place_type: str, allergens: list[str], api_key: str) -> dict:
    """AI로 추정. 모델을 순서대로 시도하고 모두 실패하면 RuntimeError(한국어 메시지)."""
    system = _SYSTEM % (", ".join(ATMOSPHERES), ", ".join(STYLES[place_type]))
    user = json.dumps({"요청한 알레르기": allergens,
                       "가게": [{"id": p["id"], "이름": p["name"], "업종": p.get("business_type")} for p in places]},
                      ensure_ascii=False)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last = "알 수 없는 오류"
    for model in _models():
        try:
            obj = _parse_json(_post(api_key, model, messages))
        except error.HTTPError as e:
            if e.code in (401, 402):
                raise RuntimeError("OpenRouter 키가 올바르지 않거나 크레딧이 부족해요.") from e
            last = f"HTTP {e.code}"
            continue
        except (error.URLError, TimeoutError, socket.timeout, ValueError, KeyError, IndexError, TypeError) as e:
            last = type(e).__name__
            continue
        items = obj.get("places") if isinstance(obj, dict) else None
        if not isinstance(items, list):
            last = "형식 오류"
            continue
        by_id = {str(i.get("id")): i for i in items if isinstance(i, dict)}
        return {p["id"]: _clean_ai(by_id[p["id"]], place_type, allergens) for p in places if p["id"] in by_id}
    raise RuntimeError(f"AI 추정에 실패했어요 ({last}). 업종 정보만으로 추천했어요.")


def _merge(rule: dict, ai: dict | None) -> dict:
    if not ai:
        return rule
    risk = {a: max(rule["allergy_risk"].get(a, "unknown"), ai["allergy_risk"].get(a, "unknown"),
                   key=RISK.index) for a in rule["allergy_risk"]}
    return {"price_band": ai["price_band"], "atmospheres": ai["atmospheres"],
            "styles": rule["styles"] or ai["styles"], "allergy_risk": risk, "source": "ai"}


def estimate_places(places: list[dict], place_type: str, allergens: list[str], store=None,
                    api_key: str | None = None) -> tuple[dict, list[str]]:
    """{place_id: 추정} 와 경고 목록을 돌려준다. 캐시가 있으면 AI를 다시 부르지 않는다."""
    api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "").strip()
    warnings: list[str] = []
    cached = store.get_estimates([p["id"] for p in places], allergens) if store else {}
    todo = [p for p in places if p["id"] not in cached]
    ai_results: dict = {}
    if todo and api_key:
        for i in range(0, len(todo), BATCH):
            try:
                ai_results.update(ai_estimate(todo[i:i + BATCH], place_type, allergens, api_key))
            except RuntimeError as e:
                if str(e) not in warnings:
                    warnings.append(str(e))
    elif todo:
        warnings.append("OPENROUTER_API_KEY가 없어 가격대·분위기는 추정하지 않고 업종 정보로만 추천했어요.")
    fresh = {p["id"]: _merge(rule_estimate(p, allergens), ai_results.get(p["id"])) for p in todo}
    if store:
        store.save_estimates({k: v for k, v in fresh.items() if v["source"] == "ai"}, allergens)
    return {**cached, **fresh}, warnings
