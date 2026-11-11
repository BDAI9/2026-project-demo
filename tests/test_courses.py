import unittest

from backend.app.providers.models import Fact, Place
from backend.app.recommendations.evaluation import Constraint
from backend.app.recommendations.courses import build_courses, straight_line_distance_m


def place(id, category, latitude=37.5, longitude=127.0, price=10000, **attributes):
    facts = {key: Fact(value, "test", True) for key, value in attributes.items()}
    if price is not None:
        facts["price_per_person_krw"] = Fact(price, "test", True)
    return Place(id, id, category, latitude=latitude, longitude=longitude, attributes=facts)


class CourseTests(unittest.TestCase):
    def setUp(self):
        self.cafe = place("c1", "cafe", quiet=True)
        self.other_cafe = place("c2", "cafe", latitude=37.51, quiet=False)
        self.restaurant = place("r1", "restaurant", longitude=127.01)
        self.baseline = [self.cafe, self.other_cafe, self.restaurant]

    def test_order_and_replacement_recompute(self):
        rules = [Constraint("quiet", "a", "quiet", "eq", True, scope="stop", stop_index=0)]
        result = build_courses(self.baseline, rules, fixed_stops={1: "r1"})
        self.assertEqual([(c.places[0].id, c.places[1].id) for c in result.eligible], [("c1", "r1")])
        self.assertFalse(build_courses(self.baseline, rules, fixed_stops={0: "c2"}).eligible)
        reverse = build_courses(self.baseline, [], ("restaurant", "cafe"), fixed_stops={1: "c2"})
        self.assertEqual([p.id for p in reverse.eligible[0].places], ["r1", "c2"])
        self.assertFalse(build_courses(self.baseline, [], fixed_stops={0: "c1"}, excluded_place_ids=["c1"]).eligible)

    def test_distance_is_straight_line_and_limits_filter(self):
        distance = straight_line_distance_m(self.cafe, self.restaurant)
        self.assertGreater(distance, 800)
        self.assertLess(distance, 1000)
        self.assertEqual(len(build_courses([self.cafe, self.restaurant], [], max_leg_distance_m=100).eligible), 0)
        result = build_courses([self.cafe, self.restaurant], [], max_leg_distance_m=2000)
        self.assertAlmostEqual(result.eligible[0].legs[0].straight_line_distance_m, distance)

    def test_unknown_distance_and_price_are_not_claimed_as_met(self):
        unknown = place("c3", "cafe", latitude=None, longitude=None, price=None)
        no_limit = build_courses([unknown, self.restaurant], [])
        self.assertEqual(len(no_limit.eligible), 1)
        self.assertIsNone(no_limit.eligible[0].legs[0].straight_line_distance_m)
        self.assertIsNone(no_limit.eligible[0].total_per_person_krw)
        result = build_courses([unknown, self.restaurant], [], max_leg_distance_m=1000, max_total_per_person_krw=30000)
        self.assertFalse(result.eligible)
        self.assertEqual(len(result.needs_review), 1)
        self.assertEqual(len(result.needs_review[0].reasons), 2)
        # The known cost alone is too high even without the missing cost.
        over_budget = build_courses([unknown, self.restaurant], [], max_total_per_person_krw=5000)
        self.assertEqual(over_budget.rejected_count, 1)
        self.assertFalse(over_budget.needs_review)

    def test_total_budget_and_missing_place_attributes(self):
        self.assertEqual(build_courses([self.cafe, self.restaurant], [], max_total_per_person_krw=15000).rejected_count, 1)
        self.assertEqual(build_courses([self.cafe, self.restaurant], [], max_total_per_person_krw=20000).eligible[0].total_per_person_krw, 20000)
        constraint = Constraint("menu", "a", "ingredients", "excludes", "해산물", scope="stop", stop_index=1)
        result = build_courses([self.cafe, self.restaurant], [constraint])
        self.assertEqual(len(result.needs_review), 1)
        self.assertFalse(result.eligible)

    def test_invalid_inputs_and_same_place_identity(self):
        with self.assertRaises(ValueError): build_courses(self.baseline, [], ("cafe", "cafe"))
        with self.assertRaises(ValueError): build_courses(self.baseline, [], max_leg_distance_m=float("nan"))
        with self.assertRaises(ValueError): build_courses(self.baseline, [], fixed_stops={2: "c1"})
        cafe = place("same", "cafe")
        restaurant = place("same", "restaurant")
        self.assertEqual(build_courses([cafe, restaurant], []).rejected_count, 1)

    def test_preferences_are_equal_per_participant_across_stops(self):
        cafe = place("c", "cafe", quiet=True, vegan=False)
        restaurant = place("r", "restaurant", quiet=True)
        rules = [Constraint("a", "a", "quiet", "eq", True, strength="soft"),
                 Constraint("b", "b", "vegan", "eq", True, strength="soft", scope="stop", stop_index=0)]
        # A's room preference applies to both places, but must not count twice
        # as much as B's stop-specific preference.
        self.assertEqual(build_courses([cafe, restaurant], rules).eligible[0].score, 0.5)
        true_cafe = place("c", "cafe", quiet=True, vegan=True)
        self.assertEqual(build_courses([true_cafe, restaurant], rules).eligible[0].score, 1.0)


if __name__ == "__main__":
    unittest.main()
