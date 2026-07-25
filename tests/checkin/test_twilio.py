import base64
import hashlib
import hmac
import json

import pytest
from checkin.messages import ButtonMessage, TemplateMessage, decode_button_id, question_buttons
from checkin.twilio import (
    ALLOWED_RECIPIENTS_ENV,
    DryRunTwilio,
    TwilioChannel,
    TwilioFormatter,
    TwilioTransport,
)
from checkin.channels import ConversationChannel

QUESTION = ButtonMessage(
    body="Is your bedroom too hot?", buttons=question_buttons("q_bedroom_warm")
)
OPENER = TemplateMessage(
    name="climatise_checkin_opener",
    language="en_GB",
    body="Hello {{1}}. It will be hot tonight. Reply to this message.",
    variable_names=("first_name",),
).bind("Doris")

SENDER = "+14155238886"
RECIPIENT = "+447700900000"


# ---------------------------------------------------------------- addressing

def test_whatsapp_addresses_are_prefixed_and_sms_addresses_are_not():
    assert TwilioTransport.WHATSAPP.address(RECIPIENT) == f"whatsapp:{RECIPIENT}"
    assert TwilioTransport.SMS.address(RECIPIENT) == RECIPIENT


def test_prefixing_is_idempotent():
    """Config may already carry the prefix; double-prefixing silently fails to send."""
    already = f"whatsapp:{RECIPIENT}"
    assert TwilioTransport.WHATSAPP.address(already) == already


def test_the_same_message_goes_to_either_transport_unchanged():
    """SMS is a parameter, not a second integration."""
    for transport in TwilioTransport:
        params = TwilioFormatter.outbound(RECIPIENT, SENDER, QUESTION, transport)
        assert "Is your bedroom too hot?" in params["Body"]


# ------------------------------------------------------------------ outbound

def test_without_a_content_sid_a_question_is_plain_numbered_text():
    """Not a degraded mode — it is what SMS uses, and it works on WhatsApp with no
    Content template configured at all."""
    params = TwilioFormatter.outbound(RECIPIENT, SENDER, QUESTION, TwilioTransport.WHATSAPP)
    assert "ContentSid" not in params
    assert "1=Yes" in params["Body"] and "3=Not sure" in params["Body"]


def test_with_a_content_sid_a_question_becomes_a_quick_reply_template():
    params = TwilioFormatter.outbound(
        RECIPIENT, SENDER, QUESTION, TwilioTransport.WHATSAPP, content_sid="HX123"
    )
    assert params["ContentSid"] == "HX123"
    assert "Body" not in params


def test_content_variables_carry_the_question_and_the_button_payloads():
    """One reusable template serves all twenty-three questions."""
    variables = json.loads(TwilioFormatter.content_variables(QUESTION))
    assert variables["1"] == "Is your bedroom too hot?"
    assert variables["2"] == "q_bedroom_warm:yes"
    assert variables["3"] == "q_bedroom_warm:no"
    assert variables["4"] == "q_bedroom_warm:unsure"


def test_a_template_message_always_sends_as_plain_body_even_with_a_content_sid():
    """The opener is a text template, not a quick-reply one."""
    params = TwilioFormatter.outbound(
        RECIPIENT, SENDER, OPENER, TwilioTransport.WHATSAPP, content_sid="HX123"
    )
    assert params["Body"].startswith("Hello Doris.")


def test_an_unbound_template_still_refuses_to_send():
    unbound = TemplateMessage(
        name="t", language="en_GB", body="Hello {{1}}.", variable_names=("first_name",)
    )
    with pytest.raises(ValueError, match="unbound variables"):
        TwilioFormatter.outbound(RECIPIENT, SENDER, unbound, TwilioTransport.SMS)


# ------------------------------------------------------------------- inbound

def test_a_tapped_button_is_read_from_button_payload():
    """ButtonPayload is invisible to the user and carries the question code, so a
    late reply cannot be misfiled."""
    sender, button_id = TwilioFormatter.parse_inbound(
        {"From": f"whatsapp:{RECIPIENT}", "Body": "Yes", "ButtonPayload": "q_bedroom_warm:yes"}
    )
    assert sender == RECIPIENT
    assert decode_button_id(button_id) == ("q_bedroom_warm", True)


def test_a_typed_reply_falls_back_to_free_text_parsing():
    """Someone who types 1 instead of tapping has still answered."""
    sender, button_id = TwilioFormatter.parse_inbound(
        {"From": RECIPIENT, "Body": "1"}, question_code="q_bedroom_warm"
    )
    assert sender == RECIPIENT
    assert decode_button_id(button_id) == ("q_bedroom_warm", True)


