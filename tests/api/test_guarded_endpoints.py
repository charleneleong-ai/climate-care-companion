"""The two endpoints that must not be open.

`/push/subscribe` decides whose health alerts arrive on which phone, and
`/cron/sweep` sends real messages to real people. Both were reachable by anyone
who knew the URL — survivable only while the URL was an unguessable tunnel, and
a deployment's whole purpose is to replace that with a stable public address.

Both fail closed. The tempting alternative — open when unconfigured, guarded
once a secret is set — means the one deployment that forgets the variable is the
one running wide open, and from the outside it looks exactly like a working one.
"""

from datetime import UTC, datetime

import api.main as api
import pytest
from fastapi.testclient import TestClient
from scheduler.sweep import SweepResult

TOKEN = "a-shared-secret"


@pytest.fixture
def client() -> TestClient:
    return TestClient(api.app)


@pytest.fixture
def registration() -> dict:
    return {
        "endpoint": "https://push.example/device",
        "p256dh": "key",
        "auth": "auth",
        "person_id": "doris",
        "audience": "caregiver",
    }


class TestPushRegistrationIsGuarded:
    def test_an_unconfigured_deployment_refuses_rather_than_opens(
        self, client, registration, monkeypatch
    ):
        monkeypatch.setattr(api, "PUSH_TOKEN", None)
        response = client.post("/push/subscribe", json=registration)
        assert response.status_code == 503
        assert "CLIMATISE_PUSH_TOKEN" in response.json()["detail"]

    @pytest.mark.parametrize(
        "headers",
        [{}, {"X-Climatise-Token": "wrong"}, {"X-Climatise-Token": ""}],
        ids=["absent", "wrong", "empty"],
    )
    def test_a_stranger_cannot_register_a_device(self, client, registration, monkeypatch, headers):
        """The attack this closes: read `GET /people`, pick a name, point your
        own phone at it, and receive that person's alerts from then on."""
        monkeypatch.setattr(api, "PUSH_TOKEN", TOKEN)
        response = client.post("/push/subscribe", json=registration, headers=headers)
        assert response.status_code == 401

    def test_the_app_can_still_register(self, client, registration, monkeypatch):
        monkeypatch.setattr(api, "PUSH_TOKEN", TOKEN)
        response = client.post(
            "/push/subscribe", json=registration, headers={"X-Climatise-Token": TOKEN}
        )
        assert response.status_code == 200
        assert response.json()["registered"] is True

    def test_unsubscribing_is_guarded_too(self, client, monkeypatch):
        """Otherwise anyone could silence a person's alerts, which is the more
        dangerous half — a device that stops buzzing looks like a quiet night."""
        monkeypatch.setattr(api, "PUSH_TOKEN", TOKEN)
        response = client.request(
            "DELETE", "/push/subscribe", json={"endpoint": "https://push.example/device"}
        )
        assert response.status_code == 401


class TestTheSweepIsGuarded:
    def test_an_unconfigured_deployment_refuses(self, client, monkeypatch):
        monkeypatch.setattr(api, "CRON_SECRET", None)
        response = client.post("/cron/sweep")
        assert response.status_code == 503
        assert "CRON_SECRET" in response.json()["detail"]

    @pytest.mark.parametrize(
        "headers",
        [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "a-cron-secret"}],
        ids=["absent", "wrong-secret", "missing-bearer-prefix"],
    )
    def test_a_stranger_cannot_trigger_a_send(self, client, monkeypatch, headers):
        monkeypatch.setattr(api, "CRON_SECRET", "a-cron-secret")
        response = client.post("/cron/sweep", headers=headers)
        assert response.status_code == 401

    def test_the_platform_can_trigger_it(self, client, monkeypatch):
        """Vercel sends `Authorization: Bearer $CRON_SECRET`."""
        monkeypatch.setattr(api, "CRON_SECRET", "a-cron-secret")
        swept = {}

        def fake_run_sweep(send: bool):
            swept["send"] = send
            return SweepResult(at=datetime.now(UTC), assessed=3, dispatched=(), unreachable=())

        monkeypatch.setattr("scheduler.build.run_sweep", fake_run_sweep)
        response = client.post("/cron/sweep", headers={"Authorization": "Bearer a-cron-secret"})

        assert response.status_code == 200
        assert response.json()["assessed"] == 3

    def test_it_does_not_send_unless_asked(self, client, monkeypatch):
        """A cron that messages people the first time anyone curls it is the
        failure the CLI's dry-run default already guards against."""
        monkeypatch.setattr(api, "CRON_SECRET", "a-cron-secret")
        swept = {}

        def fake_run_sweep(send: bool):
            swept["send"] = send
            return SweepResult(at=datetime.now(UTC), assessed=0, dispatched=(), unreachable=())

        monkeypatch.setattr("scheduler.build.run_sweep", fake_run_sweep)
        client.post("/cron/sweep", headers={"Authorization": "Bearer a-cron-secret"})

        assert swept["send"] is False
