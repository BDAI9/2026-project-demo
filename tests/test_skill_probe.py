import json
import unittest

from backend.app.providers.eatpl import EatplResponseError
from backend.skill_probe import parse_response


class SkillProbeTests(unittest.TestCase):
    def test_proxy_items_map_to_place_and_report_cache(self):
        body = {"upstream": {"status_code": 200}, "proxy": {"cache": {"hit": True}},
                "items": [{"merNm": "테스트 카페", "merAddr": "서울 중구", "merTpbuzNm": "카페",
                           "merUrl": "https://web.paybooc.ai/mer/web/profile/test", "xaxsVal": "311826", "yaxsVal": "551982"}]}
        places, cache = parse_response(json.dumps(body).encode())
        self.assertTrue(cache)
        self.assertEqual(places[0].address, "서울 중구")
        self.assertEqual(places[0].category, "cafe")
        self.assertEqual(places[0].eatpl_url, "https://web.paybooc.ai/mer/web/profile/test")
        self.assertIsNone(places[0].latitude)

    def test_invalid_or_unsuccessful_wrapper_is_not_empty_success(self):
        for body in ({"items": [], "upstream": {"status_code": 503}}, {"data": []}, []):
            with self.subTest(body=body), self.assertRaises(EatplResponseError):
                parse_response(json.dumps(body).encode())


if __name__ == "__main__":
    unittest.main()