def test_a_typed_reply_with_no_outstanding_question_is_not_an_answer():
    """Typed text carries no question code, so without context it cannot be filed."""
    _, button_id = TwilioFormatter.parse_inbound({"From": RECIPIENT, "Body": "yes"})
    assert button_id is None


def test_an_unrecognised_typed_reply_is_not_an_answer():
    _, button_id = TwilioFormatter.parse_inbound(
        {"From": RECIPIENT, "Body": "who is this"}, question_code="q_bedroom_warm"
    )
    assert button_id is None


def test_a_webhook_with_no_sender_raises():
    with pytest.raises(ValueError, match="no From field"):
        TwilioFormatter.parse_inbound({"Body": "yes"})


# -------------------------------------------------------- webhook signatures

def twilio_signature(url: str, params: dict[str, str], token: str) -> str:
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()


def test_a_correctly_signed_webhook_validates():
    url = "https://example.test/webhooks/twilio"
    params = {"From": RECIPIENT, "Body": "Yes", "ButtonPayload": "q_bedroom_warm:yes"}
    signature = twilio_signature(url, params, "secret-token")
    assert TwilioFormatter.validate_signature(url, params, signature, "secret-token")


def test_a_forged_webhook_is_rejected():
    """Without this, anyone can POST 'yes, my bedroom is dangerously hot' for a real
    person and move their tier."""
    url = "https://example.test/webhooks/twilio"
    params = {"From": RECIPIENT, "Body": "Yes"}
    assert not TwilioFormatter.validate_signature(url, params, "not-the-signature", "secret-token")


def test_a_tampered_parameter_invalidates_the_signature():
    url = "https://example.test/webhooks/twilio"
    params = {"From": RECIPIENT, "ButtonPayload": "q_rf_urine:yes"}
    signature = twilio_signature(url, params, "secret-token")
    tampered = params | {"ButtonPayload": "q_rf_urine:no"}
    assert not TwilioFormatter.validate_signature(url, tampered, signature, "secret-token")


def test_the_wrong_auth_token_invalidates_the_signature():
    url = "https://example.test/webhooks/twilio"
    params = {"From": RECIPIENT, "Body": "Yes"}
    signature = twilio_signature(url, params, "secret-token")
    assert not TwilioFormatter.validate_signature(url, params, signature, "other-token")


# --------------------------------------------------------------- SC-6 guards

def test_dry_run_twilio_is_a_conversation_channel():
    assert isinstance(DryRunTwilio(), ConversationChannel)


def test_dry_run_defaults_to_the_whatsapp_sandbox_number():
    channel = DryRunTwilio()
    channel.send(RECIPIENT, QUESTION)
    assert channel.sent[0]["From"] == f"whatsapp:{SENDER}"
    assert channel.sent[0]["To"] == f"whatsapp:{RECIPIENT}"


def test_dry_run_over_sms_uses_bare_addresses():
    channel = DryRunTwilio(transport=TwilioTransport.SMS, sender="+441234567890")
    channel.send(RECIPIENT, QUESTION)
    assert channel.sent[0]["To"] == RECIPIENT


def test_live_channel_refuses_to_construct_without_credentials(monkeypatch):
    for var in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SENDER"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValueError, match="credentials are absent"):
        TwilioChannel()


def test_live_channel_refuses_a_recipient_not_on_the_allowlist():
    channel = TwilioChannel(
        account_sid="AC1", auth_token="t", sender=SENDER, allowed_recipients=frozenset()
    )
    with pytest.raises(PermissionError, match="not on the allowlist"):
        channel.send(RECIPIENT, QUESTION)


def test_the_allowlist_check_ignores_the_whatsapp_prefix():
    """A prefixed address must not slip past a bare-number allowlist."""
    channel = TwilioChannel(
        account_sid="AC1", auth_token="t", sender=SENDER, allowed_recipients=frozenset()
    )
    with pytest.raises(PermissionError):
        channel.send(f"whatsapp:{RECIPIENT}", QUESTION)


def test_the_messages_url_targets_the_account():
    channel = TwilioChannel(
        account_sid="AC123", auth_token="t", sender=SENDER,
        allowed_recipients=frozenset({RECIPIENT}),
    )
    assert channel.url == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"


def test_the_allowlist_is_empty_by_default(monkeypatch):
    monkeypatch.delenv(ALLOWED_RECIPIENTS_ENV, raising=False)
    assert TwilioChannel.allowlist_from_env() == frozenset()
