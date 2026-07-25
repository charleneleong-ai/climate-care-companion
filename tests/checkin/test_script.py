import pytest
from checkin.script import CheckinScript
from checkin.voice import ConsoleVoice, VoiceChannel
from contracts import Assessment, Reason, ReasonCode, Tier
from core.corpus import Corpus


@pytest.fixture(scope="module")
def script() -> CheckinScript:
    return CheckinScript(Corpus.load())


def assessment(tier: Tier, *codes: ReasonCode) -> Assessment:
    return Assessment(
        tier=tier, risk_score=6.0, exposure_score=3, vulnerability_score=10,
        reasons=tuple(Reason(c, "t", "e", 1) for c in codes),
    )


def test_low_tier_places_no_call(script):
    """Ringing someone to say nothing is wrong is how a system trains people to
    ignore it."""
    assert script.utterances_for(assessment(Tier.LOW, ReasonCode.MED_DIURETIC)) == ()


def test_no_utterance_repeats_within_one_call(script):
    said = script.utterances_for(
        assessment(Tier.HIGH, ReasonCode.MED_DIURETIC, ReasonCode.MED_LITHIUM)
    )
    assert len(said) == len(set(said))


def test_rows_above_the_callers_tier_are_not_read(script):
    elevated = script.utterances_for(assessment(Tier.ELEVATED, ReasonCode.BEDROOM_UNSAFE))
    high = script.utterances_for(assessment(Tier.HIGH, ReasonCode.BEDROOM_UNSAFE))
    assert set(elevated) < set(high), "a high-tier row surfaced on an elevated call"


def test_utterances_follow_the_corpus_ordering_column(script):
    said = script.utterances_for(
        assessment(Tier.SEVERE, ReasonCode.MED_LITHIUM, ReasonCode.MED_DIURETIC)
    )
    lithium = next(r for r in script.corpus.actions
                   if r.reason_code is ReasonCode.MED_LITHIUM)
    assert said[0] == lithium.text, "lowest ordering must be spoken first"


def test_unrelated_reason_codes_are_not_read(script):
    said = script.utterances_for(assessment(Tier.HIGH, ReasonCode.MED_DIURETIC))
    lithium = next(r for r in script.corpus.actions
                   if r.reason_code is ReasonCode.MED_LITHIUM)
    assert lithium.text not in said


def test_console_voice_satisfies_the_channel_protocol():
    assert isinstance(ConsoleVoice(), VoiceChannel)


@pytest.mark.parametrize(
    "reply,expected",
    [("yes", True), ("Yes", True), (" y ", True), ("no", False), ("nope", False),
     ("mmm", None), ("", None)],
)
def test_unrecognised_reply_is_none_never_free_text(reply, expected):
    assert ConsoleVoice(replies=[reply]).ask("Is your bedroom warm?") is expected


def test_console_voice_records_a_transcript():
    voice = ConsoleVoice(replies=["yes"])
    voice.say("Open the windows after sunset.")
    voice.ask("Is your bedroom warm?")
    assert len(voice.transcript) == 2
