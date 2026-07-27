"""A red flag heard on a call, acted on immediately.

Until this existed, a completed check-in wrote its red flags to the log, said
something warm, and hung up. Nobody was contacted until the next sweep — three
hours away, or a whole day once the sweep runs on a daily cron. The one moment
the system is told directly that a person feels unwell was the one moment it
did nothing.

`test_a_recent_message_does_not_suppress_a_red_flag` is the one that matters.
The rest is plumbing; that one pins why this cannot simply reuse the ordinary
notification path.
"""

from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp

import pytest
from checkin.log import Channel, CheckinLog, CheckinRecord, Outcome
from contracts import Audience, Tier
from tests.scheduler.test_sweep import FixedWeather, RecordingChannel, sweep_with

T0 = datetime(2025, 7, 19, 21, 0, tzinfo=UTC)


def logged(red_flags: tuple[str, ...], person_id: str = "doris") -> CheckinLog:
    """A check-in already written, which is the state the voice service leaves
    behind before it asks for an escalation."""
    log = CheckinLog(Path(mkdtemp()) / "checkins.json")
    log.record(
        CheckinRecord(
            person_id=person_id,
            channel=Channel.VOICE,
            outcome=Outcome.COMPLETED,
            started_at=T0.isoformat(),
            completed_at=T0.isoformat(),
            red_flags=red_flags,
        )
    )
    return log


@pytest.fixture
def mild() -> FixedWeather:
    """Deliberately not hot. The red flag has to carry the escalation on its
    own, or this only ever fires on days the sweep would have caught anyway."""
    return FixedWeather(peak=21.0, indoor_night=19.0)


class TestSomebodyIsTold:
    def test_a_red_flag_reaches_the_caregiver(self, mild):
        channel = RecordingChannel()
        sweep = sweep_with(mild, channel, checkins=logged(("confusion",)))

        dispatch = sweep.escalate_now("doris", T0)

        assert dispatch is not None, "a reported red flag told nobody"
        assert dispatch.notification.audience is Audience.CAREGIVER
        assert channel.sent, "nothing actually left the building"

    def test_the_message_names_the_symptom(self, mild):
        """A caregiver reading "something is wrong" cannot triage it."""
        channel = RecordingChannel()
        sweep = sweep_with(mild, channel, checkins=logged(("confusion",)))
        sweep.escalate_now("doris", T0)

        _, message = channel.sent[0]
        assert message.is_bound

    def test_a_clean_check_in_tells_nobody(self, mild):
        """Answering the questions and being fine is the common case, and it
        must not page anyone."""
        channel = RecordingChannel()
        sweep = sweep_with(mild, channel, checkins=logged(()))

        assert sweep.escalate_now("doris", T0) is None
        assert not channel.sent

    def test_an_unknown_person_is_ignored_rather_than_raising(self, mild):
        """This runs in a background task after the response has gone, so an
        exception here would be a silent traceback rather than a failure."""
        sweep = sweep_with(mild, RecordingChannel(), checkins=logged((), "doris"))
        assert sweep.escalate_now("nobody-by-that-name", T0) is None


class TestTheRateLimitDoesNotApply:
    def test_a_recent_message_does_not_suppress_a_red_flag(self, mild):
        """The bug this exists to prevent.

        FR-22 allows one message per person per six hours, to stop repeated
        forecasts becoming noise a caregiver mutes. Applied here it would ration
        a person saying they feel unwell: somebody who got their morning
        Elevated message and reports new confusion at lunchtime has not changed
        tier and is inside the window, so the ordinary path stays silent.
        """
        channel = RecordingChannel()
        sweep = sweep_with(mild, channel, checkins=logged(("confusion",)))
        # As though the sweep messaged them minutes ago.
        state = sweep.policy.seen("doris")
        state.last_notified_tier = Tier.ELEVATED
        state.last_sent_at = T0

        # Establishes that the bypass is doing real work: routed through the
        # ordinary path, this person is silent at every tier.
        assert not sweep.policy.should_notify("doris", Tier.ELEVATED, T0)
        assert not sweep.policy.should_notify("doris", Tier.SEVERE, T0)

        assert sweep.escalate_now("doris", T0) is not None
        assert channel.sent, "the rate limit swallowed a red flag"

    def test_the_send_is_recorded_so_the_next_sweep_does_not_repeat_it(self, mild):
        """Bypassing the policy must not mean ignoring it — otherwise the sweep
        twenty minutes later says the same thing again."""
        sweep = sweep_with(mild, RecordingChannel(), checkins=logged(("confusion",)))
        sweep.escalate_now("doris", T0)

        assert sweep.policy.seen("doris").last_sent_at == T0
        assert not sweep.policy.should_notify("doris", Tier.LOW, T0)
