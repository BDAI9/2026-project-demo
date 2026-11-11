"""Fictional sample places, not real businesses or Eatpl data."""

from backend.app.providers.models import Fact, Place


def sample_places(region: str | None = None, category: str | None = None) -> list[Place]:
    # Coordinates are illustrative, and do not identify real shops.
    def place(id, name, category, lat, lng, price, capacity, quiet):
        return Place(id=id, name=name, category=category, address="가상 지역", latitude=lat, longitude=lng,
                     attributes={"region": Fact("가상 지역", "mock"), "price_per_person_krw": Fact(price, "mock"),
                                 "capacity": Fact(capacity, "mock"), "quiet": Fact(quiet, "mock")})
    places = [
        place("sample-cafe-1", "샘플 카페 A", "cafe", 37.50, 127.00, 8000, 8, True),
        place("sample-cafe-2", "샘플 카페 B", "cafe", None, None, 6000, 4, False),
        place("sample-restaurant-1", "샘플 식당 A", "restaurant", 37.505, 127.005, 18000, 6, True),
        place("sample-restaurant-2", "샘플 식당 B", "restaurant", 37.51, 127.01, 15000, 4, False),
    ]
    return [p for p in places if (region is None or p.attributes["region"].value == region) and (category is None or p.category == category)]
