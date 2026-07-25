import pytest
from allocation.distance import haversine_km


def test_distance_between_two_bedford_town_centre_points():
    assert 0.05 < haversine_km(52.1364, -0.4669, 52.1358, -0.4681) < 0.2


def test_distance_to_self_is_zero():
    assert haversine_km(52.1364, -0.4669, 52.1364, -0.4669) == pytest.approx(0.0)


def test_london_to_bedford_is_about_seventy_kilometres():
    assert haversine_km(51.5074, -0.1278, 52.1364, -0.4669) == pytest.approx(73, abs=4)


def test_distance_is_symmetric():
    there = haversine_km(51.5074, -0.1278, 52.1364, -0.4669)
    back = haversine_km(52.1364, -0.4669, 51.5074, -0.1278)
    assert there == pytest.approx(back)
