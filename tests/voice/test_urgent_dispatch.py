"""The call hangs up and somebody gets told.

The wiring between "a red flag was heard" and "a caregiver was contacted" is
easy to get subtly wrong in a way nothing surfaces: the caller still hears a
warm closing line either way, and the log entry is written either way. These
tests assert on the one observable difference — whether a dispatch was
scheduled.
"""

from pathlib import Path
from tempfile import mkdtemp

import pytest
from checkin.log import CheckinLog, Outcome
from fastapi.testclient import TestClient

from tests.scheduler.test_sweep import FixedWeather

from voice import main as voice


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """A fresh log, and weather hot enough that there are questions to ask.

    The weather is injected rather than simulated through the environment:
    `SIMULATE_PEAK` is read once at import, so setting the variable from a test
    does nothing and every test here silently skipped. It also removes a live
    Open-Meteo call from the suite, which made these tests slow and dependent on
    what the actual forecast happened to be.

    The log is fresh because otherwise the suite reads whatever manual testing
    left in /tmp, where one stale red flag makes every assertion here pass.
    """
    monkeypatch.setattr(voice, "CHECKINS", CheckinLog(Path(mkdtemp()) / "checkins.json"))
    monkeypatch.setattr(voice, "WEATHER", FixedWeather(peak=34.0, indoor_night=27.0))
    voice.CALLS.clear()
    yield


@pytest.fixture
def escalated(monkeypatch) -> list[str]:
    """Records who an escalation was requested for, without building a sweep."""
    asked: list[str] = []
    monkeypatch.setattr(voice, "escalate", asked.append)
    return asked


@pytest.fixture
def client() -> TestClient:
    return TestClient(voice.app)


def answer_every_question(client: TestClient, call_sid: str, *, concerning: bool) -> None:
    """Walk the questionnaire to the end, which is what triggers the record.

    Each answer is derived from that question's own `red_flag_when` rather than
    being a fixed "yes" or "no", because the polarity differs per question: for
    "is your bedroom too hot" the flag is *yes*, and for "can you get yourself a
    drink" it is *no*. An earlier version of this answered "no" throughout and
    called that the reassuring case, which in fact tripped several flags.
    """
    state = voice.CALLS[call_sid]
    for index, question in enumerate(state.questionnaire.questions):
        if question.red_flag is None:
            answer = False
        else:
            # Answering `red_flag_when` is precisely what trips the flag.
            answer = question.red_flag_when if concerning else not question.red_flag_when
        client.post(
            f"/voice/answer?q={index}",
            data={"CallSid": call_sid, "SpeechResult": "yes" if answer else "no"},
        )


def start_call(client: TestClient, call_sid: str = "CA-test") -> bool:
    """Begin a call, returning whether there was anything to ask.

    With the weather fixed hot above there always is, so a false here means the
    questionnaire stopped being generated rather than that today was mild.
    """
    client.post("/voice/checkin", data={"CallSid": call_sid})
    state = voice.CALLS.get(call_sid)
    return state is not None and bool(state.questionnaire.questions)


class TestARedFlagIsActedOn:
    def test_a_concerning_answer_dispatches(self, client, escalated):
        assert start_call(client), "hot weather produced no questions to ask"

        answer_every_question(client, "CA-test", concerning=True)

        assert escalated == ["doris"], "a reported red flag scheduled no escalation"

    def test_a_reassuring_check_in_dispatches_nothing(self, client, escalated):
        assert start_call(client), "hot weather produced no questions to ask"

        answer_every_question(client, "CA-test", concerning=False)

        assert escalated == [], "a clean check-in paged somebody"

    def test_the_check_in_is_recorded_either_way(self, client, escalated):
        """The escalation reads the log entry, so the write has to happen first
        and has to happen regardless of the answers."""
        assert start_call(client), "hot weather produced no questions to ask"

        answer_every_question(client, "CA-test", concerning=False)

        assert voice.CHECKINS.for_person("doris"), "the call left no record"


def test_a_failing_escalation_never_reaches_the_caller(monkeypatch, capsys):
    """It runs after the response has gone, so raising would be an invisible
    traceback rather than an error anyone sees."""

    def explode(_person_id: str):
        raise RuntimeError("no contact book")

    monkeypatch.setattr(voice, "URGENT", type("S", (), {"escalate_now": explode})())
    voice.escalate("doris")

    assert "failed" in capsys.readouterr().out


class TestSilenceIsActedOnToo:
    """A missed call was recorded and then waited for the sweep.

    That made silence the slowest signal in the system — three hours, and a
    whole day once the sweep runs on a daily cron — when it is the one the
    escalation ladder was built for. Nobody knows how the person is, and the
    reasons someone does not answer overlap heavily with the reasons to worry.
    """

    def test_an_unanswered_call_escalates_immediately(self, client, escalated):
        client.post("/voice/status", data={"CallSid": "CA-missed", "CallStatus": "no-answer"})
        assert escalated == ["doris"], "a missed call told nobody until the next sweep"

    def test_it_is_recorded_before_it_is_escalated(self, client, escalated):
        """The escalation reads the log entry, so a dispatch that fires first
        judges the person on their previous call rather than this one."""
        client.post("/voice/status", data={"CallSid": "CA-missed", "CallStatus": "no-answer"})
        latest = voice.CHECKINS.latest_for("doris")
        assert latest is not None and latest.outcome is Outcome.NO_ANSWER

    def test_a_completed_call_does_not_escalate_twice(self, client, escalated):
        """The answer handler already recorded and escalated it. Twilio still
        sends a status callback afterwards, and acting on both would double
        every alert."""
        assert start_call(client), "hot weather produced no questions to ask"
        answer_every_question(client, "CA-test", concerning=True)
        before = list(escalated)

        client.post("/voice/status", data={"CallSid": "CA-test", "CallStatus": "completed"})

        assert escalated == before, "the status callback re-escalated a finished call"


class TestAnAbandonedCallKeepsWhatItHeard:
    def test_red_flags_survive_the_line_dropping(self, client, escalated):
        """Someone who says they are confused and then loses the call had that
        answer stored and never read as a flag: only the completed path derived
        them. The record looked whole, which is what made it dangerous."""
        assert start_call(client), "hot weather produced no questions to ask"
        state = voice.CALLS["CA-test"]
        flagged = next(q for q in state.questionnaire.questions if q.red_flag is not None)
        client.post(
            "/voice/answer?q=" + str(state.questionnaire.questions.index(flagged)),
            data={"CallSid": "CA-test", "SpeechResult": "yes" if flagged.red_flag_when else "no"},
        )

        client.post("/voice/status", data={"CallSid": "CA-test", "CallStatus": "completed"})

        latest = voice.CHECKINS.latest_for("doris")
        assert latest is not None
        assert latest.outcome is Outcome.ABANDONED
        assert latest.red_flags, "a red flag heard before the drop was discarded"
