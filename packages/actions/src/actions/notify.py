"""When to tell someone, and when to say nothing.

FR-21 dispatches on an **upward tier transition only**. FR-22 allows at most one
notification per person per six hours. Both rules exist to protect the signal
rather than to save messages: a system that texts every three hours is one a
caregiver mutes by Wednesday, and a muted system has a worse false-negative rate
than no system at all.

The asymmetry is deliberate. Going up is news and gets sent. Going down is not,
and staying put is not — someone who has been High since lunchtime does not need
telling again at four.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from contracts import Audience, Tier

RATE_LIMIT = timedelta(hours=6)
"""FR-22. Long enough not to pester, short enough that a morning Elevated and an
evening Severe arrive as two separate messages."""


@dataclass(frozen=True, slots=True)
class Notification:
    person_id: str
    audience: Audience
    from_tier: Tier | None
    to_tier: Tier
    at: datetime

    @property
    def is_first_ever(self) -> bool:
        return self.from_tier is None


@dataclass(slots=True)
class PersonState:
    """What this person was last assessed at, and what they were last told.

    The two are separate because they diverge, and the divergence is the whole
    point: an assessment the rate limit suppressed happened, but nobody heard it.
    Measuring the next rise against what was *assessed* rather than what was
    *said* is how a suppressed escalation gets deleted instead of deferred.
    """

    last_tier: Tier | None = None
    """The most recent assessment, notified or not. Kept so a fall is remembered."""
    last_notified_tier: Tier | None = None
    """The tier the person was actually told about. Rises are measured from here."""
    last_sent_at: datetime | None = None


@dataclass(slots=True)
class NotificationPolicy:
    """Decides whether an assessment is worth interrupting someone for.

    Holds the previous tier per person, because "upward transition" is a claim
    about two assessments and cannot be answered from one. In memory for the
    scaffold; the surface is small enough that a durable store is a drop-in.
    """

    state: dict[str, PersonState] = field(default_factory=dict)

    def seen(self, person_id: str) -> PersonState:
        return self.state.setdefault(person_id, PersonState())

    def rate_limited(self, person_id: str, now: datetime) -> bool:
        last = self.seen(person_id).last_sent_at
        return last is not None and now - last < RATE_LIMIT

    def should_notify(self, person_id: str, tier: Tier, now: datetime) -> bool:
        """FR-21 and FR-22 together.

        The comparison is against the last tier the person was *told*, not the
        last one assessed. Otherwise a rise that FR-22 suppressed still advances
        the baseline, and once the window reopens the escalation reads as "no
        change" and is never sent at all — the rate limit would delete a warning
        rather than delay it.

        A first assessment above Low counts as a rise. There is nothing to
        compare against, and staying quiet because the system has not met
        someone before is the wrong way to fail.
        """
        if tier is Tier.LOW:
            return False
        told = self.seen(person_id).last_notified_tier
        rising = told is None or tier > told
        return rising and not self.rate_limited(person_id, now)

    def record_assessment(self, person_id: str, tier: Tier) -> None:
        """Called on every assessment, notified or not.

        A tier that fell still has to be remembered, or a later reading is judged
        against a level the person is no longer at.
        """
        self.seen(person_id).last_tier = tier

    def notifications_for(
        self,
        person_id: str,
        tier: Tier,
        now: datetime,
        audiences: tuple[Audience, ...] = (Audience.CAREGIVER, Audience.CARED_FOR),
    ) -> tuple[Notification, ...]:
        """One event, one message per audience.

        The caregiver and the cared-for person are messaged separately because
        they are told different things, not the same thing twice — see the two
        voices carried by every interaction rule.
        """
        state = self.seen(person_id)
        sending = self.should_notify(person_id, tier, now)
        # Recorded either way: the assessment happened whether or not it was sent.
        state.last_tier = tier
        if not sending:
            return ()

        # `from_tier` is what they last heard, so the message describes the change
        # from their point of view rather than from the register's.
        from_tier = state.last_notified_tier
        state.last_notified_tier = tier
        state.last_sent_at = now
        return tuple(
            Notification(
                person_id=person_id,
                audience=audience,
                from_tier=from_tier,
                to_tier=tier,
                at=now,
            )
            for audience in audiences
        )
