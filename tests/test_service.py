import json
import os
import tempfile
import threading
import unittest
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from backend.app.providers.eatpl import EatplAuthenticationError, EatplTimeoutError, map_place
from backend.app.service import next_trace_number, search_courses
from backend.server import Handler


class Provider:
    def __init__(self, places=None, failure=None):
        self.places, self.failure, self.calls = places or [], failure, []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return self.places


def payload(**kwargs):
    return {"mode": "eatpl", "region": "서울 중구", "order": ["cafe", "restaurant"], **kwargs}


class ServiceTests(unittest.TestCase):
    def test_official_response_to_courses_and_conditions(self):
        cafe = map_place({"merNm": "카페", "merAddr": "서울 중구", "merTpbuzNm": "카페", "merUrl": "https://web.paybooc.ai/mer/web/profile/abc"})
        restaurant = map_place({"merNm": "식당", "merAddr": "서울 중구", "merTpbuzNm": "고기구이", "merUrl": "https://web.paybooc.ai/mer/web/profile/def"})
        provider = Provider([cafe, restaurant])
        result = search_courses(payload(max_leg_distance_m=500, max_total_per_person_krw=30000), provider=provider, trace_factory=lambda: "trace")
        self.assertEqual(provider.calls, [{"trace_number": "trace", "location": "서울 중구"}])
        self.assertEqual(result["status"], "ok")
        course = result["courses"][0]
        self.assertEqual(course["status"], "needs_review")
        self.assertIsNone(course["distance_m"])
        self.assertIsNone(course["total_per_person_krw"])
        self.assertEqual(course["places"][0]["eatpl_url"], "https://web.paybooc.ai/mer/web/profile/abc")
        self.assertTrue(any("거리" in reason for reason in course["reasons"]))
        self.assertTrue(any("예산" in reason for reason in course["reasons"]))

    def test_empty_errors_and_no_silent_sample(self):
        self.assertEqual(search_courses(payload(), provider=Provider(), trace_factory=lambda: "trace")["status"], "empty")
        for error, message in [(EatplAuthenticationError(), "인증"), (EatplTimeoutError(), "시간")]:
            result = search_courses(payload(), provider=Provider(failure=error), trace_factory=lambda: "trace")
            self.assertEqual(result["source"], "eatpl")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["courses"], [])
            self.assertIn(message, result["message"])

    def test_sample_and_invalid_input(self):
        result = search_courses(payload(mode="sample", region="가상 지역", order=["restaurant", "cafe"]))
        self.assertEqual(result["source"], "mock")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["courses"][0]["places"][0]["name"].startswith("샘플 식당"))
        self.assertEqual(search_courses(payload(mode="sample", region="다른 지역"))["status"], "empty")
        for values in ({"region": ""}, {"mode": "invalid"}, {"order": ["cafe"]}, {"max_leg_distance_m": float("nan")}, {"max_total_per_person_krw": -1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                search_courses(payload(**values))

    def test_normalized_conditions_reach_course_evaluation(self):
        base = {"mode": "sample", "region": "가상 지역", "order": ["cafe", "restaurant"]}
        quiet_cafe = {"id": "quiet", "owner_id": "a", "field": "quiet", "operator": "eq", "value": True,
                      "scope": "stop", "stop_index": 0}
        result = search_courses({**base, "constraints": [quiet_cafe]})
        self.assertEqual(result["status"], "ok")
        self.assertTrue(all(course["places"][0]["name"] == "샘플 카페 A" for course in result["courses"]))
        allergy = {"id": "allergy", "owner_id": "b", "field": "ingredients", "operator": "excludes", "value": "해산물"}
        result = search_courses({**base, "constraints": [allergy]})
        self.assertTrue(result["courses"])
        self.assertTrue(all(course["status"] == "needs_review" for course in result["courses"]))
        inactive = {**quiet_cafe, "active": False}
        result = search_courses({**base, "constraints": [inactive]})
        self.assertTrue(any(course["places"][0]["name"] == "샘플 카페 B" for course in result["courses"]))

    def test_invalid_or_unsupported_conditions_never_disappear_silently(self):
        constraint = {"id": "1", "owner_id": "a", "field": "price_per_person_krw", "operator": "lte", "value": 10000}
        invalid = [
            {"unexpected": True}, {"constraints": {}}, {"constraints": [constraint] * 51},
            {"constraints": [{**constraint, "unsupported": True}]},
            {"constraints": [{**constraint, "value": float("nan")}]},
            {"constraints": [{**constraint, "value": 10**400}]},
            {"constraints": [{**constraint, "value": [10000]}]},
            {"constraints": [{**constraint, "value": True}]},
            {"constraints": [{**constraint, "scope": "stop", "stop_index": True}]},
            {"constraints": [{**constraint, "scope": "stop", "stop_index": 2}]},
            {"constraints": [{**constraint, "active": "false"}]},
            {"constraints": [constraint, constraint]},
            {"constraints": [{"field": "quiet"}]},
            {"max_total_per_person_krw": 10**400},
        ]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                search_courses(payload(mode="sample", region="가상 지역", **fields))

    def test_result_limit_warning_and_no_credentials(self):
        place = map_place({"merNm": "가게", "merAddr": "주소", "merTpbuzNm": "카페"})
        result = search_courses(payload(), provider=Provider([place] * 100), trace_factory=lambda: "trace")
        self.assertTrue(result["truncated"])
        with patch.dict(os.environ, {"EATPL_INSTITUTION": ""}):
            result = search_courses(payload())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["source"], "eatpl")

    def test_trace_sequence_is_durable_and_concurrent(self):
        with tempfile.TemporaryDirectory() as path:
            db = os.path.join(path, "traces.sqlite")
            with ThreadPoolExecutor(max_workers=8) as pool:
                values = list(pool.map(lambda _: next_trace_number("partner", db), range(32)))
            self.assertEqual(len(set(values)), 32)
            self.assertTrue(all(value.startswith("partner") and len(value) == len("partner") + 18 for value in values))
            self.assertNotIn(next_trace_number("partner", db), values)

    def test_http_endpoint_and_cross_origin_rejection(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            body = json.dumps(payload(mode="sample", region="가상 지역")).encode()
            conn.request("POST", "/api/search", body, {"Content-Type": "application/json"})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["status"], "ok")
            malformed = json.dumps(payload(mode="sample", region="가상 지역", max_leg_distance_m=10**400)).encode()
            conn.request("POST", "/api/search", malformed, {"Content-Type": "application/json"})
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            ignored = json.dumps(payload(mode="sample", region="가상 지역", allergy="해산물")).encode()
            conn.request("POST", "/api/search", ignored, {"Content-Type": "application/json"})
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            conn.request("POST", "/api/search", body, {"Content-Type": "application/json", "Origin": "https://other.example"})
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_http_actual_provider_path_with_mocked_official_response(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size):
                return json.dumps({"rspCode": "00000", "data": [
                    {"merNm": "카페", "merAddr": "서울 중구", "merTpbuzNm": "카페", "merUrl": "https://web.paybooc.ai/mer/web/profile/cafe"},
                    {"merNm": "식당", "merAddr": "서울 중구", "merTpbuzNm": "고기구이", "merUrl": "https://web.paybooc.ai/mer/web/profile/restaurant"},
                ]}, ensure_ascii=False).encode()
        with tempfile.TemporaryDirectory() as path, patch.dict(os.environ, {"EATPL_INSTITUTION": "partner", "EATPL_ENV": "dev", "EATPL_TRACE_DB": os.path.join(path, "trace.sqlite")}), patch("backend.app.providers.eatpl.request.build_opener") as opener:
            opener.return_value.open.return_value = Response()
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.request("POST", "/api/search", json.dumps(payload(max_leg_distance_m=700)).encode(), {"Content-Type": "application/json"})
                response = conn.getresponse()
                result = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(result["source"], "eatpl")
                self.assertEqual(result["courses"][0]["status"], "needs_review")
                self.assertEqual(result["courses"][0]["places"][0]["eatpl_url"], "https://web.paybooc.ai/mer/web/profile/cafe")
                provider_request = opener.return_value.open.call_args.args[0]
                submitted = json.loads(provider_request.data)
                self.assertEqual(submitted["location"], "서울 중구")
                self.assertEqual(submitted["instNm"], "partner")
                conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    @patch("backend.skill_probe.urlopen")
    def test_skill_test_mode_makes_one_request_and_preserves_actual_links(self, opener):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size):
                return json.dumps({"upstream": {"status_code": 200}, "proxy": {"cache": {"hit": True}},
                    "items": [{"merNm": "가게", "merAddr": "서울 중구", "merTpbuzNm": "카페",
                               "merUrl": "https://web.paybooc.ai/mer/web/profile/original"}]}, ensure_ascii=False).encode()
        opener.return_value = Response()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST", "/api/search", json.dumps(payload(mode="skill-test")).encode(), {"Content-Type": "application/json"})
            response = conn.getresponse()
            result = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(result["source"], "skill-test")
            self.assertEqual(result["status"], "empty")  # One cafe is not a course.
            self.assertTrue(result["cache_hit"])
            self.assertEqual(result["place_options"][0]["eatpl_url"], "https://web.paybooc.ai/mer/web/profile/original")
            opener.assert_called_once()
            proxy_request = opener.call_args.args[0]
            self.assertEqual(proxy_request.get_method(), "GET")
            self.assertEqual(parse_qs(urlsplit(proxy_request.full_url).query), {"location": ["서울 중구"]})
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    @patch("backend.skill_probe.urlopen", side_effect=URLError("offline"))
    def test_skill_failure_does_not_fall_back_to_sample(self, opener):
        result = search_courses(payload(mode="skill-test"))
        self.assertEqual(result["source"], "skill-test")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["courses"], [])
        self.assertIn("실패", result["message"])
        opener.assert_called_once()


if __name__ == "__main__":
    unittest.main()
