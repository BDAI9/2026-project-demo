"""데모용 가게와 검색/공유 저장소. 실제 매장이 아닙니다."""
from math import asin, cos, radians, sin, sqrt
from secrets import choice
from string import ascii_uppercase, digits
from threading import Lock

CATEGORIES = ['한식', '중식', '일식', '양식', '아시안', '퓨전']
_NAMES = ['달빛밥상', '구름반점', '푸른초밥', '노을키친', '바람식탁', '별빛부엌',
          '모래카페', '달콩카페', '푸른바', '별모퉁이']

def _make(i, name):
    restaurant = i < 6
    return dict(id=f'place-{i+1:02}', name=name, type='restaurant' if restaurant else 'cafe_bar',
                category=CATEGORIES[i] if restaurant else ['카페', '카페', '바', '카페'][i-6],
                address=f'서울 예시구 가상로 {10+i} (가상 주소)',
                lat=37.5 + i * 0.00015, lon=127.0 + i * 0.0001,
                price=[12000,15000,22000,25000,13000,19000,6500,7000,16000,8000][i],
                rating=[4.7,4.5,4.8,4.4,4.3,4.6,4.7,4.5,4.8,4.2][i],
                seafood=['없음','포함','정보 미확인'][i % 3],
                diets=[['비건'], [], ['할랄'], None][i % 4],
                wifi=[True, False, None][i % 3])

PLACES = [_make(i, n) for i, n in enumerate(_NAMES)]
_SHARES = {}
_LOCK = Lock()

def search_places(query='', types=None, categories=None, seafood_free=False, diets=None, budget=None):
    """검색어는 이름 또는 주소의 부분 문자열. 알 수 없는 정보는 안전하다고 간주하지 않음."""
    types = set(types if types is not None else ['restaurant', 'cafe_bar'])
    categories = set(categories if categories is not None else CATEGORIES + ['카페', '바'])
    diets = set(diets or [])
    q = query.strip().casefold()
    result = []
    for p in PLACES:
        if p['type'] not in types or p['category'] not in categories:
            continue
        if q and q not in (p['name'] + ' ' + p['address']).casefold():
            continue
        if p['type'] == 'restaurant':
            if seafood_free and p['seafood'] != '없음':
                continue
            if not diets.issubset(set(p['diets'] or [])):
                continue
        if budget is not None and not budget[0] <= p['price'] <= budget[1]:
            continue
        result.append(p.copy())
    return sorted(result, key=lambda p: (-p['rating'], p['name']))

def distance_m(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (a['lat'], a['lon'], b['lat'], b['lon']))
    h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 12742000 * asin(sqrt(min(1, h)))

def search_pairs(query='', categories=None, seafood_free=False, diets=None, max_distance=100):
    # 검색어는 조합의 어느 한 장소에 일치하면 됨.
    all_places = search_places(categories=categories, seafood_free=seafood_free, diets=diets)
    restaurants = [p for p in all_places if p['type'] == 'restaurant']
    cafes = [p for p in all_places if p['type'] == 'cafe_bar']
    q = query.strip().casefold()
    pairs = []
    for a in restaurants:
        for b in cafes:
            distance = distance_m(a, b)
            if distance <= max_distance and (not q or any(q in (p['name'] + ' ' + p['address']).casefold() for p in (a,b))):
                pairs.append({'restaurant': a, 'cafe_bar': b, 'distance_m': round(distance), 'rating': (a['rating']+b['rating'])/2})
    return sorted(pairs, key=lambda p: (-p['rating'], p['restaurant']['name'], p['cafe_bar']['name']))

def create_share(ids):
    known = {p['id'] for p in PLACES}
    ids = list(dict.fromkeys(ids))
    if not ids or not set(ids) <= known:
        raise ValueError('찜 목록이 비었거나 알 수 없는 가게가 있습니다.')
    with _LOCK:
        while True:
            code = ''.join(choice(ascii_uppercase + digits) for _ in range(7))
            if code not in _SHARES:
                _SHARES[code] = ids
                return code

def get_share(code):
    code = code.strip().upper()
    if len(code) != 7 or any(c not in ascii_uppercase + digits for c in code):
        raise ValueError('공유 ID는 영문 대문자와 숫자로 된 7자리입니다.')
    with _LOCK:
        ids = _SHARES.get(code)
        if ids is None:
            return None
        return [p.copy() for p in PLACES if p['id'] in ids]
