import unittest

from backend.app.providers.eatpl import map_place
from backend.app.providers.models import Fact, Place
from backend.app.providers.team_contract import to_team_place


class TeamContractTests(unittest.TestCase):
    def test_region_hint_requires_literal_address_match(self):
        place = map_place({"merNm": "가게", "merAddr": "서울 중구 을지로 1", "merTpbuzNm": "카페"})
        self.assertEqual(to_team_place(place)["region"], "")
        self.assertEqual(to_team_place(place, region_hint=" 서울 중구 ")["region"], "서울 중구")
        self.assertEqual(to_team_place(place, region_hint="강남역")["region"], "")
        self.assertEqual(to_team_place(place, region_hint="")["region"], "")
        with self.assertRaises(ValueError):
            to_team_place(place, region_hint=2)

    def test_region_fact_takes_precedence_when_verified_against_address(self):
        place = Place("id", "가게", "cafe", address="서울 중구 을지로 1", source="eatpl",
                      attributes={"region": Fact("서울 중구", "confirmed")})
        self.assertEqual(to_team_place(place, region_hint="을지로")["region"], "서울 중구")
        unknown = Place("id", "가게", "cafe", address="서울 중구 을지로 1", source="eatpl",
                        attributes={"region": Fact("강남", "confirmed")})
        self.assertEqual(to_team_place(unknown, region_hint="서울 중구")["region"], "서울 중구")

    def test_official_address_rank_link_and_unknown_fields(self):
        row = {"merNm": "가게", "merAddr": "서울 중구 을지로 1", "merTpbuzNm": "고기구이",
               "merUrl": "https://web.paybooc.ai/mer/web/profile/a1", "allSaleRnk": 0.04,
               "ccgSaleRnk": 3.25, "srtTime": "1830", "endTime": "0145",
               "xaxsVal": "311826", "yaxsVal": "551982"}
        result = to_team_place(map_place(row))
        self.assertEqual(result["address"], row["merAddr"])
        self.assertEqual(result["merchant_url"], row["merUrl"])
        self.assertEqual(result["all_sale_rank_pct"], 0.04)
        self.assertEqual(result["_extra"]["ccg_sale_rank_pct"], 3.25)
        self.assertEqual(result["_extra"]["raw_kind"], "고기구이")
        self.assertEqual(result["estimated_hours"], "예상 18:30–익일 01:45 (공식 영업시간 아님)")
        self.assertFalse(result["coordinate_verified"])
        self.assertIsNone(result["lat_wgs84"])
        self.assertIsNone(result["lon_wgs84"])
        self.assertIsNone(result["price_per_person_krw"])
        self.assertEqual(result["safe_for_terms"], [])
        self.assertFalse(result["menu_verified"])

    def test_sample_not_mistaken_for_actual_and_no_unverified_coordinates(self):
        place = Place("sample", "가상", "cafe", address="가상 지역", latitude=37.5, longitude=127.0,
                      eatpl_url="https://web.paybooc.ai/mer/web/profile/a", source="mock",
                      attributes={"region": Fact("가상 지역", "mock"), "price_per_person_krw": Fact(7000, "mock"),
                                  "capacity": Fact(4, "mock"), "quiet": Fact(True, "mock")})
        result = to_team_place(place)
        self.assertEqual(result["source"], "demo")
        self.assertTrue(result["is_demo"])
        self.assertEqual(result["region"], "가상 지역")
        self.assertEqual(result["price_per_person_krw"], 7000)
        self.assertEqual(result["capacity"], 4)
        self.assertEqual(result["merchant_url"], "")
        self.assertIsNone(result["lat_wgs84"])
        self.assertFalse(result["coordinate_verified"])
        self.assertEqual(result["tags"], [])

    def test_invalid_data_is_not_promoted_to_verified(self):
        place = Place("id", "가게", "unknown", address="서울 강남구", source="eatpl",
                      eatpl_url="https://web.paybooc.ai/mer/web/profile/a?tracking=1", attributes={
                          "region": Fact("서초", "test"), "price_per_person_krw": Fact(-1, "test"),
                          "capacity": Fact(True, "test"), "national_sales_percentile": Fact(101, "test"),
                          "estimated_open_time": Fact("2460", "test"), "estimated_close_time": Fact("1400", "test")})
        result = to_team_place(place)
        self.assertEqual(result["region"], "")
        self.assertEqual(result["category"], "")
        self.assertIsNone(result["price_per_person_krw"])
        self.assertIsNone(result["capacity"])
        self.assertIsNone(result["all_sale_rank_pct"])
        self.assertEqual(result["estimated_hours"], "")
        self.assertEqual(result["merchant_url"], "")

    def test_absent_source_and_unknown_place_source(self):
        place = Place("id", "가게", "bar", source="eatpl", attributes={
            "price_per_person_krw": Fact(20000, ""), "capacity": Fact(4, "")})
        result = to_team_place(place)
        self.assertEqual(result["category"], "bar")
        self.assertIsNone(result["price_per_person_krw"])
        self.assertIsNone(result["capacity"])
        with self.assertRaises(ValueError):
            to_team_place(Place("id", "가게", "cafe", source="unknown"))


if __name__ == "__main__":
    unittest.main()
