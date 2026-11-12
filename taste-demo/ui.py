import streamlit as st
import data_access as db


def init():
    defaults = {'restaurant': False, 'cafe_bar': False, 'budget': False,
                'min_price': 0, 'max_price': 300000, 'min_slide': 0, 'max_slide': 300000,
                'favorites': set(), 'results': None, 'pair_mode': False, 'page': '검색'}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def toggle_type(key):
    st.session_state[key] = not st.session_state[key]
    if st.session_state.restaurant and st.session_state.cafe_bar:
        st.session_state.budget = False


def sync(source, target):
    st.session_state[target] = st.session_state[source]


def place(p, key):
    name = p.get('name') or '이름 미확인'
    st.markdown(f"**{name}** · {p.get('category') or '분류 미확인'}")
    st.write(p.get('address') or '주소 미확인')
    price, rating = p.get('price'), p.get('rating')
    st.caption(f"1인 예시 가격: {f'{price:,}원' if price is not None else '미확인'} · 평점: {rating if rating is not None else '미확인'}")
    diets = p.get('diets')
    st.caption(f"해산물: {p.get('seafood') or '정보 미확인'} · 특수 식단: {', '.join(diets) if diets else ('없음' if diets == [] else '정보 미확인')} · 와이파이: { {True:'있음', False:'없음', None:'확인되지 않음'}.get(p.get('wifi'), '확인되지 않음')}")
    liked = p['id'] in st.session_state.favorites
    if st.button('♥ 찜 해제' if liked else '♡ 찜', key=key):
        if liked: st.session_state.favorites.remove(p['id'])
        else: st.session_state.favorites.add(p['id'])
        st.rerun()


def render():
    init()
    st.title('🍽️ 한끼산책')
    st.subheader('오늘의 한 끼와 다음 발걸음을 찾아요')
    st.info('모든 가게·주소·가격·평점과 정보는 실제 업체가 아닌 가상 예시입니다.')
    st.radio('화면', ['검색', '공유'], horizontal=True, key='page')
    st.caption('찜은 현재 사용자 세션에만 저장되며 새 세션이나 서버 재시작 후 유지되지 않을 수 있습니다.')
    if st.session_state.page == '공유':
        st.header('공유 ID')
        st.warning('공유 ID와 목록은 현재 서버 메모리에만 저장됩니다. 재시작 시 사라지며 여러 서버 또는 실제 배포 환경에서 안정적인 공유 기능이 아닙니다.')
        selected = [p for p in db.PLACES if p['id'] in st.session_state.favorites]
        st.write(f'현재 찜 {len(selected)}개')
        for p in selected: place(p, 'fav_'+p['id'])
        if st.button('현재 찜으로 공유 ID 생성'):
            try: st.session_state.created_code = db.create_share(st.session_state.favorites)
            except ValueError as e: st.error(str(e))
        if st.session_state.get('created_code'): st.success('생성된 ID: ' + st.session_state.created_code)
        code = st.text_input('7자리 공유 ID 입력', max_chars=7)
        if st.button('공유 목록 조회'):
            try:
                found = db.get_share(code)
                st.session_state.shared = found
                if found is None: st.warning('존재하지 않는 공유 ID입니다.')
            except ValueError as e: st.session_state.shared = None; st.error(str(e))
        for p in st.session_state.get('shared') or []: place(p, 'shared_'+p['id'])
        return
    query = st.text_input('지역명 또는 가게 이름', placeholder='예: 예시구, 달빛밥상')
    a,b,c = st.columns(3)
    a.button('식당', type='primary' if st.session_state.restaurant else 'secondary', on_click=toggle_type, args=('restaurant',), use_container_width=True)
    b.button('카페/바', type='primary' if st.session_state.cafe_bar else 'secondary', on_click=toggle_type, args=('cafe_bar',), use_container_width=True)
    both = st.session_state.restaurant and st.session_state.cafe_bar
    c.button('예산', type='primary' if st.session_state.budget else 'secondary', disabled=both, on_click=toggle_type, args=('budget',), use_container_width=True)
    if both: st.caption('식당과 카페/바를 함께 선택하면 예산을 적용할 수 없습니다.')
    if st.session_state.budget:
        st.caption('가게의 1인 기준 예시 가격입니다.')
        st.slider('최소 금액 슬라이더', 0, 300000, step=1, key='min_slide', on_change=sync, args=('min_slide','min_price'))
        st.number_input('최소 금액(원)', 0, 300000, step=1, key='min_price', on_change=sync, args=('min_price','min_slide'))
        st.slider('최대 금액 슬라이더', 0, 300000, step=1, key='max_slide', on_change=sync, args=('max_slide','max_price'))
        st.number_input('최대 금액(원)', 0, 300000, step=1, key='max_price', on_change=sync, args=('max_price','max_slide'))
        if st.session_state.min_price > st.session_state.max_price: st.error('최솟값은 최댓값보다 클 수 없습니다.')
    cats = []
    seafood = False
    diets = []
    if st.session_state.restaurant:
        st.caption('식당 카테고리')
        cats += [x for x in db.CATEGORIES if st.checkbox(x, value=True, key='cat_'+x)]
        st.caption('알레르기')
        seafood = st.checkbox('해산물 알레르기 (정보상 해산물 없음만 포함)')
        st.caption('특수 식단')
        diets = [x for x in ['비건','할랄'] if st.checkbox(x)]
    if st.session_state.cafe_bar:
        st.caption('카페/바 카테고리')
        cats += [x for x in ['카페','바'] if st.checkbox(x, value=x=='카페', key='cat_'+x)]
    distance = 100
    if both:
        distance = st.selectbox('식당–카페/바 최대 거리', [100,200,500,1000], format_func=lambda x: f'{x:,}m')
        st.caption('가상 좌표 간 직선거리이며 실제 도보 거리와 다릅니다.')
    if st.button('검색', type='primary'):
        if not (st.session_state.restaurant or st.session_state.cafe_bar): st.error('식당 또는 카페/바를 선택해 주세요.')
        elif st.session_state.budget and st.session_state.min_price > st.session_state.max_price: st.error('예산 범위를 확인해 주세요.')
        else:
            types = [x for x in ['restaurant','cafe_bar'] if st.session_state[x]]
            if both: results = db.search_pairs(query, cats, seafood, diets, distance)
            else: results = db.search_places(query, types, cats, seafood, diets, (st.session_state.min_price,st.session_state.max_price) if st.session_state.budget else None)
            st.session_state.results, st.session_state.pair_mode = results[:20], both
    results = st.session_state.results
    if results is not None:
        st.header('검색 결과')
        if not results: st.info('조건에 맞는 결과가 없습니다. 검색어나 필터를 바꿔 보세요.')
        elif len(results)<3: st.info(f'조건에 맞는 결과가 {len(results)}개뿐입니다.')
        for i, item in enumerate(results,1):
            st.markdown(f'### {i}위')
            if st.session_state.pair_mode:
                st.caption(f"조합 평균 평점 {item['rating']:.2f} · 직선거리 {item['distance_m']}m")
                place(item['restaurant'], f'r{i}'); place(item['cafe_bar'], f'c{i}')
            else: place(item, f'p{i}')
            st.divider()

