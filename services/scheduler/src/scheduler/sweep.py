"""The only part of the system that initiates.

Everything else waits to be opened. A caregiver has to remember the app exists,
on the evening they are least likely to be thinking about it. §5.3 runs this
loop instead: score everyone on the register every three hours, and when someone's
tier rises, say so.

Two messages leave for every one rise, because a caregiver and the person they
look after need different sentences. The caregiver gets a name, a tier and the
single most specific action. The person gets no tier word at all — "Severe" read
alone on a phone frightens without telling anyone what to do — and a closing line
naming who to tell, because the failure mode for this group is not noticing and
not saying.

Wording never gets composed here. Both messages are pre-approved templates whose
one free slot is filled verbatim from the prevention plan, which has already been
through the SC-1 medication gate at corpus load.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from actions.checklist import PreventionPlanBuilder
from actions.escalation import Escalation, EscalationPolicy, Responder, Urgency
from actions.notify import Notification, NotificationPolicy
from checkin.channels import ConversationChannel
from checkin.log import CheckinLog
from checkin.log import Outcome as CheckinOutcome
from checkin.messages import TemplateLibrary, TemplateMessage
from contracts import (
    Assessment,
    DateRange,
    RedFlag,
    SelfReport,
    Audience,
    ExposureFeatures,
    Person,
    Place,
    PreventionPlan,
)
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from exposure.openmeteo import OpenMeteoClient
from persons.loader import PersonaLoader
from scheduler.contacts import Contact, ContactBook

TEMPLATE_BY_AUDIENCE = {
    Audience.CAREGIVER: "heat_alert_caregiver",
    Audience.CARED_FOR: "heat_alert_person",
}

FALLBACK_ACTION = {
    Audience.CAREGIVER: "check on them this evening.",
    Audience.CARED_FOR: "drink water regularly, even if you are not thirsty.",
}
"""Used only when the plan comes back with nothing addressed to that audience.

