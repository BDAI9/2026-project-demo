"""Create QA scenario results for fictional 30-place Eatpl MVP fixture.

Usage (from a folder containing validation.py, 30-place CSV, and requests JSON):
  python run_test_scenarios.py sample_places_v2_30.csv sample_user_requests.json

This checks input contract, reference candidate statuses, and example course QA.
It DOES NOT test AI extraction, real Eatpl, or real walking-distance accuracy.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

# If validation.py is in the same folder as the script, add that folder to module lookup.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validation import load_places_csv, validate_conditions, filter_places, evaluate_candidate, validate_course

# Hand-authored expectations on the unchanged 30-row fictional demo fixture.
BASELINE = {
    "T01": {"counts": (2, 4, 24), "target": ("G01", "pass"), "second": ("G02", "reject"), "why": "매운 음식·해산물 제외: 확인된 안전 식당만 통과"},
    "T02": {"counts": (4, 2, 24), "target": ("G04", "reject"), "why": "8명 요청에서 수용 2명인 식당 제외"},
    "T03": {"counts": (8, 2, 20), "target": ("G11", "reject"), "why": "해산물 취급 식당 제외"},
    "T04": {"counts": (0, 0, 30), "why": "양식과 이탈리안은 현재 정확한 문자열 비교에서 다른 음식 유형"},
    "T05": {"counts": (7, 3, 20), "target": ("G09", "needs_verification"), "why": "조용한 분위기가 증명되지 않은 장소는 추가 확인"},
    "T06": {"counts": (0, 1, 29), "target": ("G09", "reject"), "why": "20명 조건에서 수용인원 미달 장소 제외"},
    "T07": {"counts": (11, 0, 19), "course": ["D01", "D02"], "why": "카페→식당 업종 순서와 미검증 좌표"},
    "T08": {"counts": (14, 1, 15), "course": ["D01", "D02", "D14"], "why": "카페→식당→술집 업종 순서와 미검증 좌표"},
    "T09": {"counts": (10, 3, 17), "course": ["G01", "G13"], "why": "강남 식당→카페 코스, 미검증 좌표"},
    "T10": {"counts": (11, 0, 19), "course": ["D01", "D02"], "why": "0.5km 한도라도 실제 검증되지 않은 좌표로 확정하면 안 됨"},
    "T11": {"why": "0명은 유효하지 않은 사용자 조건"},
    "T12": {"why": "데이트 모드에서 한 장소만 제시하면 입력 규격 위반"},
}

COLUMNS = ["test_id", "scenario", "expected_behavior", "expected_validation_ok", "actual_validation_ok", "actual_pass", "actual_needs_verification", "actual_reject", "checked_place", "actual_place_status", "example_course_ids", "actual_course_status", "test_result", "finding_or_followup"]


def execute(places_path: str, requests_path: str, output_path: str) -> list[dict]:
    places = load_places_csv(places_path)
    if len(places) != 30:
        raise ValueError("이 시나리오 결과는 기존 30개 가상 장소 데이터만을 기준으로 합니다.")
    by_id = {place["place_id"]: place for place in places}
    with open(requests_path, encoding="utf-8-sig") as fh:
        requests = json.load(fh)
    ids = [s["test_id"] for s in requests]
    if sorted(ids) != sorted(BASELINE):
        raise ValueError(f"입력 JSON의 테스트 ID가 예상한 T01~T12와 다릅니다: {ids}")

    rows = []
    for request in requests:
        test_id = request["test_id"]
        baseline = BASELINE[test_id]
        expected_ok = request["expected_validation_ok"]
        checked = validate_conditions(request["expected_conditions"])
        ok = checked["ok"] == expected_ok
        counts = ("", "", "")
        target_status, checked_place, course_status, course_ids = "", "", "", ""
        findings = []

        if checked["ok"]:
            groups = filter_places(places, checked["normalized"])
            counts = tuple(len(groups[k]) for k in ("pass", "needs_verification", "reject"))
            if "counts" in baseline and counts != baseline["counts"]:
                ok = False
                findings.append(f"기대 분류 건수 {baseline['counts']} vs 실제 {counts}")
            for field in ("target", "second"):
                if field in baseline:
                    pid, expected_status = baseline[field]
                    actual = evaluate_candidate(by_id[pid], checked["normalized"])["status"]
                    if field == "target":
                        checked_place, target_status = pid, actual
                    if actual != expected_status:
                        ok = False
                        findings.append(f"{pid}: 기대 {expected_status}, 실제 {actual}")
            if baseline.get("course"):
                course_ids = " → ".join(baseline["course"])
                course = validate_course(baseline["course"], by_id, checked["normalized"])
                course_status = course["status"]
                if course_status != "needs_verification":
                    ok = False
                    findings.append(f"예시 코스: 좌표 미검증인데 상태가 {course_status}로 나옴")
                if course["unknown"]:
                    findings.append(" / ".join(course["unknown"]))
        elif expected_ok:
            findings.append("유효해야 할 입력이 거부됨: " + "; ".join(checked["errors"]))
        else:
            findings.append("입력 거부 사유: " + "; ".join(checked["errors"]))

        if not findings:
            findings.append(baseline["why"])
        rows.append({
            "test_id": test_id,
            "scenario": request["user_input"],
            "expected_behavior": baseline["why"],
            "expected_validation_ok": expected_ok,
            "actual_validation_ok": checked["ok"],
            "actual_pass": counts[0],
            "actual_needs_verification": counts[1],
            "actual_reject": counts[2],
            "checked_place": checked_place,
            "actual_place_status": target_status,
            "example_course_ids": course_ids,
            "actual_course_status": course_status,
            "test_result": "PASS" if ok else "FAIL",
            "finding_or_followup": "; ".join(findings),
        })

    # 3 edge cases that independently check critical user-facing safety behavior.
    t10 = next(x for x in requests if x['test_id'] == 'T10')["expected_conditions"]
    t10 = validate_conditions(t10)["normalized"]
    edge_checks = [
        ("T13", "홍대 카페→식당 코스: 카페 좌표 누락", "D10 → D02의 좌표가 없으면 코스는 추가 확인", "D10 → D02", "needs_verification", validate_course(["D10", "D02"], by_id, t10)["status"]),
    ]
    t01 = next(x for x in requests if x['test_id'] == 'T01')["expected_conditions"]
    t01 = validate_conditions(t01)["normalized"]
    t03 = next(x for x in requests if x['test_id'] == 'T03')["expected_conditions"]
    t03 = validate_conditions(t03)["normalized"]
    edge_checks += [
        ("T14", "강남 메뉴 미확인 식당 G05에 매운·해산물 제외 조건 적용", "메뉴 안전 근거가 없으면 추가 확인", "G05", "needs_verification", evaluate_candidate(by_id["G05"], t01)["status"]),
        ("T15", "강남 해물 칼국수 G11에 해산물 제외 조건 적용", "해산물 포함이 확인되면 제외", "G11", "reject", evaluate_candidate(by_id["G11"], t03)["status"]),
    ]
    for test_id, scenario, expected, target, expected_status, actual in edge_checks:
        rows.append({
            "test_id": test_id,
            "scenario": scenario,
            "expected_behavior": expected,
            "expected_validation_ok": "",
            "actual_validation_ok": "",
            "actual_pass": "",
            "actual_needs_verification": "",
            "actual_reject": "",
            "checked_place": target,
            "actual_place_status": actual if test_id in ("T14", "T15") else "",
            "example_course_ids": target if test_id == "T13" else "",
            "actual_course_status": actual if test_id == "T13" else "",
            "test_result": "PASS" if actual == expected_status else "FAIL",
            "finding_or_followup": "실데이터 교체 시 근거를 재확인해야 함",
        })

    with open(output_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("places", help="sample_places_v2_30.csv 경로")
    parser.add_argument("requests", help="sample_user_requests.json 경로")
    parser.add_argument("--output", default="test_scenarios_15.csv")
    args = parser.parse_args()
    rows = execute(args.places, args.requests, args.output)
    print(f"총 {len(rows)}개 테스트: PASS {sum(row['test_result']=='PASS' for row in rows)}, FAIL {sum(row['test_result']=='FAIL' for row in rows)}")
    print("결과 저장:", args.output)
    print("※ 가상 데이터 검증 결과이며 AI 추출/API/실제 도보 경로 검증이 아닙니다.")


if __name__ == "__main__":
    main()
