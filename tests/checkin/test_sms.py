import pytest
from checkin.messages import (
    ButtonMessage,
    TemplateMessage,
    decode_button_id,
    question_buttons,
)
from checkin.sms import REPLY_TOKENS, SmsFormatter

QUESTION = ButtonMessage(
    body="Is your bedroom too hot?", buttons=question_buttons("q_bedroom_warm")
)
OPENER = TemplateMessage(
    name="climatise_checkin_opener",
    language="en_GB",
    body="Hello {{1}}. It will be hot tonight. Reply to this message.",
    variable_names=("first_name",),
).bind("Doris")


# ------------------------------------------------------------------ rendering


def test_a_question_renders_with_numbered_options():
    """SMS has no buttons, so the options have to be in the text."""
    text = SmsFormatter.render(QUESTION)
    assert "Is your bedroom too hot?" in text
    assert "1=Yes" in text and "2=No" in text and "3=Not sure" in text


def test_a_template_renders_with_variables_substituted():
    assert SmsFormatter.render(OPENER) == (
        "Hello Doris. It will be hot tonight. Reply to this message."
    )


def test_a_rendered_question_fits_in_one_or_two_segments():
    assert SmsFormatter.segments(SmsFormatter.render(QUESTION)) <= 2


def test_an_over_long_message_is_rejected_rather_than_fragmented():
    """An older handset may show fragments out of order, which turns a question
    into nonsense."""
    long_question = ButtonMessage(body="x" * 400, buttons=question_buttons("q_x"))
    with pytest.raises(ValueError, match="segments"):
        SmsFormatter.check_length(SmsFormatter.render(long_question))


# -------------------------------------------------------------- reply parsing


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("yes", True),
        ("YES", True),
        ("y", True),
        ("1", True),
        (" Yeah ", True),
        ("no", False),
        ("N", False),
        ("2", False),
        ("nope.", False),
        ("unsure", None),
        ("3", None),
        ("dunno", None),
    ],
)
def test_replies_map_onto_the_closed_answer_set(reply, expected):
    button_id = SmsFormatter.parse_reply(reply, "q_bedroom_warm")
    code, answer = decode_button_id(button_id)
    assert code == "q_bedroom_warm"
    assert answer is expected


@pytest.mark.parametrize("reply", ["maybe later", "", "stop", "who is this"])
def test_an_unrecognised_reply_is_not_an_answer(reply):
    """Same rule as the voice channel: confusion is escalated, never interpreted."""
    assert SmsFormatter.parse_reply(reply, "q_bedroom_warm") is None


def test_numeric_replies_match_the_displayed_option_order():
    """1/2/3 in the text must mean the same as 1/2/3 in the parser."""
    rendered = SmsFormatter.render(QUESTION)
    for position, expected in ((1, True), (2, False), (3, None)):
        title = {True: "Yes", False: "No", None: "Not sure"}[expected]
        assert f"{position}={title}" in rendered
        _, answer = decode_button_id(SmsFormatter.parse_reply(str(position), "q_x"))
        assert answer is expected
