from datetime import UTC, datetime, timedelta

import pytest
from checkin.messages import ButtonMessage, TemplateMessage, encode_button_id
from checkin.questions import QuestionBank
from checkin.session import CheckinSession, SessionState
from checkin.twilio import DryRunTwilio
from contracts import Assessment, DateRange, Reason, ReasonCode, RedFlag, Tier
from datetime import date

T0 = datetime(2025, 7, 19, 18, 0, tzinfo=UTC)
WINDOW = DateRange(date(2025, 7, 19), date(2025, 7, 20))
OPENER = TemplateMessage(
    name="climatise_checkin_opener",
    language="en_GB",
    body="Hello. It is going to be hot tonight. Can we ask you a few quick questions?",
)


@pytest.fixture(scope="module")
def bank() -> QuestionBank:
    return QuestionBank.load()


def session(bank, tier=Tier.HIGH, *codes) -> CheckinSession:
    codes = codes or (ReasonCode.BEDROOM_WARM, ReasonCode.MED_DIURETIC)
    assessment = Assessment(
        tier=tier, risk_score=6.0, exposure_score=3, vulnerability_score=10,
        reasons=tuple(Reason(c, "t", "e", 1) for c in codes),
    )
    return CheckinSession(
        questionnaire=bank.build_for("doris", WINDOW, assessment), opener=OPENER
    )


# ------------------------------------------------- the template-first constraint

def test_the_first_message_is_always_the_approved_template(bank):
    """Meta permits no other way to open a business-initiated conversation."""
    assert isinstance(session(bank).next_message(T0), TemplateMessage)


def test_nothing_further_can_be_sent_until_they_reply(bank):
    """The 24-hour window opens on their reply, not on our send. Until then the
    session is stuck, which is the state a no-answer escalation fires from."""
    s = session(bank)
    s.record_sent(T0)
    assert s.state is SessionState.AWAITING_OPENER_REPLY
    assert s.next_message(T0 + timedelta(minutes=1)) is None


def test_a_reply_opens_the_window_and_releases_the_first_question(bank):
    s = session(bank)
    s.record_sent(T0)
    s.record_opener_acknowledged(T0 + timedelta(minutes=2))
    assert s.state is SessionState.IN_PROGRESS
    message = s.next_message(T0 + timedelta(minutes=2))
    assert isinstance(message, ButtonMessage)


def test_the_window_closes_after_twenty_four_hours_of_silence(bank):
    s = session(bank)
    s.record_sent(T0)
    s.record_opener_acknowledged(T0)
    assert s.window_open(T0 + timedelta(hours=23))
    assert not s.window_open(T0 + timedelta(hours=25))
    assert s.next_message(T0 + timedelta(hours=25)) is None


# ----------------------------------------------------------------- progression

def test_answers_advance_the_session_question_by_question(bank):
    s = session(bank)
    s.record_sent(T0)
    s.record_opener_acknowledged(T0)

    asked = []
    now = T0
    while (message := s.next_message(now)) is not None:
        assert isinstance(message, ButtonMessage)
        asked.append(message.body)
        now += timedelta(seconds=30)
        s.record_reply(message.buttons[0].id, now)

    assert len(asked) == len(s.questionnaire.questions)
    assert s.state is SessionState.COMPLETE


def test_a_late_reply_is_recorded_against_its_own_question_not_the_current_one(bank):
    """Replies arrive asynchronously and out of order. The button id carries the
    question, so a stale tap cannot be misfiled."""
    s = session(bank)
    s.record_sent(T0)
    s.record_opener_acknowledged(T0)
    first, second = s.questionnaire.questions[0], s.questionnaire.questions[1]

    s.record_reply(encode_button_id(second.code, True), T0 + timedelta(minutes=1))
    assert s.answers[second.code] is True
    assert first.code not in s.answers

    s.record_reply(encode_button_id(first.code, False), T0 + timedelta(minutes=2))
    assert s.answers[first.code] is False


def test_answering_out_of_order_still_completes(bank):
    s = session(bank)
    s.record_sent(T0)
    s.record_opener_acknowledged(T0)
    for question in reversed(s.questionnaire.questions):
        s.record_reply(encode_button_id(question.code, True), T0 + timedelta(minutes=1))
    assert s.state is SessionState.COMPLETE


# ---------------------------------------------------------------- the no answer

def test_silence_past_the_timeout_is_overdue(bank):
    """A check-in is about tonight, so silence becomes a signal well before
    WhatsApp's 24-hour window expires."""
    s = session(bank)
    s.record_sent(T0)
    assert not s.is_overdue(T0 + timedelta(minutes=10))
    assert s.is_overdue(T0 + timedelta(minutes=31))


def test_a_completed_session_is_never_overdue(bank):
    s = session(bank)
    s.record_sent(T0)
    s.record_opener_acknowledged(T0)
    for question in s.questionnaire.questions:
        s.record_reply(encode_button_id(question.code, True), T0)
    assert s.state is SessionState.COMPLETE
    assert not s.is_overdue(T0 + timedelta(days=2))


def test_an_unanswered_session_reports_as_unanswered(bank):
    s = session(bank)
    s.record_sent(T0)
    s.abandon()
    report = s.to_self_report()
    assert report.answered is False
    assert report.red_flags == ()


def test_a_partial_session_keeps_what_was_gathered(bank):
    """A red flag answered before they stopped replying matters as much as one in a
    completed run."""
    s = session(bank, Tier.HIGH, ReasonCode.AGE_85_PLUS)
    s.record_sent(T0)
    s.record_opener_acknowledged(T0)
    s.record_reply(encode_button_id("q_rf_urine", False), T0 + timedelta(minutes=1))
    s.abandon()

    report = s.to_self_report()
    assert report.answered is True
    assert RedFlag.NO_URINE_OUTPUT in report.red_flags


# ------------------------------------------------------------ end to end, dry run

def test_a_whole_check_in_runs_over_the_dry_run_channel(bank):
    s = session(bank)
    channel = DryRunTwilio()
    now = T0

    channel.send("447700900000", s.next_message(now))
    s.record_sent(now)
    now += timedelta(minutes=2)
    s.record_opener_acknowledged(now)

    while (message := s.next_message(now)) is not None:
        channel.send("447700900000", message)
        now += timedelta(seconds=30)
        s.record_reply(message.buttons[0].id, now)

    assert s.state is SessionState.COMPLETE
    assert channel.sent[0]["Body"] == OPENER.body
    assert all("Reply 1=Yes" in p["Body"] for p in channel.sent[1:])
    assert len(channel.sent) == len(s.questionnaire.questions) + 1
