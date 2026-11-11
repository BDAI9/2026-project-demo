"""규칙 기반 해석에 쓰는 단어 사전.

새 표현을 인식시키고 싶으면 여기 패턴만 추가하면 된다.
각 항목: (표준 이름, 종류, 정규식, 강제 극성)
  - 종류: food | atmosphere | place | region
  - 강제 극성: "neg"면 문맥과 상관없이 제외 조건 (예: "안 매운")
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

H = "가-힣"  # 한글 음절 범위
NB = rf"(?<![{H}])"  # 앞에 한글이 붙지 않음 (예: '로드맵'의 '맵' 방지)


class Term(NamedTuple):
    canonical: str
    kind: str
    pattern: re.Pattern
    force: Optional[str] = None


_RAW_TERMS: list[tuple[str, str, str, Optional[str]]] = [
    # ---- 음식 ----
    ("매운 음식", "food", r"안\s?매운|덜\s?매운|맵지\s?않|안\s?맵", "neg"),
    ("매운 음식", "food", rf"매운\s?(?:음식|거|것|걸)?|매콤|얼큰|{NB}맵", None),
    ("해산물", "food",
     rf"해산물|해물|수산|조개|새우|생선|{NB}굴(?![{H}])|횟집|"
     rf"{NB}회(?=$|[는를도랑이가나\s,.!?])", None),
    ("고기", "food", r"고기|삼겹|갈비|곱창|막창|대창", None),
    ("한식", "food", r"한식|국밥|찌개|백반|한정식|감자탕|비빔밥", None),
    ("중식", "food", r"중식|중국\s?(?:집|음식|요리)|짜장|짬뽕|탕수육|마라|훠궈|딤섬", None),
    ("일식", "food", r"일식|초밥|스시|오마카세|라멘|돈카츠|돈까스|우동", None),
    ("양식", "food", r"양식|파스타|스테이크|피자|리조또|브런치|이탈리안|프렌치", None),
    ("분식", "food", r"분식|떡볶이|김밥|순대|라면", None),
    ("치킨", "food", r"치킨|닭강정", None),
    ("버거", "food", r"햄?버거", None),
    ("아시안", "food", r"쌀국수|태국\s?음식|베트남\s?음식|커리|카레|아시안", None),
    ("채식", "food", r"비건|채식|베지", None),
    ("견과류", "food", r"견과|땅콩|호두|아몬드", None),
    ("갑각류", "food", r"갑각류", None),
    ("유제품", "food", r"유제품|우유", None),
    ("밀가루", "food", r"글루텐|밀가루", None),
    # ---- 분위기 ----
    ("조용한", "atmosphere", r"시끄럽지\s?않|안\s?시끄러|조용", None),
    ("시끄러운", "atmosphere", r"시끄럽|시끄러운|북적", None),
    ("분위기 좋은", "atmosphere", r"분위기\s?(?:좋|있|깡패)|감성|분위기", None),
    ("뷰 좋은", "atmosphere", rf"{NB}뷰|전망|야경|오션", None),
    ("야외·테라스", "atmosphere", r"야외|테라스|루프탑", None),
    ("룸·프라이빗", "atmosphere", rf"{NB}룸|프라이빗|개별\s?(?:실|룸)", None),
    ("단체석", "atmosphere", r"단체석|단체\s?(?:룸|가능)", None),
    ("가성비", "atmosphere", r"가성비|저렴|(?<!비)싼|착한\s?가격", None),
    ("주차 가능", "atmosphere", r"주차", None),
    # ---- 장소 종류 (데이트 코스 단계) ----
    ("카페", "place", r"카페|커피", None),
    ("디저트", "place", r"디저트|케이크|빙수|베이커리|빵집|마카롱", None),
    ("식당", "place",
     rf"식당|{NB}밥(?![{H}])|{NB}밥(?=[은을도먹이])|식사|맛집|레스토랑|(?:저녁|점심)\s?(?:먹|식사)", None),
    ("술집", "place",
     rf"술집|{NB}술(?=$|[은는을이도\s,.!?])|이자카야|포차|호프|{NB}펍|"
     rf"{NB}바(?=$|[\s,.!?에는])|와인\s?바|와인|맥주|칵테일|하이볼|{NB}2차", None),
    ("산책", "place", r"산책|공원|걷기|한강", None),
    ("전시", "place", r"전시|미술관|박물관|팝업|갤러리", None),
    ("영화", "place", r"영화", None),
    ("놀거리", "place", r"보드게임|방탈출|노래방|볼링|오락실|공방", None),
]

# 자주 쓰는 지역 이름. 짧아서 다른 단어와 겹치는 것은 뒤에 예외를 붙였다.
REGIONS = [
    "강남", "신논현", "역삼", "선릉", "삼성(?!전자)", "코엑스", "잠실", "송파", "건대", "성수",
    "왕십리", "홍대", "합정", "연남", "망원", "상수(?!도)", "신촌", "이대(?!로)", "마포", "공덕",
    "여의도", "영등포", "문래", "이태원", "한남", "용산", "해방촌", "종로", "익선동", "을지로",
    "광화문", "시청(?!률)", "명동", "동대문", "혜화", "대학로", "압구정", "신사(?!동)", "가로수길",
    "청담", "서초", "교대", "사당", "서울대입구", "샤로수길", "노원", "수유", "천호", "목동",
    "판교", "분당", "수원", "인천", "부산", "서면", "해운대", "대구", "대전", "광주",
]

# 지역 이름의 표준형: 패턴의 예외 부분을 뗀 이름
_REGION_NAMES = {re.sub(r"\(.*\)", "", r): r for r in REGIONS}

for _name, _pat in _REGION_NAMES.items():
    _RAW_TERMS.append((_name, "region", rf"{NB}{_pat}", None))

TERMS: list[Term] = [Term(c, k, re.compile(p), f) for c, k, p, f in _RAW_TERMS]

# "○○역" 형태의 지역. 사전에 없는 역도 잡는다.
STATION_RE = re.compile(rf"{NB}([{H}A-Za-z]{{1,6}})역(?=$|[^{H}]|에|근처|쪽|앞|으로|이|은|도|부근|인근)")
STATION_STOPWORDS = {"지", "무", "구", "전", "영", "역", "반", "시", "출"}

# ---- 극성 단서 ----
NEG_CUE_RE = re.compile(
    r"싫|못\s?먹|안\s?먹|별로|제외|빼|알레르기|알러지|피하|피해|안\s?땡|질렸|질려|"
    r"안\s?돼|안\s?좋|않|불호|못\s?가|안\s?가|패스|노노|"
    r"안\s?마[시셔]|못\s?마[시셔]|금주"
)
OK_CUE_RE = re.compile(r"괜찮|상관\s?없|아무거나|다\s?좋|무난")

# 절(clause) 나누기: 쉼표·화살표·접속 표현 기준
SPLIT_RE = re.compile(
    rf"[,.!?\n~;/]|→|->|>|그리고|근데|그런데|하지만|그러나|"
    rf"(?<=[{H}])(?:는데|은데|인데|지만)|"
    rf"(?<=[{H}])(?<!말)고(?=\s)(?!\s+싶)"
)
# "A 말고 B": A는 제외, B는 따로 판단
EXCEPT_RE = re.compile(r"말고")

# ---- 인원 ----
KOREAN_NUM = {
    "혼자": 1, "한": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4,
    "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10, "열한": 11, "열두": 12,
}
_NUM = r"\d{1,2}|열한|열두|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열"
PEOPLE_DELTA_PLUS_RE = re.compile(rf"({_NUM})\s*명\s*(?:더|추가)")
PEOPLE_DELTA_MINUS_RE = re.compile(rf"({_NUM})\s*명\s*(?:빠|못\s?와|못\s?온|불참)")
PEOPLE_ABS_RES = [
    re.compile(r"(\d{1,2})\s*(?:명|인(?![분당])(?!\s*\d)|사람)"),
    re.compile(rf"{NB}({_NUM})\s*(?:명|사람)"),
    re.compile(rf"{NB}(둘|셋|넷|다섯|여섯)(?:이서|이|명)"),
    re.compile(rf"{NB}(혼자)"),
]


def to_int(token: str) -> int:
    return int(token) if token.isdigit() else KOREAN_NUM[token]


def find_terms(text: str) -> list[tuple[int, int, Term]]:
    """겹치지 않게 사전 단어를 찾는다. 같은 위치면 더 긴 것이 이긴다."""
    found: list[tuple[int, int, Term]] = []
    for term in TERMS:
        for m in term.pattern.finditer(text):
            if m.end() > m.start():
                found.append((m.start(), m.end(), term))
    for m in STATION_RE.finditer(text):
        base = m.group(1)
        if base in STATION_STOPWORDS:
            continue
        name = base if base in _REGION_NAMES else f"{base}역"
        found.append((m.start(), m.end(), Term(name, "region", STATION_RE)))
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    picked: list[tuple[int, int, Term]] = []
    last_end = -1
    for s, e, t in found:
        if s >= last_end:
            picked.append((s, e, t))
            last_end = e
    return picked


def canonicalize(value: str) -> tuple[str, Optional[str], Optional[str]]:
    """AI가 준 자유 표현을 사전의 표준 이름으로 맞춘다.

    반환: (표준 이름, 종류 또는 None, 강제 극성 또는 None)
    사전에 없는 표현은 그대로 돌려준다.
    """
    value = (value or "").strip()
    terms = find_terms(value)
    if not terms:
        return value, None, None
    _, _, t = terms[0]
    return t.canonical, t.kind, t.force
