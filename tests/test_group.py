import unittest

from backend.app.providers.models import Fact, Place
from backend.app.recommendations.evaluation import Constraint
from backend.app.recommendations.group import CandidateExclusion, evaluate_group_candidates


class GroupCandidateTests(unittest.TestCase):
    def setUp(self):
        self.baseline = [
            Place("one", "A", "restaurant", attributes={"price": Fact(10000, "sample"), "quiet": Fact(True, "sample")}),
            Place("two", "B", "restaurant", attributes={"price": Fact(30000, "sample")}),
            Place("three", "C", "restaurant", attributes={"quiet": Fact(False, "sample")}),
        ]
        self.cheap_a = Constraint("cheap-a", "a", "price", "lte", 20000)
        self.cheap_b = Constraint("cheap-b", "b", "price", "lte", 20000)

    def test_removing_one_participants_condition_keeps_the_others(self):
        both = evaluate_group_candidates(self.baseline, [self.cheap_a, self.cheap_b])
        self.assertEqual([c.place.id for c in both.eligible], ["one"])
        self.assertEqual([c.place.id for c in both.excluded], ["two"])
        self.assertEqual([c.place.id for c in both.needs_review], ["three"])
        self.assertIn("조건 불충족: cheap-a", both.excluded[0].reasons)
        self.assertIn("조건 불충족: cheap-b", both.excluded[0].reasons)
        only_b = evaluate_group_candidates(self.baseline, [self.cheap_b])
        self.assertIn("조건 불충족: cheap-b", only_b.excluded[0].reasons)
        self.assertNotIn("조건 불충족: cheap-a", only_b.excluded[0].reasons)
        none = evaluate_group_candidates(self.baseline, [])
        self.assertEqual({c.place.id for c in none.eligible}, {"one", "two", "three"})
        self.assertEqual([p.id for p in self.baseline], ["one", "two", "three"])

    def test_direct_exclusion_recovers_only_when_all_participants_remove_it(self):
        first = CandidateExclusion("one", "a", "too far")
        second = CandidateExclusion("one", "b")
        both = evaluate_group_candidates(self.baseline, [], [first, second])
        self.assertEqual([c.place.id for c in both.excluded], ["one"])
        self.assertEqual(both.excluded[0].direct_exclusions, (first, second))
        one_left = evaluate_group_candidates(self.baseline, [], [CandidateExclusion("one", "a", active=False), second])
        self.assertEqual(one_left.excluded[0].direct_exclusions, (second,))
        neither = evaluate_group_candidates(self.baseline, [], [CandidateExclusion("one", "a", active=False)])
        self.assertEqual({c.place.id for c in neither.eligible}, {"one", "two", "three"})

    def test_removed_direct_exclusion_does_not_remove_other_conditions(self):
        blocked = evaluate_group_candidates(self.baseline, [self.cheap_a], [CandidateExclusion("two", "a")])
        self.assertIn("참가자가 직접 제외", blocked.excluded[0].reasons)
        self.assertIn("조건 불충족: cheap-a", blocked.excluded[0].reasons)
        restored = evaluate_group_candidates(self.baseline, [self.cheap_a], [])
        self.assertEqual(restored.excluded[0].place.id, "two")
        self.assertFalse(restored.excluded[0].direct_exclusions)

    def test_uncertain_condition_stays_unconfirmed(self):
        exclude_seafood = Constraint("seafood", "a", "contains_seafood", "eq", False)
        result = evaluate_group_candidates(self.baseline, [exclude_seafood])
        self.assertFalse(result.eligible)
        self.assertEqual(len(result.needs_review), 3)
        self.assertTrue(all("조건 확인 필요: seafood" in c.reasons for c in result.needs_review))

    def test_ambiguous_exclusions_and_unsupported_stop_scope_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_group_candidates(self.baseline, [], [CandidateExclusion("one", "a"), CandidateExclusion("one", "a", active=False)])
        with self.assertRaises(ValueError):
            evaluate_group_candidates(self.baseline, [Constraint("c", "a", "quiet", "eq", True, scope="stop", stop_index=0)])


if __name__ == "__main__":
    unittest.main()
