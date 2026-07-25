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


def test_exposure_provenance_is_reported(client):
    """A fixture must not be presented as a live forecast."""
    assert client.get("/people/doris/assessment").json()["exposure"]["source"] == "fixture"


def test_unknown_person_returns_404_not_500(client):
    assert client.get("/people/nobody/assessment").status_code == 404
