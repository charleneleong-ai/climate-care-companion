"""The webhook is the only surface an outsider can reach, so it is tested as one."""

import base64
import hashlib
import hmac
from datetime import UTC, date, datetime

import pytest
from checkin.messages import TemplateLibrary, encode_button_id
from checkin.questions import QuestionBank
from checkin.session import CheckinSession, SessionState
from contracts import Assessment, DateRange, Reason, ReasonCode, Tier
from fastapi.testclient import TestClient

from voice import main as webhook_module

WINDOW = DateRange(date(2025, 7, 19), date(2025, 7, 20))
RECIPIENT = "+447700900000"
TOKEN = "test-auth-token"
URL = "https://example.test/webhooks/twilio"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(webhook_module, "WEBHOOK_URL", URL)
    webhook_module.SESSIONS.by_number.clear()
    webhook_module.CHANNEL.sent.clear()
    yield


@pytest.fixture(scope="module")
def bank() -> QuestionBank:
    return QuestionBank.load()


@pytest.fixture
def client() -> TestClient:
    return TestClient(webhook_module.app)


def make_session(bank) -> CheckinSession:
    assessment = Assessment(
        tier=Tier.HIGH,
        risk_score=6.0,
        exposure_score=3,
        vulnerability_score=10,
        reasons=(Reason(ReasonCode.BEDROOM_WARM, "t", "e", 1),),
    )
    return CheckinSession(
        questionnaire=bank.build_for("doris", WINDOW, assessment),
        opener=TemplateLibrary.load().opener_for(simplified=False).bind("Doris"),
    )


def signed(form: dict[str, str]) -> dict[str, str]:
    payload = URL + "".join(f"{k}{form[k]}" for k in sorted(form))
    signature = base64.b64encode(
        hmac.new(TOKEN.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()
    return {"X-Twilio-Signature": signature}


def post(client, form: dict[str, str], headers: dict[str, str] | None = None):
    return client.post("/webhooks/twilio", data=form, headers=headers or signed(form))


# ------------------------------------------------------------------- security


def test_an_unsigned_request_is_rejected(client):
    """Without this anyone can inject false health data for a real person."""
    form = {"From": RECIPIENT, "ButtonPayload": "q_bedroom_warm:yes"}
    assert post(client, form, headers={"X-Twilio-Signature": "forged"}).status_code == 403


def test_a_tampered_parameter_is_rejected(client, bank):
    webhook_module.SESSIONS.open(RECIPIENT, make_session(bank))
    form = {"From": RECIPIENT, "ButtonPayload": "q_bedroom_warm:no"}
    headers = signed(form)
    tampered = form | {"ButtonPayload": "q_bedroom_warm:yes"}
    assert post(client, tampered, headers=headers).status_code == 403


def test_a_missing_auth_token_fails_closed(client, monkeypatch):
    """A misconfiguration is not permission to accept whatever arrives."""
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLIMATISE_ALLOW_UNSIGNED_WEBHOOKS", raising=False)
    form = {"From": RECIPIENT, "Body": "yes"}
    assert post(client, form).status_code == 503


def test_an_unknown_sender_is_silently_ignored(client):
    """A 404 with detail would confirm which numbers the service talks to, which is
    a disclosure about vulnerable people."""
    form = {"From": "+447700999999", "Body": "hello?"}
    response = post(client, form)
    assert response.status_code == 204
    assert response.content == b""


def test_a_webhook_with_no_sender_is_a_bad_request(client):
    assert post(client, {"Body": "yes"}).status_code == 400


# ---------------------------------------------------------------- the exchange


def test_a_button_reply_is_recorded_and_the_next_question_goes_out(client, bank):
    session = make_session(bank)
    session.record_sent(datetime.now(UTC))
    webhook_module.SESSIONS.open(RECIPIENT, session)

    first = session.questionnaire.questions[0]
    post(client, {"From": RECIPIENT, "ButtonPayload": encode_button_id(first.code, True)})

    assert session.answers[first.code] is True
    assert session.state is SessionState.IN_PROGRESS
    assert webhook_module.CHANNEL.sent, "no follow-up question was sent"


def test_a_typed_reply_is_matched_against_the_outstanding_question(client, bank):
    """Someone who types 1 rather than tapping has still answered."""
    session = make_session(bank)
    session.record_sent(datetime.now(UTC))
    webhook_module.SESSIONS.open(RECIPIENT, session)
    first = session.questionnaire.questions[0]

    post(client, {"From": RECIPIENT, "Body": "1"})
    assert session.answers[first.code] is True


def test_an_unparseable_reply_does_not_count_as_an_answer(client, bank):
    """It reopens the window and re-sends the question rather than guessing."""
    session = make_session(bank)
    session.record_sent(datetime.now(UTC))
    webhook_module.SESSIONS.open(RECIPIENT, session)
    first = session.questionnaire.questions[0]

    post(client, {"From": RECIPIENT, "Body": "who is this?"})
    assert first.code not in session.answers
    assert session.state is SessionState.IN_PROGRESS


def test_the_whatsapp_prefix_is_stripped_when_matching_a_session(client, bank):
    session = make_session(bank)
    session.record_sent(datetime.now(UTC))
    webhook_module.SESSIONS.open(RECIPIENT, session)
    first = session.questionnaire.questions[0]

    post(
        client,
        {
            "From": f"whatsapp:{RECIPIENT}",
            "ButtonPayload": encode_button_id(first.code, False),
        },
    )
    assert session.answers[first.code] is False


def test_health_reports_open_sessions(client, bank):
    webhook_module.SESSIONS.open(RECIPIENT, make_session(bank))
    assert client.get("/health").json()["sessions"] == 1