A tier rose, so silence is not an option — but inventing specific advice to fill
the gap would be composing clinical text, which is exactly what the template
mechanism exists to prevent. These two are deliberately the blandest true things
in the corpus.
"""


@dataclass(frozen=True, slots=True)
class Dispatch:
    """One message, sent or about to be. The audit trail for FR-21."""

    notification: Notification
    contact: Contact
    message: TemplateMessage
    plan: PreventionPlan


@dataclass(frozen=True, slots=True)
class SweepResult:
    at: datetime
    assessed: int
    dispatched: tuple[Dispatch, ...]
    unreachable: tuple[tuple[str, Audience], ...]
    """Rises that had no one to tell. Not an error — someone registered with no
    caregiver is the person the council view exists to find — but it must surface
    rather than vanish into a skipped iteration."""
    failed: tuple[tuple[str, str], ...] = ()
    """(person_id, reason) for anyone the sweep could not complete.

    Distinct from `unreachable`, which means "nobody to contact". This means the
    attempt itself broke — no forecast, a refused send — and the person's risk is
    therefore unknown rather than known-and-undeliverable.
    """

    @property
    def completed(self) -> int:
        return self.assessed - len(self.failed)


class HeatSweep:
    """One pass over the register.

    Holds the policy across passes, because "upward transition" is a claim about
    two assessments and the second one is three hours later.
    """

    def __init__(
        self,
        personas: PersonaLoader,
        weather: OpenMeteoClient,
        scorer: RiskScorer,
        planner: PreventionPlanBuilder,
        contacts: ContactBook,
        channel: ConversationChannel,
        vulnerability: VulnerabilityScorer | None = None,
        templates: TemplateLibrary | None = None,
        policy: NotificationPolicy | None = None,
        checkins: CheckinLog | None = None,
        escalation: EscalationPolicy | None = None,
        fallback_latlon: tuple[float, float] = (52.1364, -0.4669),
    ) -> None:
        self.personas = personas
        self.weather = weather
        self.scorer = scorer
        self.vulnerability = vulnerability or VulnerabilityScorer()
        self.planner = planner
        self.contacts = contacts
        self.channel = channel
        self.templates = templates or TemplateLibrary.load()
        self.policy = policy or NotificationPolicy()
        self.checkins = checkins or CheckinLog()
        self.escalation = escalation or EscalationPolicy()
        self.fallback_latlon = fallback_latlon

    def exposure_for(self, place: Place, when: datetime) -> ExposureFeatures:
        latitude = place.lat or self.fallback_latlon[0]
        longitude = place.lon or self.fallback_latlon[1]
        forecast = self.weather.fetch(latitude, longitude, when)
        return self.weather.features_for(forecast, when.date(), place.dwelling_offset)

    def run(self, now: datetime | None = None) -> SweepResult:
        """Assess everyone on the register, and tell whoever needs telling.

        Each person is isolated. The bug this prevents was live and confirmed by
        execution: `TwilioChannel.send` raises `PermissionError` for anyone off
        the SC-6 allow-list — which, in this build, is most of the register — so
        the first such person ended the evening's sweep for everyone after them
        in dict order. Nine people silently unassessed, and the result
        indistinguishable from "nothing to report".

        `WebPushChannel.send_to` already isolates per *device*. This is the same
        rule one level up, where it matters more.
        """
        now = now or datetime.now(UTC)
        people = self.personas.load()
        places = self.personas.places()
        dispatched: list[Dispatch] = []
        unreachable: list[tuple[str, Audience]] = []
        failed: list[tuple[str, str]] = []

        for person_id, person in people.items():
            try:
                dispatched.extend(self.sweep_person(person_id, person, places, now, unreachable))
            except Exception as exc:
                failed.append((person_id, f"{type(exc).__name__}: {exc}"))

        return SweepResult(
            at=now,
            assessed=len(people),
            dispatched=tuple(dispatched),
            unreachable=tuple(unreachable),
            failed=tuple(failed),
        )

    def sweep_person(
        self,
        person_id: str,
        person: Person,
        places: dict[str, Place],
        now: datetime,
        unreachable: list[tuple[str, Audience]],
    ) -> list[Dispatch]:
        exposure = self.exposure_for(places[person_id], now)
        assessment = self.scorer.assess(exposure, self.vulnerability.profile(person))
        sent: list[Dispatch] = []
        for notification in self.policy.notifications_for(person_id, assessment.tier, now):
            dispatch = self.dispatch(notification, person, exposure, assessment)
            if dispatch is None:
                unreachable.append((person_id, notification.audience))
            else:
                sent.append(dispatch)
        return sent

    def escalate_now(self, person_id: str, now: datetime | None = None) -> Dispatch | None:
        """A red flag heard on a call, acted on now rather than at the next sweep.

        The gap this closes: someone told the questionnaire they were confused
        and unsteady, heard the call end warmly, and nobody was contacted until
        the next pass — three hours away, or a day once the sweep runs on a
        daily cron. The one moment the system is told directly that something is
        wrong was the one moment it did nothing.

        **Deliberately bypasses `NotificationPolicy`.** FR-21 gates on an upward
        tier transition and FR-22 on a six-hour window, and a red flag is
        neither: somebody reporting new confusion an hour after their morning
        Elevated message has not changed tier, so both rules would suppress the
        most urgent thing this system ever hears. Rate limiting exists to stop
        repeated *forecasts* becoming noise, not to ration a person saying they
        feel unwell.

        The send is still recorded against the policy, so the sweep that runs
        twenty minutes later does not say the same thing again.

        Returns None when there is nobody to tell — a real state, and the case
        the council view exists to surface, not an error.
        """
        now = now or datetime.now(UTC)
        person = self.personas.load().get(person_id)
        if person is None:
            return None

        place = self.personas.places()[person_id]
        exposure = self.exposure_for(place, now)
        assessment = self.scorer.assess(exposure, self.vulnerability.profile(person))

        escalation = self.escalation_for(person, assessment)
        if escalation.responder is Responder.NOBODY:
            return None

        state = self.policy.seen(person_id)
        notification = Notification(
            person_id=person_id,
            audience=Audience.CAREGIVER,
            from_tier=state.last_notified_tier,
            to_tier=assessment.tier,
            at=now,
        )
        dispatch = self.dispatch(notification, person, exposure, assessment)
        if dispatch is not None:
            state.last_notified_tier = assessment.tier
            state.last_sent_at = now
            state.last_tier = assessment.tier
        return dispatch

    def dispatch(
        self,
        notification: Notification,
        person: Person,
        exposure: ExposureFeatures,
        assessment: Assessment,
    ) -> Dispatch | None:
        contact = self.contacts.get(notification.person_id, notification.audience)
        if contact is None:
            return None

        plan = self.planner.build(person, exposure, assessment, audience=notification.audience)
        escalation = self.escalation_for(person, assessment)
        message = self.bind(notification, person, plan, escalation)
        self.channel.send(contact.msisdn, message)
        return Dispatch(notification=notification, contact=contact, message=message, plan=plan)

    def escalation_for(self, person: Person, assessment: Assessment) -> Escalation:
        """What the latest check-in means, if anything.

        A person with no check-in history has no `SelfReport`, which is not the
        same as one who did not answer — so the policy is handed None and decides
        on the tier alone.
        """
        latest = self.checkins.latest_for(person.id)
        report: SelfReport | None = None
        if latest is not None:
            report = SelfReport(
                person_id=person.id,
                window=DateRange(start=latest_date(latest), end=latest_date(latest)),
                answered=latest.outcome is CheckinOutcome.COMPLETED,
                red_flags=tuple(RedFlag(f) for f in latest.red_flags),
            )
        has_caregiver = self.contacts.get(person.id, Audience.CAREGIVER) is not None
        return self.escalation.decide(
            person,
            assessment.tier,
            report,
            has_caregiver,
            self.checkins.consecutive_missed(person.id),
        )

    def bind(
        self,
        notification: Notification,
        person: Person,
        plan: PreventionPlan,
        escalation: Escalation,
    ) -> TemplateMessage:
        """Fill the one free slot from the plan, never from a sentence written here.

        When somebody has to attend, the caregiver gets that instead of the
        advice. A list of things to do is the wrong shape for "go round" — it
        invites the reader to do them remotely and feel they have responded.
        """
        if notification.audience is Audience.CAREGIVER and escalation.urgency is Urgency.EMERGENCY:
            return self.templates.get("escalation_emergency").bind(person.name, escalation.detail)
        if (
            notification.audience is Audience.CAREGIVER
            and escalation.needs_visit
            and escalation.responder is not Responder.NOBODY
        ):
            return self.templates.get("escalation_visit").bind(person.name, escalation.reason)

        template = self.templates.get(TEMPLATE_BY_AUDIENCE[notification.audience])
        action = plan.items[0].text if plan.items else FALLBACK_ACTION[notification.audience]
        if notification.audience is Audience.CAREGIVER:
            return template.bind(person.name, notification.to_tier.name.title(), action)
        return template.bind(person.name, action)


def next_sweep_at(now: datetime, every_hours: int = 3) -> datetime:
    """§5.3's three-hourly cadence, aligned to the clock rather than to start-up.

    An unaligned loop drifts, and a sweep that lands at 02:47 instead of midnight
    is one that missed the evening it was built for.
    """
    days, hour = divmod((now.hour // every_hours + 1) * every_hours, 24)
    return now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days)


def latest_date(record) -> date:
    """The day a check-in happened, for the SelfReport window.

    Parsed rather than assumed to be today: a sweep at one minute past midnight
    is reasoning about a call made the previous evening.
    """
    return datetime.fromisoformat(record.started_at).date()
