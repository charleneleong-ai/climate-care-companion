"""The push path, end to end, without a network or a clock.

The sweep is the only component that initiates, so its failure mode is silent:
nothing sends and nothing errors. These tests assert on what left the building.
"""

from datetime import UTC, datetime, timedelta

import pytest
from actions.checklist import PreventionPlanBuilder
from actions.interactions import InteractionTable
from checkin.messages import TemplateLibrary, TemplateMessage
from contracts import AlertLevel, Audience, ExposureFeatures, ExposureSource, Tier
from core.corpus import Corpus
from core.scoring import RiskScorer
from persons.loader import PersonaLoader
from scheduler.contacts import ContactBook
from scheduler.sweep import HeatSweep, next_sweep_at

T0 = datetime(2025, 7, 19, 18, 0, tzinfo=UTC)


class RecordingChannel:
    """A ConversationChannel that keeps what it was asked to send."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, TemplateMessage]] = []

    def send(self, to: str, message) -> str:
        self.sent.append((to, message))
        return f"stub-{len(self.sent)}"


class FixedWeather:
    """Returns the same exposure for everyone, so the only thing that varies
    between people is the person."""

    def __init__(self, peak: float, indoor_night: float) -> None:
        self.peak = peak
        self.indoor_night = indoor_night

    def fetch(self, lat: float, lon: float, when: datetime) -> object:
        return object()

    def features_for(self, forecast: object, day, offset: float) -> ExposureFeatures:
        return ExposureFeatures(
            date=day,
            overnight_min=self.peak - 12,
            peak_apparent=self.peak + 1,
            peak_air=self.peak,
            hours_above_26=8 if self.peak > 26 else 0,
            indoor_night_est=self.indoor_night + offset,
            indoor_day_est=self.peak + offset,
            spell_day=3,
            alert_level=AlertLevel.NONE,
            source=ExposureSource.LIVE,
        )


def sweep_with(weather: FixedWeather, channel: RecordingChannel) -> HeatSweep:
    corpus = Corpus.load()
    return HeatSweep(
        personas=PersonaLoader(),
        weather=weather,
        scorer=RiskScorer(corpus),
        planner=PreventionPlanBuilder(corpus, InteractionTable.load()),
        contacts=ContactBook.load(),
        channel=channel,
    )


@pytest.fixture
def hot() -> FixedWeather:
    return FixedWeather(peak=33.0, indoor_night=26.0)


@pytest.fixture
def mild() -> FixedWeather:
    return FixedWeather(peak=21.0, indoor_night=19.0)


def test_a_hot_evening_sends_to_both_audiences(hot):
    channel = RecordingChannel()
    result = sweep_with(hot, channel).run(T0)

    doris = [d for d in result.dispatched if d.notification.person_id == "doris"]
    assert {d.notification.audience for d in doris} == {
        Audience.CAREGIVER,
        Audience.CARED_FOR,
    }


def test_the_two_messages_are_different_text(hot):
    """The whole point of two audiences. If these ever converge, the second
    message is costing trust and adding nothing."""
    channel = RecordingChannel()
    sweep_with(hot, channel).run(T0)

    doris = [m for _, m in channel.sent if "Doris" in m.variables]
    assert len({m.body for m in doris}) == len(doris) > 1


def test_the_person_is_never_told_a_tier_word(hot):
    """ "Severe" read alone on a phone frightens without telling anyone what to do."""
    channel = RecordingChannel()
    result = sweep_with(hot, channel).run(T0)

    cared_for = [d for d in result.dispatched if d.notification.audience is Audience.CARED_FOR]
    # Without this the whole test goes green when the sweep dispatched nothing,
    # which is exactly what the two bugs above caused.
    assert cared_for
    for dispatch in cared_for:
        rendered = dispatch.message.body + " ".join(dispatch.message.variables)
        assert not any(t.name.title() in rendered for t in Tier)


def test_the_action_in_the_message_comes_from_the_plan(hot):
    """Not composed at send time. This is what keeps the SC-1 gate meaningful."""
    channel = RecordingChannel()
    result = sweep_with(hot, channel).run(T0)

    carried = [d for d in result.dispatched if d.plan.items]
    assert carried
    assert all(d.plan.items[0].text in d.message.variables for d in carried)


def test_a_mild_evening_sends_nothing(mild):
    channel = RecordingChannel()
    result = sweep_with(mild, channel).run(T0)

    assert result.assessed > 0
    assert result.dispatched == ()
    assert channel.sent == []


def test_the_second_sweep_of_the_same_evening_is_quiet(hot):
    """Nothing has changed by nine o'clock. FR-22 in the place it actually bites."""
    channel = RecordingChannel()
    sweep = sweep_with(hot, channel)
    sweep.run(T0)
    before = len(channel.sent)
    sweep.run(T0 + timedelta(hours=3))

    assert len(channel.sent) == before


