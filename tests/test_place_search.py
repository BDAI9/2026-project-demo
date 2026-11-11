import json
import unittest
from unittest.mock import patch

from backend.app.place_search import search_group_places
from backend.app.providers.eatpl import EatplPlaceProvider, EatplTimeoutError
from backend.app.providers.models import Fact, Place
from backend.app.recommendations.evaluation import Constraint
from backend.app.recommendations.group import CandidateExclusion, evaluate_group_candidates


class RecordingProvider:
    source = "mock"

    def __init__(self, places=(), error=None):
        self.places, self.error, self.calls = list(places), error, []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.places


def make_place(pid, price, quiet, source="mock"):
    return Place(pid, pid, "restaurant", source=source, attributes={
        "price_per_person_krw": Fact(price, source),
        "quiet": Fact(quiet, source),
    })


class PlaceSearchTests(unittest.TestCase):
    def test_provider_receives_query_and_all_participant_conditions_apply(self):
        places = [make_place("a", 10000, True), make_place("b", 25000, True),
                  make_place("c", 10000, False)]
        provider = RecordingProvider(places)
        constraints = [Constraint("budget", "member-a", "price_per_person_krw", "lte", 20000),
                       Constraint("quiet", "member-b", "quiet", "eq", True)]
        result = search_group_places(region=" 서울 중구 ", business_type="일반한식", merchant_name="식당",
                                     constraints=constraints, provider=provider, trace_number="trace")
        self.assertEqual(provider.calls, [{"trace_number": "trace", "location": "서울 중구",
                                           "business_type": "일반한식", "merchant_name": "식당"}])
        self.assertEqual([c.place.id for c in result.candidates.eligible], ["a"])
        self.assertEqual({c.place.id for c in result.candidates.excluded}, {"b", "c"})
        self.assertEqual(result.baseline_places, tuple(places))
        self.assertEqual(result.source, "mock")
        self.assertFalse(result.truncated)
        # Removing a participant's condition starts from the same baseline.
        updated = evaluate_group_candidates(result.baseline_places, constraints[:1])
        self.assertEqual({c.place.id for c in updated.eligible}, {"a", "c"})

    def test_exclusions_and_unknown_conditions_are_preserved(self):
        first, second = make_place("a", 10000, True), make_place("b", 10000, True)
        first_exclusion = CandidateExclusion("a", "member-a", "멀어요")
        second_exclusion = CandidateExclusion("a", "member-b", "싫어요")
        rule = Constraint("seafood", "member-b", "contains_seafood", "eq", False)
        result = search_group_places(region="서울", constraints=[rule],
                                     exclusions=[first_exclusion, second_exclusion],
                                     provider=RecordingProvider([first, second]), trace_number="trace")
        self.assertEqual(result.candidates.excluded[0].place.id, "a")
        self.assertEqual(set(result.candidates.excluded[0].direct_exclusions), {first_exclusion, second_exclusion})
        self.assertEqual(result.candidates.needs_review[0].place.id, "b")
        remaining = evaluate_group_candidates(result.baseline_places, [rule], [second_exclusion])
        self.assertEqual(remaining.excluded[0].direct_exclusions, (second_exclusion,))

    def test_empty_errors_and_limit_are_distinct(self):
        empty = search_group_places(region="서울", constraints=[], provider=RecordingProvider(), trace_number="trace")
        self.assertEqual(empty.baseline_places, ())
        self.assertEqual(empty.candidates.eligible, ())
        self.assertEqual(empty.source, "mock")
        self.assertFalse(empty.truncated)
        with self.assertRaises(EatplTimeoutError):
            search_group_places(region="서울", constraints=[], provider=RecordingProvider(error=EatplTimeoutError()), trace_number="trace")
        hundred = [make_place(str(i), 10000, True) for i in range(100)]
        limited = search_group_places(region="서울", constraints=[], provider=RecordingProvider(hundred), trace_number="trace")
        self.assertTrue(limited.truncated)
        with self.assertRaises(ValueError):
            search_group_places(region=" ", constraints=[], provider=RecordingProvider(), trace_number="trace")

        class UnlabelledProvider(RecordingProvider):
            source = "unknown"
        unknown = search_group_places(region="서울", constraints=[], provider=UnlabelledProvider(), trace_number="trace")
        self.assertEqual(unknown.source, "unknown")

    @patch("backend.app.providers.eatpl.request.build_opener")
    def test_official_provider_mapping_preserves_business_type_and_link(self, opener):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size):
                return json.dumps({"rspCode": "00000", "data": [{
                    "merNm": "장소 A", "merAddr": "서울 중구", "merTpbuzNm": "고기구이",
                    "merUrl": "https://web.paybooc.ai/mer/web/profile/example",
                    "xaxsVal": "311826", "yaxsVal": "551982"}]}, ensure_ascii=False).encode()

        opener.return_value.open.return_value = Response()
        result = search_group_places(region="서울 중구", constraints=[], provider=EatplPlaceProvider("partner"),
                                     trace_number="partner202611110000000001")
        self.assertEqual(result.source, "eatpl")
        place = result.candidates.eligible[0].place
        self.assertEqual(place.attributes["business_type"].value, "고기구이")
        self.assertEqual(place.eatpl_url, "https://web.paybooc.ai/mer/web/profile/example")
        self.assertIsNone(place.latitude)  # TM128 is not WGS84.
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(json.loads(request.data)["location"], "서울 중구")
        self.assertEqual(request.get_method(), "POST")


if __name__ == "__main__":
    unittest.main()
