"""The register scored across an episode.

Written after a real bug: the first version of `episode_exposure` computed the
bedroom with a formula invented in the endpoint rather than `IndoorModel`, which
silently flattened the cohort — nobody reached High, contradicting the worked
example the verification suite pins. These tests exist so the view cannot drift
from the engine again.
"""

import pytest
from api.main import HEAT_EPISODE, app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def episode(client) -> dict:
    return client.get("/monitoring/forecast?scenario=heat").json()


def test_the_episode_covers_every_day_of_it(episode):
    assert len(episode["days"]) == len(HEAT_EPISODE)


def test_the_register_is_quiet_before_it_is_not(episode):
    """The lead-time argument in one assertion: nobody at risk on the first day,
    everybody by the last. A view that showed risk on all three would suggest
    there was never a window to act in."""
    days = episode["days"]
    assert days[0]["at_risk"] == 0
    assert days[-1]["at_risk"] == episode["register_size"]


def test_the_peak_climbs_across_the_episode(episode):
    peaks = [day["peak_air"] for day in episode["days"]]
    assert peaks == sorted(peaks)
    assert peaks[0] < peaks[-1]


def test_the_worked_example_day_still_reaches_high(episode):
    """The bug this was written for. An invented indoor formula left the whole
    cohort at Elevated, which reads as a milder day than 19 July actually was."""
    final = episode["days"][-1]["tiers"]
    assert final["High"] > 0, "nobody reaches High — the indoor model is being bypassed"


def test_every_tier_count_sums_to_the_register(episode):
    """A person missing from the counts is a person nobody looked at."""
    size = episode["register_size"]
    for day in episode["days"]:
        assert sum(day["tiers"].values()) + day["unavailable"] == size


def test_each_person_is_named_with_the_day_they_cross(episode):
    first = episode["first_at_risk"]
    assert len(first) == episode["register_size"]
    assert all(entry["date"] == episode["days"][-1]["date"] for entry in first)


def test_the_scenario_is_labelled_rather_than_passed_off_as_live(episode):
    """SC-5's habit applied to a whole view: a modelled past episode must say so."""
    assert episode["scenario"] == "heat"
    assert "2025" in episode["label"]


def test_the_live_series_is_a_different_shape(client):
    """Not asserting values — the weather decides those. Only that asking for
    live gets live, so the toggle is real rather than decorative."""
    body = client.get("/monitoring/forecast").json()
    assert body["scenario"] == "live"
