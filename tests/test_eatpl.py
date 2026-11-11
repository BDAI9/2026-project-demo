import io
import json
import socket
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from backend.app.providers.eatpl import (
    DEV_URL, EatplAuthenticationError, EatplNetworkError, EatplPlaceProvider,
    EatplResponseError, EatplTimeoutError, map_place,
)


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return self.body[:size]


class EatplTests(unittest.TestCase):
    def setUp(self):
        self.provider = EatplPlaceProvider("partner")
        self.trace = "partner202611100000000001"

    def test_maps_actual_documented_fields_without_inventing_wgs84(self):
        detail = "https://web.paybooc.ai/mer/web/profile/abc_123"
        place = map_place({"merNm": "가게", "merAddr": "서울 중구", "merTpbuzNm": "카페", "merUrl": detail,
                           "xaxsVal": "312345", "yaxsVal": "545678", "allSaleRnk": 0.09})
        self.assertEqual(place.category, "cafe")
        self.assertEqual(place.eatpl_url, detail)
        self.assertEqual(place.attributes["national_sales_percentile"].value, 0.09)
        self.assertIsNone(place.latitude)
        self.assertIsNone(place.longitude)
        self.assertNotIn("price_per_person_krw", place.attributes)

    def test_invalid_detail_links_are_not_enabled(self):
        for url in ("https://web.paybooc.ai.evil.test/mer/web/profile/a", "http://web.paybooc.ai/mer/web/profile/a",
                    "https://web.paybooc.ai/mer/web/profile/a?track=x", "javascript:alert(1)"):
            with self.subTest(url=url):
                self.assertIsNone(map_place({"merNm": "A", "merAddr": "B", "merUrl": url}).eatpl_url)

    def test_unknown_taxonomy_is_not_guessed(self):
        for label in ("기타", "주점", None, ["카페"]):
            self.assertEqual(map_place({"merNm": "A", "merAddr": "B", "merTpbuzNm": label}).category, "unknown")

    @patch("backend.app.providers.eatpl.request.build_opener")
    def test_search_posts_official_envelope_and_empty_is_success(self, opener):
        opener.return_value.open.return_value = FakeResponse({"rspCode": "00000", "data": []})
        self.assertEqual(self.provider.search(trace_number=self.trace, location="서울 종로구", business_type="카페"), [])
        args, kwargs = opener.return_value.open.call_args
        req = args[0]
        self.assertEqual(req.full_url, DEV_URL + "/v1/search")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(json.loads(req.data), {"trnsTrceNo": self.trace, "instNm": "partner", "location": "서울 종로구", "merTpbuzNm": "카페"})
        self.assertEqual(kwargs["timeout"], 10.0)

    @patch("backend.app.providers.eatpl.request.build_opener")
    def test_errors_are_not_empty_results(self, opener):
        for exception, expected in (
            (HTTPError("https://example.invalid", 403, "forbidden", {}, io.BytesIO()), EatplAuthenticationError),
            (HTTPError("https://example.invalid", 500, "error", {}, io.BytesIO()), EatplNetworkError),
            (URLError(socket.timeout()), EatplTimeoutError),
            (URLError("network"), EatplNetworkError),
        ):
            with self.subTest(expected=expected):
                opener.return_value.open.side_effect = exception
                with self.assertRaises(expected):
                    self.provider.search(trace_number=self.trace, location="서울")

    @patch("backend.app.providers.eatpl.request.build_opener")
    def test_semantic_errors_and_invalid_shapes_raise(self, opener):
        for body in ({"rspCode": "99999", "data": []}, {"rspCode": "00000", "data": {}}, []):
            opener.return_value.open.return_value = FakeResponse(body)
            with self.subTest(body=body), self.assertRaises(EatplResponseError):
                self.provider.search(trace_number=self.trace, location="서울")

    def test_rejects_invalid_configuration_and_query_before_network(self):
        with self.assertRaises(ValueError):
            EatplPlaceProvider("partner", base_url="https://evil.test")
        with self.assertRaises(ValueError):
            self.provider.search(trace_number=self.trace)
        with self.assertRaises(ValueError):
            self.provider.search(trace_number="bad", location="서울")


if __name__ == "__main__":
    unittest.main()
