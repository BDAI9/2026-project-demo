import unittest
from data_validation.eatpl_adapter import normalize_eatpl_merchant
from data_validation.validation import validate_place


class EatplAdapterTests(unittest.TestCase):
    def test_live_record_never_pretends_to_know_menu_or_capacity(self):
        p = normalize_eatpl_merchant({"merNm": "예시 매장", "addr": "서울 강남구 테헤란로", "merTpbuzNm": "한식음식점", "allSaleRnk": "0.04"}, region_hint="강남")
        self.assertIsNone(p["capacity"])
        self.assertFalse(p["menu_verified"])
        self.assertFalse(p["coordinate_verified"])
        self.assertEqual(p["all_sale_rank_pct"], 0.04)

    def test_estimated_hours_can_wrap_midnight(self):
        p = normalize_eatpl_merchant({"merNm": "예시", "merTpbuzNm": "카페", "srtTime": "1814", "endTime": "0556"})
        self.assertIn("익일 05:56", p["estimated_hours"])

    def test_spoofed_link_discarded(self):
        p = normalize_eatpl_merchant({"merNm": "예시", "merTpbuzNm": "카페", "merUrl": "https://web.paybooc.ai.attacker.test/"})
        self.assertEqual(p["merchant_url"], "")

    def test_unknown_category_kept_unknown_not_guessed(self):
        p = normalize_eatpl_merchant({"merNm": "예시", "merTpbuzNm": "기타"})
        self.assertEqual(p["category"], "")
        self.assertFalse(validate_place(p)["valid"])


if __name__ == "__main__":
    unittest.main()
