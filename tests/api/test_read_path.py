import pytest
from api.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_the_loaded_corpus_and_persona_counts(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["personas"] >= 3
    assert body["reason_codes"] == 23
    assert body["reasons_loaded"] == 23


def test_people_lists_every_seeded_persona(client):
    ids = {p["id"] for p in client.get("/people").json()}
    assert ids >= {"doris", "harold", "margaret"}


def test_assessment_returns_tier_and_reasons_not_a_bare_score(client):
    """AC-2: the reasons array is the system of record for explanation."""
    body = client.get("/people/doris/assessment").json()
    assert body["tier"] in {"Low", "Elevated", "High", "Severe"}
    assert body["reasons"], "an assessment with no reasons is not explainable"
    assert all({"code", "title", "explanation"} <= set(r) for r in body["reasons"])


def test_indoor_estimates_are_labelled_modelled(client):
    """SC-5: modelled values labelled at every point of display. The label is in the
    key name so a caller cannot drop it on the way to a screen."""
    exposure = client.get("/people/doris/assessment").json()["exposure"]
    assert "indoor_night_est_modelled" in exposure
    assert "indoor_day_est_modelled" in exposure


def test_response_states_it_is_not_medical_advice(client):
    """SC-2."""
    assert client.get("/people/doris/assessment").json()["not_medical_advice"] is True


VALID_SOURCES = {"live", "archive", "cache", "fixture", "self_report"}


def test_exposure_provenance_is_reported(client):
    """A cached figure must never be presented as a live one. The value matters
    less than the fact that one is always stated."""
    source = client.get("/people/doris/assessment").json()["exposure"]["source"]
    assert source in VALID_SOURCES


def test_the_read_path_survives_the_weather_service_being_down(client, monkeypatch):
    """NFR-04. With a warm cache the answer is stale and says so; with a cold one
    the failure is honest rather than invented."""
    from api import main

    class Dead:
        def get(self, *args, **kwargs):
            raise TimeoutError("Open-Meteo is unreachable")

    monkeypatch.setattr(main.WEATHER, "http", Dead())
    response = client.get("/people/doris/assessment")
    assert response.status_code in {200, 503}
    if response.status_code == 200:
        assert response.json()["exposure"]["source"] == "cache"


def test_unknown_person_returns_404_not_500(client):
    assert client.get("/people/nobody/assessment").status_code == 404


def test_tier_casing_matches_the_interaction_rules(client):
    """One casing across the whole system.

    /assess returned LOW while the interaction rules and the parity corpus used
    Elevated, so the front end's tier-to-band mapping fell through and labelled
    a Low assessment "Severe heat risk" — confidently, which is the dangerous
    kind of wrong.
    """
    from actions.export import ClinicalExporter

    tiers = {r["min_tier"] for r in ClinicalExporter.load().document()["interactions"]}
    served = client.get("/people/doris/assessment").json()["tier"]
    assert served[0].isupper() and served[1:].islower(), f"{served} is not title case"
    assert all(t[0].isupper() and t[1:].islower() for t in tiers)


PLACE_BODY = {
    "person": {
        "id": "doris",
        "name": "Doris",
        "age_band": "b85_plus",
        "lives_alone": True,
        "mobility_limited": False,
        "conditions": ["cardiovascular", "dementia"],
        "med_classes": ["beta_blocker"],
    },
    # Top-floor south-facing flat: FR-11 offset 2.8, which is the dwelling the
    # worked example is written for, so its declared estimates apply unchanged.
    "place": {"dwelling_type": "flat", "floor": 3, "aspect": "south", "has_cooling": False},
}
BUNGALOW = {**PLACE_BODY["place"], "dwelling_type": "bungalow", "floor": 0}


def assess_heat(client, place=None, **extra):
    body = {**PLACE_BODY, "fixture": "heat", **extra}
    if place is not None:
        body["place"] = place
    return client.post("/assess", json=body)


class TestAssessFixture:
    """The heat fixture is a different day, not a different model."""

    def test_the_worked_example_is_reproduced_exactly(self, client):
        """Spec section 8.6 declares 24.6 and 25.85 for a 2.8 offset. Pinning the
        literals holds the fixture and FR-11 against each other, so neither can
        drift without a test naming which one moved."""
        exposure = assess_heat(client).json()["exposure"]
        assert exposure["indoor_night_est_modelled"] == pytest.approx(24.6)
        assert exposure["indoor_day_est_modelled"] == pytest.approx(25.85)

    def test_sending_a_place_without_an_offset_is_not_a_500(self, client):
        """Omitting dwelling_offset is the documented way to make the core do the
        real lookup, and it crashed the demo path on a None."""
        assert assess_heat(client).status_code == 200

    def test_the_dwelling_moves_both_estimates(self, client):
        """A bungalow must not be served a top-floor flat's bedroom. Both routes
        left indoor_day_est at the fixture value for everyone regardless of home."""
        flat = assess_heat(client).json()["exposure"]
        bungalow = assess_heat(client, place=BUNGALOW).json()["exposure"]
        assert bungalow["indoor_night_est_modelled"] < flat["indoor_night_est_modelled"]
        assert bungalow["indoor_day_est_modelled"] < flat["indoor_day_est_modelled"]

    def test_an_explicit_offset_overrides_the_lookup(self, client):
        """The branch that already worked, kept covered while the other was fixed."""
        exposure = assess_heat(client, dwelling_offset=2.8).json()["exposure"]
        assert exposure["indoor_night_est_modelled"] == pytest.approx(24.6)

    def test_the_persona_route_agrees_with_assess(self, client):
        """Doris came back 24.6 and High from /assess but 19.8 and Elevated from
        her own page — the same woman on the same day, differing by which screen
        you opened, because each route had grown its own arithmetic."""
        served = client.get("/people/doris/assessment?fixture=heat").json()
        posted = assess_heat(client).json()
        # The two routes serialise different subsets of ExposureFeatures; what
        # must not differ is any figure they both choose to report.
        shared = served["exposure"].keys() & posted["exposure"].keys()
        assert {k: served["exposure"][k] for k in shared} == {
            k: posted["exposure"][k] for k in shared
        }
        assert served["tier"] == posted["tier"] == "High"
