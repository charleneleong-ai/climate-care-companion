import pytest
from checkin.messages import (
    ButtonMessage,
    ReplyButton,
    TemplateMessage,
    decode_button_id,
    encode_button_id,
    question_buttons,
)
from checkin.whatsapp import (
    ALLOW_REAL_SENDS_ENV,
    GRAPH_API_VERSION,
    CloudApiWhatsApp,
    ConversationChannel,
    DryRunWhatsApp,
    WhatsAppFormatter,
)

OPENER = TemplateMessage(
    name="climatise_checkin_opener",
    language="en_GB",
    body="Hello {{1}}. It is going to be hot tonight. Can we ask you two quick questions?",
    variable_names=("first_name",),
).bind("Doris")


# ------------------------------------------------------------- button encoding

@pytest.mark.parametrize("answer", [True, False, None], ids=["yes", "no", "unsure"])
def test_button_ids_round_trip(answer):
    code, decoded = decode_button_id(encode_button_id("q_bedroom_warm", answer))
    assert code == "q_bedroom_warm"
    assert decoded is answer


def test_button_id_carries_the_question_so_late_replies_cannot_be_misfiled():
    assert decode_button_id(encode_button_id("q_rf_urine", False))[0] == "q_rf_urine"


@pytest.mark.parametrize("bad", ["", "no_colon", "q_x:maybe", ":yes"])
def test_unrecognised_button_ids_raise(bad):
    with pytest.raises(ValueError, match="button id"):
        decode_button_id(bad)


def test_every_question_offers_yes_no_and_not_sure():
    """'Not sure' is a first-class answer. Forcing a binary from someone who does
    not know produces a confident wrong value."""
    titles = [b.title for b in question_buttons("q_wellbeing")]
    assert titles == ["Yes", "No", "Not sure"]


# ------------------------------------------------------- WhatsApp's own limits

def test_more_than_three_buttons_is_rejected():
    with pytest.raises(ValueError, match="at most 3"):
        ButtonMessage(
            body="?", buttons=tuple(ReplyButton(f"q:{i}", str(i)) for i in range(4))
        )


def test_a_button_title_over_twenty_characters_is_rejected():
    with pytest.raises(ValueError, match="20 characters"):
        ReplyButton("q_x:yes", "A title far too long for WhatsApp")


def test_an_interactive_message_needs_at_least_one_button():
    with pytest.raises(ValueError, match="at least one button"):
        ButtonMessage(body="?", buttons=())


# ------------------------------------------------------------------- payloads

def test_template_payload_targets_the_current_graph_version():
    channel = CloudApiWhatsApp(
        phone_number_id="123", access_token="t", allowed_recipients=frozenset({"447700900000"})
    )
    assert channel.url == f"https://graph.facebook.com/{GRAPH_API_VERSION}/123/messages"


def test_template_payload_carries_variables_as_body_parameters():
    payload = WhatsAppFormatter.template("447700900000", OPENER)
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "climatise_checkin_opener"
    assert payload["template"]["language"] == {"code": "en_GB"}
    assert payload["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": "Doris"}
    ]


def test_template_without_variables_omits_components():
    plain = TemplateMessage(name="t", language="en_GB", body="Hello.")
    assert "components" not in WhatsAppFormatter.template("447700900000", plain)["template"]


def test_button_payload_matches_the_cloud_api_interactive_shape():
    message = ButtonMessage(
        body="Is your bedroom too hot?", buttons=question_buttons("q_bedroom_warm")
    )
    payload = WhatsAppFormatter.buttons("447700900000", message)
    assert payload["type"] == "interactive"
    assert payload["interactive"]["type"] == "button"
    assert payload["interactive"]["body"]["text"] == "Is your bedroom too hot?"
    buttons = payload["interactive"]["action"]["buttons"]
    assert len(buttons) == 3
    assert buttons[0] == {
        "type": "reply",
        "reply": {"id": "q_bedroom_warm:yes", "title": "Yes"},
    }


def test_build_dispatches_on_message_type():
    assert WhatsAppFormatter.build("447700900000", OPENER)["type"] == "template"
    buttons = ButtonMessage(body="?", buttons=question_buttons("q_x"))
    assert WhatsAppFormatter.build("447700900000", buttons)["type"] == "interactive"


# ------------------------------------------------------------------- inbound

def button_webhook(sender: str, button_id: str) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": sender,
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {"id": button_id, "title": "Yes"},
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_inbound_button_press_is_parsed():
    sender, button_id = WhatsAppFormatter.parse_inbound(
        button_webhook("447700900000", "q_bedroom_warm:yes")
    )
    assert sender == "447700900000"
    assert button_id == "q_bedroom_warm:yes"


def test_a_typed_message_returns_no_button_but_still_identifies_the_sender():
    """Any inbound reopens the 24-hour window, so the sender matters even when the
    content is not an answer."""
    payload = {
        "entry": [
            {"changes": [{"value": {"messages": [{"from": "447700900000", "type": "text"}]}}]}
        ]
    }
    sender, button_id = WhatsAppFormatter.parse_inbound(payload)
    assert sender == "447700900000"
    assert button_id is None


def test_a_malformed_webhook_raises_rather_than_returning_nothing():
    with pytest.raises(ValueError, match="not a WhatsApp inbound"):
        WhatsAppFormatter.parse_inbound({"entry": []})


# --------------------------------------------------------------- SC-6 guards

def test_dry_run_is_a_conversation_channel():
    assert isinstance(DryRunWhatsApp(), ConversationChannel)


def test_dry_run_captures_the_real_payload_without_sending():
    channel = DryRunWhatsApp()
    channel.send("447700900000", OPENER)
    assert len(channel.sent) == 1
    assert channel.sent[0]["to"] == "447700900000"
    assert channel.sent[0]["type"] == "template"


def test_dry_run_renders_a_readable_transcript():
    channel = DryRunWhatsApp()
    channel.send("447700900000", OPENER)
    channel.send(
        "447700900000",
        ButtonMessage(body="Is your bedroom too hot?", buttons=question_buttons("q_b")),
    )
    transcript = channel.transcript()
    assert "climatise_checkin_opener" in transcript[0]
    assert "Is your bedroom too hot?" in transcript[1]
    assert "Not sure" in transcript[1]


def test_live_channel_refuses_to_construct_without_credentials(monkeypatch):
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="credentials are absent"):
        CloudApiWhatsApp()


def test_live_channel_refuses_a_recipient_not_on_the_allowlist():
    """SC-6. Valid credentials are not enough — the number must be listed too."""
    channel = CloudApiWhatsApp(
        phone_number_id="123", access_token="t", allowed_recipients=frozenset()
    )
    with pytest.raises(PermissionError, match="not on the allowlist"):
        channel.send("447700900000", OPENER)


def test_the_allowlist_is_empty_when_the_environment_says_nothing(monkeypatch):
    monkeypatch.delenv(ALLOW_REAL_SENDS_ENV, raising=False)
    assert CloudApiWhatsApp.allowlist_from_env() == frozenset()


def test_the_allowlist_parses_a_comma_separated_environment_variable(monkeypatch):
    monkeypatch.setenv(ALLOW_REAL_SENDS_ENV, "447700900000, 447700900001")
    assert CloudApiWhatsApp.allowlist_from_env() == {"447700900000", "447700900001"}
