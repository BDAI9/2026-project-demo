"""Run the isolated sample recommendation flow: python -m backend.demo."""

from backend.app.providers.mock import sample_places
from backend.app.recommendations.courses import build_courses
from backend.app.recommendations.evaluation import Constraint, evaluate_candidates


def main():
    print("샘플 데이터: 아래 장소와 정보는 모두 가상입니다. 잇플로 이동할 수 없습니다.")
    places = sample_places()
    rules = [Constraint("budget", "participant-a", "price_per_person_krw", "lte", 20000)]
    group = evaluate_candidates(places, rules, party_size=4)
    print("단체 후보:", ", ".join(c.place.name for c in group.eligible))
    print("확인 필요:", ", ".join(c.place.name for c in group.needs_review) or "없음")
    courses = build_courses(places, [], party_size=2, max_leg_distance_m=1500, max_total_per_person_krw=30000)
    for status, options in (("코스", courses.eligible), ("확인 필요", courses.needs_review)):
        for course in options:
            distance = course.legs[0].straight_line_distance_m
            distance_text = f"직선거리 {distance:.0f}m" if distance is not None else "거리 정보 없음"
            print(f"{status}: {' → '.join(p.name for p in course.places)} · {distance_text} · 1인 {course.total_per_person_krw:,.0f}원" if course.total_per_person_krw is not None else f"{status}: {' → '.join(p.name for p in course.places)} · {distance_text} · 가격 정보 없음")


if __name__ == "__main__":
    main()
