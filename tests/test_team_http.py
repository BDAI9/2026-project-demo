"""Cross-module HTTP smoke tests for the local team integration demo."""

import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from backend.server import Handler


class TeamHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request_json(self, path, payload):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request("POST", path, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                         {"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_text_to_confirmed_group_filter(self):
        status, data = self.request_json("/api/interpret", {
            "text": "강남에서 4명, 해산물 제외", "product_mode": "group"})
        self.assertEqual(status, 200)
        self.assertEqual(data["proposal"]["region"], "강남")
        self.assertEqual(data["proposal"]["people"], 4)
        self.assertIn("해산물", data["proposal"]["exclusions"])
        request = {"product_mode": "group", "source": "sample", "region": "강남",
                   "party_size": 4, "excluded_terms": ["해산물"], "preferred_cuisines": [],
                   "required_tags": [], "category_order": [], "max_budget_per_person": None,
                   "max_leg_distance_m": None, "confirmed": True}
        status, result = self.request_json("/api/team-search", request)
        self.assertEqual(status, 200)
        self.assertEqual(result["source"], "sample")
        self.assertTrue(result["candidates"])
        self.assertTrue(any(c["status"] == "reject" for c in result["candidates"]))
        self.assertTrue(all(not c.get("eatpl_url") for c in result["candidates"]))

    def test_confirmation_required_and_unknown_fields_rejected(self):
        payload = {"product_mode": "group", "source": "sample", "region": "강남",
                   "party_size": 4, "excluded_terms": [], "preferred_cuisines": [],
                   "required_tags": [], "category_order": [], "max_budget_per_person": None,
                   "max_leg_distance_m": None, "confirmed": False}
        self.assertEqual(self.request_json("/api/team-search", payload)[0], 400)
        payload["confirmed"] = True
        payload["ignored_important_constraint"] = "알레르기"
        self.assertEqual(self.request_json("/api/team-search", payload)[0], 400)


if __name__ == "__main__":
    unittest.main()
