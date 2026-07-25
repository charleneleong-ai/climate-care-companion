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
    assert body["tier"] in {"LOW", "ELEVATED", "HIGH", "SEVERE"}
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
