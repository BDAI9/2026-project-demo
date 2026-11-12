import unittest
from unittest.mock import patch

from backend.app.providers.eatpl import map_place
from backend.app.team_integration import _SAMPLES, interpret, recommend
from github_feature_data_validation_ready.data_validation import validation


def request(**changes):
    values = {
        "product_mode": "group", "source": "sample", "region": "강남", "party_size": 4,
        "excluded_terms": [], "preferred_cuisines": [], "required_tags": [],
        "category_order": [], "max_budget_per_person": None, "max_leg_distance_m": None,
        "confirmed": True,
    }
    values.update(changes)
    return values


class TeamIntegrationTests(unittest.TestCase):
    def test_interpret_proposes_and_requires_confirmation(self):
        proposed = interpret({"text": "강남에서 4명, 해산물 제외", "product_mode": "group"})
        self.assertEqual(proposed["status"], "ok")
        self.assertEqual(proposed["proposal"]["people"], 4)
        self.assertEqual(proposed["proposal"]["source"], "rule")
        with self.assertRaises(ValueError):
            recommend(request(confirmed=False))
        with self.assertRaises(ValueError):
            interpret({"text": "조건", "product_mode": "group", "unexpected": True})

    def test_sample_uses_team_validation_and_preserves_unknown(self):
        result = recommend(request(excluded_terms=["매운", "해산물"]))
        decisions = {c["id"]: c for c in result["candidates"]}
        self.assertEqual(result["status"], "ok")
        self.assertEqual(decisions["G01"]["status"], "pass")
        self.assertEqual(decisions["G02"]["status"], "reject")
        self.assertEqual(decisions["G03"]["status"], "reject")
        self.assertEqual(decisions["G04"]["status"], "reject")
        self.assertEqual(decisions["G05"]["status"], "needs_verification")
        self.assertTrue(all(c["eatpl_url"] is None for c in result["candidates"]))
        self.assertIn("가상", result["message"])

    def test_preference_is_ranking_only_and_budget_is_per_person(self):
        plain = recommend(request())
        preferred = recommend(request(preferred_cuisines=["한식"]))
        self.assertEqual({c["id"]: c["status"] for c in plain["candidates"]},
                         {c["id"]: c["status"] for c in preferred["candidates"]})
        self.assertIn("우선", preferred["message"])
        budget = {c["id"]: c for c in recommend(request(max_budget_per_person=18000))["candidates"]}
        self.assertEqual(budget["G01"]["status"], "reject")
        self.assertEqual(budget["G02"]["status"], "pass")

    def test_no_distance_default_and_explicit_distance_limit(self):
        samples = validation.load_places_csv(_SAMPLES)
        sample = [dict(p) for p in samples if p["place_id"] in ("G01", "G13")]
        next(p for p in sample if p["place_id"] == "G13")["lat_wgs84"] += 0.03
        args = request(product_mode="date", party_size=2, category_order=["cafe", "restaurant"])
        with patch("backend.app.team_integration.validation.load_places_csv", return_value=sample):
            unlimited = recommend(args)
            limited = recommend({**args, "max_leg_distance_m": 1500})
        self.assertEqual(unlimited["status"], "ok")
        self.assertGreater(unlimited["courses"][0]["distance_m"], 1500)
        self.assertEqual(limited["status"], "empty")
        self.assertEqual(limited["courses"], [])

    def test_skill_call_once_unknowns_and_links(self):
        places = [map_place({"merNm": "카페", "merAddr": "서울 강남", "merTpbuzNm": "카페",
                             "merUrl": "https://web.paybooc.ai/mer/web/profile/cafe"}),
                  map_place({"merNm": "식당", "merAddr": "서울 강남", "merTpbuzNm": "일반한식",
                             "merUrl": "https://web.paybooc.ai/mer/web/profile/food"})]
        args = request(source="skill-test", product_mode="date", party_size=2,
                       excluded_terms=["해산물"], max_budget_per_person=20000,
                       category_order=["cafe", "restaurant"])
        with patch("backend.app.team_integration.skill_probe.fetch_places", return_value=(places, False)) as fetch:
            result = recommend(args)
        fetch.assert_called_once_with("강남")
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["courses"][0]["status"], "needs_verification")
        self.assertIsNone(result["courses"][0]["distance_m"])
        self.assertTrue(all(c["status"] == "needs_verification" for c in result["candidates"]))
        self.assertTrue(all(c["eatpl_url"] for c in result["candidates"]))
        self.assertIn("미확인", " ".join(result["candidates"][0]["reasons"]))

    def test_failure_and_empty_never_fallback_to_sample(self):
        with patch("backend.app.team_integration.skill_probe.fetch_places", side_effect=TimeoutError):
            failed = recommend(request(source="skill-test"))
        self.assertEqual((failed["status"], failed["candidates"]), ("error", []))
        with patch("backend.app.team_integration.skill_probe.fetch_places", return_value=([], None)):
            empty = recommend(request(source="skill-test"))
        self.assertEqual((empty["status"], empty["candidates"]), ("empty", []))

    def test_rejects_invalid_or_unrecognized_conditions(self):
        invalid = [request(confirmed=1), request(party_size=True), request(source="unknown"),
                   request(extra_condition="must not be dropped"), request(excluded_terms="해산물"),
                   request(max_leg_distance_m=float("nan")),
                   request(product_mode="date", category_order=["cafe", "bar"])]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                recommend(payload)


if __name__ == "__main__":
    unittest.main()
