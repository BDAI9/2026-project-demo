import unittest

from backend.app.providers.models import Fact, Place
from backend.app.providers.mock import sample_places
from backend.app.recommendations.evaluation import Constraint, evaluate_candidates


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.p = Place("1", "sample", "restaurant", attributes={"price_per_person_krw": Fact(20000, "mock"), "ingredients": Fact(["beef"], "mock"), "capacity": Fact(4, "mock")})

    def test_hard_failure_unknown_and_recovery(self):
        cheap = Constraint("cheap", "a", "price_per_person_krw", "lte", 10000)
        no_seafood = Constraint("seafood", "b", "ingredients", "excludes", "seafood")
        self.assertEqual(len(evaluate_candidates([self.p], [cheap, no_seafood]).excluded), 1)
        self.assertEqual(len(evaluate_candidates([self.p], [no_seafood]).needs_review), 1)
        self.assertEqual(len(evaluate_candidates([self.p], []).eligible), 1)
        self.assertEqual(len(evaluate_candidates([self.p], [], ["1"]).excluded), 1)

    def test_complete_list_allows_negative_assertion(self):
        p = Place("1", "sample", "restaurant", attributes={"ingredients": Fact(["beef"], "source", complete=True)})
        rule = Constraint("1", "a", "ingredients", "excludes", "seafood")
        self.assertEqual(len(evaluate_candidates([p], [rule]).eligible), 1)

    def test_seafood_absence_requires_explicit_verified_fact(self):
        # A list containing shrimp without the literal word "해산물" cannot
        # establish that the broader class of seafood is absent.
        p = Place("shrimp", "sample", "restaurant", attributes={"ingredients": Fact(["새우"], "test", True)})
        rule = Constraint("seafood", "a", "contains_seafood", "eq", False)
        self.assertEqual(len(evaluate_candidates([p], [rule]).needs_review), 1)
        verified = Place("verified", "sample", "restaurant", attributes={"contains_seafood": Fact(False, "test")})
        self.assertEqual(len(evaluate_candidates([verified], [rule]).eligible), 1)

    def test_stop_scope_and_participant_weight(self):
        rules = [Constraint("1", "a", "price_per_person_krw", "lte", 20000, "soft"),
                 Constraint("2", "a", "capacity", "gte", 4, "soft"),
                 Constraint("3", "b", "capacity", "gte", 10, "soft"),
                 Constraint("4", "a", "price_per_person_krw", "lte", 1, scope="stop", stop_index=1)]
        self.assertEqual(evaluate_candidates([self.p], rules, stop_index=0).eligible[0].score, .5)
        self.assertEqual(len(evaluate_candidates([self.p], rules, stop_index=1).excluded), 1)

    def test_party_size_and_unknown_capacity(self):
        self.assertEqual(len(evaluate_candidates([self.p], [], party_size=5).excluded), 1)
        unknown = Place("2", "unknown", "cafe")
        self.assertEqual(len(evaluate_candidates([unknown], [], party_size=2).needs_review), 1)

    def test_samples_are_fictional_and_have_no_eatpl_link(self):
        places = sample_places(region="가상 지역", category="cafe")
        self.assertEqual(len(places), 2)
        self.assertTrue(all(p.source == "mock" and p.eatpl_url is None for p in places))
        self.assertEqual(sample_places(region="강남"), [])

    def test_bad_coordinates_rejected(self):
        with self.assertRaises(ValueError): Place("x", "x", "cafe", latitude=300000, longitude=500000)
        with self.assertRaises(ValueError): Place("x", "x", "cafe", latitude=37.5)

    def test_scalar_comparison_never_proves_list_or_incompatible_type(self):
        contains_seafood = Place("seafood", "restaurant", "restaurant", attributes={"ingredients": Fact(["seafood"], "menu", complete=True)})
        rule = Constraint("avoid", "a", "ingredients", "neq", "seafood")
        self.assertEqual(len(evaluate_candidates([contains_seafood], [rule]).needs_review), 1)
        # A proper membership rule excludes a known ingredient, even in a partial list.
        rule = Constraint("avoid", "a", "ingredients", "excludes", "seafood")
        self.assertEqual(len(evaluate_candidates([contains_seafood], [rule]).excluded), 1)
        p = Place("integer", "sample", "cafe", attributes={"quiet": Fact(1, "source")})
        self.assertEqual(len(evaluate_candidates([p], [Constraint("quiet", "a", "quiet", "eq", True)]).needs_review), 1)

    def test_unknown_category_is_unverified_for_both_comparisons(self):
        p = Place("unknown", "sample", "unknown", source="eatpl")
        for op in ("eq", "neq"):
            result = evaluate_candidates([p], [Constraint("category", "a", "category", op, "cafe")])
            self.assertEqual(len(result.needs_review), 1)
            self.assertFalse(result.eligible)
            self.assertFalse(result.excluded)


if __name__ == "__main__":
    unittest.main()