def test_someone_with_no_caregiver_is_reported_not_skipped(hot):
    """Margaret has no caregiver row. That is the council's problem to see, not
    an iteration to swallow."""
    result = sweep_with(hot, RecordingChannel()).run(T0)

    assert ("margaret", Audience.CAREGIVER) in result.unreachable


def test_the_alert_templates_declare_the_variables_the_sweep_binds():
    """Guards the seam between the yaml and the binder — a renamed variable there
    surfaces here rather than at send time."""
    library = TemplateLibrary.load()
    assert library.get("heat_alert_caregiver").variable_names == (
        "cared_for_name",
        "tier",
        "first_action",
    )
    assert library.get("heat_alert_person").variable_names == ("first_name", "first_action")


@pytest.mark.parametrize(
    ("now", "expected_hour", "expected_day"),
    [
        (datetime(2025, 7, 19, 18, 5, tzinfo=UTC), 21, 19),
        (datetime(2025, 7, 19, 21, 0, tzinfo=UTC), 0, 20),
        (datetime(2025, 7, 19, 23, 59, tzinfo=UTC), 0, 20),
    ],
)
def test_sweeps_align_to_the_clock_and_roll_over_midnight(now, expected_hour, expected_day):
    """An unaligned loop drifts, and a sweep at 02:47 missed the evening it was
    built for."""
    nxt = next_sweep_at(now)
    assert (nxt.hour, nxt.day) == (expected_hour, expected_day)


# ────────────────────────── one person's failure must not become everyone's


class Refusing:
    """Raises for one recipient, records the rest.

    Models the live channels: TwilioChannel raises PermissionError for anyone off
    the SC-6 allow-list, which in this build is most of the register.
    """

    def __init__(self, refuse_name: str) -> None:
        self.refuse_name = refuse_name
        self.sent: list[str] = []

    def send(self, to: str, message) -> str:
        if to.endswith(self.refuse_name):
            raise PermissionError(f"{to} is not on the allowlist")
        self.sent.append(to)
        return "ok"


def first_contact_number() -> str:
    """The number the first persona in sweep order would be messaged on."""
    people = PersonaLoader().load()
    contacts = ContactBook.load()
    for person_id in people:
        contact = contacts.get(person_id, Audience.CAREGIVER)
        if contact:
            return contact.msisdn
    raise AssertionError("no persona has a caregiver contact")


def test_a_refused_send_does_not_abort_the_sweep(hot):
    """The live bug, confirmed by execution: an unguarded channel.send inside the
    per-person loop meant the first un-allowlisted caregiver ended the evening's
    sweep for everyone after them — nine people silently unassessed, and the
    result indistinguishable from "nothing to report"."""
    channel = Refusing(first_contact_number()[-4:])
    result = sweep_with(hot, channel).run(T0)

    assert result.assessed > 1
    assert channel.sent, "the sweep stopped at the first refusal"
    assert result.dispatched, "nobody after the failure was reached"


def test_a_failure_is_reported_rather_than_silently_skipped(hot):
    """Unreachable means "nobody to contact". Failed means the attempt broke and
    that person's risk is unknown — the two must not be conflated."""
    channel = Refusing(first_contact_number()[-4:])
    result = sweep_with(hot, channel).run(T0)

    assert result.failed, "the refusal vanished"
    assert result.completed < result.assessed


def test_a_broken_forecast_for_one_person_does_not_stop_the_others(hot):
    """LookupError is what OpenMeteoClient raises with no live call and no cache."""

    class OneBadForecast(FixedWeather):
        def __init__(self, inner: FixedWeather, bad_offset: float) -> None:
            super().__init__(inner.peak, inner.indoor_night)
            self.bad_offset = bad_offset

        def features_for(self, forecast, day, offset: float):
            if offset == self.bad_offset:
                raise LookupError("no forecast and nothing cached")
            return super().features_for(forecast, day, offset)

    offsets = {p.dwelling_offset for p in PersonaLoader().places().values()}
    weather = OneBadForecast(hot, sorted(offsets)[0])
    result = sweep_with(weather, RecordingChannel()).run(T0)

    assert result.failed
    assert result.completed > 0, "one missing forecast stopped the whole register"
