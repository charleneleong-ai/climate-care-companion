"""What the sweep has to remember between runs.

FR-21 sends on an upward transition and FR-22 allows one message per person per
six hours. Both are claims about two assessments, so both are answered from
state the previous run left behind. A long-running process keeps that in memory
and never notices the dependency; a cron invocation is a new process every time,
so without persistence every sweep is a first sweep — the whole register reads
as a fresh rise and gets re-alerted on every pass.

That is the cry-wolf failure the rules exist to prevent, and a caregiver's
response to it is to mute the system, which is worse than not having one.
"""

from datetime import UTC, datetime, timedelta

import pytest
from actions.notify import NotificationPolicy
from checkin.storage import FileFields
from contracts import Tier
from scheduler.build import load_policy, save_policy

MONDAY = datetime(2025, 7, 19, 9, 0, tzinfo=UTC)


@pytest.fixture
def backend(tmp_path) -> FileFields:
    return FileFields(tmp_path / "notify.json")


def told(policy: NotificationPolicy, person_id: str, tier: Tier, when: datetime) -> None:
    """Assess and dispatch, which is what a sweep does per person."""
    policy.notifications_for(person_id, tier, when)


class TestTheNextRunRemembers:
    def test_a_person_already_told_is_not_told_again(self, backend):
        first = NotificationPolicy()
        told(first, "doris", Tier.HIGH, MONDAY)
        save_policy(first, backend)

        # A new process, seven hours later — past the rate limit, so only the
        # remembered tier can suppress this.
        revived = load_policy(backend)
        assert not revived.should_notify("doris", Tier.HIGH, MONDAY + timedelta(hours=7))

    def test_a_genuine_rise_still_gets_through(self, backend):
        first = NotificationPolicy()
        told(first, "doris", Tier.HIGH, MONDAY)
        save_policy(first, backend)

        revived = load_policy(backend)
        assert revived.should_notify("doris", Tier.SEVERE, MONDAY + timedelta(hours=7))

    def test_the_rate_limit_survives_too(self, backend):
        """Otherwise a restart is a way to bypass FR-22 — and a crash loop
        becomes a way to text somebody every few minutes."""
        first = NotificationPolicy()
        told(first, "doris", Tier.HIGH, MONDAY)
        save_policy(first, backend)

        revived = load_policy(backend)
        assert not revived.should_notify("doris", Tier.SEVERE, MONDAY + timedelta(hours=1))

    def test_someone_never_seen_is_still_notified(self, backend):
        """Failing quiet for an unknown person is the wrong way to fail."""
        told(NotificationPolicy(), "doris", Tier.HIGH, MONDAY)
        assert load_policy(backend).should_notify("victor", Tier.HIGH, MONDAY)


class TestTheStateItselfRoundTrips:
    def test_a_fall_is_remembered_as_well_as_a_rise(self, backend):
        policy = NotificationPolicy()
        told(policy, "doris", Tier.SEVERE, MONDAY)
        policy.record_assessment("doris", Tier.LOW)
        save_policy(policy, backend)

        revived = load_policy(backend)
        assert revived.seen("doris").last_tier is Tier.LOW
        assert revived.seen("doris").last_notified_tier is Tier.SEVERE

    def test_tiers_are_stored_by_name_not_ordinal(self, backend):
        """A stored ordinal silently becomes a different severity the day
        somebody inserts a tier in the middle of the enum."""
        policy = NotificationPolicy()
        told(policy, "doris", Tier.HIGH, MONDAY)
        save_policy(policy, backend)

        assert backend.all()["doris"]["last_notified_tier"] == "HIGH"

    def test_an_empty_store_loads_an_empty_policy(self, backend):
        assert load_policy(backend).state == {}
