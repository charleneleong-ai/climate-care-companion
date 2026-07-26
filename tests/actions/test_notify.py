"""FR-21 and FR-22.

Both rules protect the signal rather than the message budget. The question is
never "did it send" but "would a caregiver still be reading these by Wednesday" —
and, just as importantly, "is there any escalation these rules would swallow".
"""

from datetime import UTC, datetime, timedelta

import pytest
from actions.notify import RATE_LIMIT, NotificationPolicy
from contracts import Audience, Tier

T0 = datetime(2025, 7, 19, 9, 0, tzinfo=UTC)
LATER = T0 + RATE_LIMIT + timedelta(minutes=1)
LONG_AGO = T0 - RATE_LIMIT * 2


@pytest.fixture
def policy() -> NotificationPolicy:
    return NotificationPolicy()


def told(policy: NotificationPolicy, tier: Tier, at: datetime = LONG_AGO) -> None:
    """Put Doris in the state of having actually been sent `tier`.

    Deliberately not `record_assessment`, which records what was *measured*. The
    distinction between those two is the subject of half this file.
    """
    policy.notifications_for("doris", tier, at)


class TestUpwardTransitions:
    """FR-21: rises are news, everything else is noise."""

    @pytest.mark.parametrize(
        ("last_told", "tier", "expected"),
        [
            (Tier.ELEVATED, Tier.HIGH, True),
            (Tier.HIGH, Tier.HIGH, False),
            (Tier.SEVERE, Tier.ELEVATED, False),
            # Nothing to compare against. Staying quiet because the system has
            # not met someone before is the wrong way to fail.
            (None, Tier.HIGH, True),
        ],
    )
    def test_only_a_rise_notifies(self, policy, last_told, tier, expected):
        if last_told is not None:
            told(policy, last_told)
        assert policy.should_notify("doris", tier, T0) is expected

    @pytest.mark.parametrize("last_told", [None, Tier.SEVERE])
    def test_low_never_notifies_however_it_was_reached(self, policy, last_told):
        """Telling someone nothing is wrong is how a system teaches people to
        ignore it."""
        if last_told is not None:
            told(policy, last_told)
        assert not policy.should_notify("doris", Tier.LOW, T0)

    def test_a_fall_is_remembered_so_a_later_reading_is_judged_against_it(self, policy):
        told(policy, Tier.SEVERE)
        policy.record_assessment("doris", Tier.LOW)
        assert policy.seen("doris").last_tier is Tier.LOW


class TestRateLimit:
    """FR-22: at most one message per person per six hours."""

    def test_a_second_rise_inside_the_window_is_suppressed(self, policy):
        told(policy, Tier.ELEVATED, T0)
        assert not policy.should_notify("doris", Tier.SEVERE, T0 + timedelta(hours=3))

    def test_a_suppressed_rise_is_deferred_not_deleted(self, policy):
        """The bug this guards, found in review and confirmed by execution.

        A Severe arriving inside the window used to advance the remembered tier
        even though nobody had been told. Once the window reopened, the escalation
        read as "no change" and was never sent at all — so a caregiver told
        "Elevated" at nine was never told it had become Severe. A rate limit is
        meant to delay a message, not delete one.
        """
        told(policy, Tier.ELEVATED, T0)
        policy.notifications_for("doris", Tier.SEVERE, T0 + timedelta(hours=3))

        sent = policy.notifications_for("doris", Tier.SEVERE, LATER)
        assert sent, "the escalation to Severe was lost rather than deferred"
        assert sent[0].to_tier is Tier.SEVERE

    def test_a_deferred_rise_reports_the_tier_they_last_actually_heard(self, policy):
        """Not the suppressed reading in between — the message describes the
        change from the reader's point of view, not the register's."""
        told(policy, Tier.ELEVATED, T0)
        policy.notifications_for("doris", Tier.SEVERE, T0 + timedelta(hours=3))

        sent = policy.notifications_for("doris", Tier.SEVERE, LATER)
        assert sent[0].from_tier is Tier.ELEVATED

    def test_the_limit_is_per_person_not_global(self, policy):
        """One busy household must not silence another."""
        told(policy, Tier.HIGH, T0)
        assert policy.should_notify("harold", Tier.HIGH, T0)


class TestAudiences:
    """One event, two voices."""

    def test_one_rise_produces_a_message_for_each_audience(self, policy):
        sent = policy.notifications_for("doris", Tier.HIGH, T0)
        assert {n.audience for n in sent} == {Audience.CAREGIVER, Audience.CARED_FOR}

    @pytest.mark.parametrize(
        ("last_told", "expected_from"), [(None, None), (Tier.ELEVATED, Tier.ELEVATED)]
    )
    def test_both_carry_the_transition_the_reader_experienced(
        self, policy, last_told, expected_from
    ):
        """A first message has no "since this morning" to refer to, and phrasing
        one as an escalation would invent a history."""
        if last_told is not None:
            told(policy, last_told)
        sent = policy.notifications_for("doris", Tier.SEVERE, T0)

        assert sent
        assert all(n.from_tier is expected_from for n in sent)
        assert all(n.is_first_ever is (expected_from is None) for n in sent)

    def test_a_suppressed_assessment_sends_nothing_but_is_still_recorded(self, policy):
        told(policy, Tier.HIGH, T0)
        assert policy.notifications_for("doris", Tier.ELEVATED, T0) == ()
        assert policy.seen("doris").last_tier is Tier.ELEVATED
