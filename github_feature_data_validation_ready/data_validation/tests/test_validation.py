import unittest
from pathlib import Path

from data_validation.validation import (validate_conditions, validate_place, load_places_csv, evaluate_candidate,
                        filter_places, haversine_km, validate_course, quality_report, is_trusted_eatpl_url)

ROOT = Path(__file__).resolve().parents[1]


class QAContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.places = load_places_csv(ROOT / "data/sample_places.csv")
        cls.by_id = {p["place_id"]: p for p in cls.places}
        requests = json.loads((ROOT / "data/sample_requests.json").read_text(encoding="utf-8"))
        cls.group = validate_conditions(requests["group_ok"])["normalized"]
        cls.date = validate_conditions(requests["date_ok"])["normalized"]

    def test_01_valid_group_input(self):
        self.assertEqual(self.group["party_size"], 4)

    def test_02_invalid_party_size(self):
        self.assertFalse(validate_conditions({"mode": "group", "region": "강남", "party_size": 0})["ok"])

    def test_03_invalid_date_missing_order(self):
        self.assertFalse(validate_conditions({"mode": "date", "region": "홍대", "party_size": 2})["ok"])

    def test_04_pass_safe_group_restaurant(self):
        self.assertEqual(evaluate_candidate(self.by_id["G01"], self.group)["status"], "pass")

    def test_05_reject_spicy(self):
        self.assertEqual(evaluate_candidate(self.by_id["G02"], self.group)["status"], "reject")

    def test_06_reject_seafood(self):
        self.assertEqual(evaluate_candidate(self.by_id["G03"], self.group)["status"], "reject")

    def test_07_reject_too_small_capacity(self):
        self.assertEqual(evaluate_candidate(self.by_id["G04"], self.group)["status"], "reject")

    def test_08_unknown_menu_not_claimed_safe(self):
        self.assertEqual(evaluate_candidate(self.by_id["G05"], self.group)["status"], "needs_verification")

    def test_09_reject_over_budget(self):
        self.assertEqual(evaluate_candidate(self.by_id["G06"], self.group)["status"], "reject")

    def test_10_unknown_capacity_not_claimed_pass(self):
        self.assertEqual(evaluate_candidate(self.by_id["G07"], self.group)["status"], "needs_verification")

    def test_11_group_filter_three_statuses(self):
        result = filter_places(self.places, self.group)
        self.assertEqual({"pass", "reject", "needs_verification"}, set(result))
        self.assertEqual({"G01"}, {p["place_id"] for p in result["pass"]})

    def test_12_haversine_same_spot(self):
        self.assertAlmostEqual(haversine_km(37.55, 126.9, 37.55, 126.9), 0, places=6)

    def test_13_date_course_demo_pass(self):
        r = validate_course(["D01", "D02", "D04"], self.by_id, self.date, allow_demo_coordinates=True)
        self.assertEqual(r["status"], "pass")
        self.assertEqual(len(r["legs"]), 2)

    def test_14_date_course_far_leg_fail(self):
        r = validate_course(["D01", "D02", "D03"], self.by_id, self.date, allow_demo_coordinates=True)
        self.assertEqual(r["status"], "fail")

    def test_15_missing_coordinates_not_pass(self):
        r = validate_course(["D05", "D02", "D04"], self.by_id, self.date, allow_demo_coordinates=True)
        self.assertEqual(r["status"], "needs_verification")

    def test_16_unverified_demo_coordinates_without_demo_flag(self):
        r = validate_course(["D01", "D02", "D04"], self.by_id, self.date)
        self.assertEqual(r["status"], "needs_verification")

    def test_17_duplicate_place_fail(self):
        r = validate_course(["D01", "D01", "D04"], self.by_id, self.date, allow_demo_coordinates=True)
        self.assertEqual(r["status"], "fail")

    def test_18_course_order_fail(self):
        r = validate_course(["D02", "D01", "D04"], self.by_id, self.date, allow_demo_coordinates=True)
        self.assertEqual(r["status"], "fail")

    def test_19_tm128_as_wgs84_fails(self):
        p = dict(self.by_id["G01"], lat_wgs84=198737.4, lon_wgs84=454321.5)
        self.assertFalse(validate_place(p)["valid"])

    def test_20_bad_merchant_url(self):
        self.assertFalse(is_trusted_eatpl_url("https://web.paybooc.ai.evil.example/path"))
        self.assertFalse(is_trusted_eatpl_url("http://web.paybooc.ai/path"))

    def test_21_quality_report_returns_summary(self):
        r = quality_report(self.places)
        self.assertEqual(r["total"], 12)
        self.assertEqual(len(r["invalid_records"]), 0)

    def test_22_missing_tag_evidence_is_unknown(self):
        p = dict(self.by_id["G01"], tags=["조용한"], tags_evidence="")
        c = dict(self.group, required_tags=["조용한"])
        self.assertEqual(evaluate_candidate(p, c)["status"], "needs_verification")

    def test_23_conflicting_area_reject(self):
        self.assertEqual(evaluate_candidate(self.by_id["D01"], self.group)["status"], "reject")


if __name__ == "__main__":
    unittest.main()
