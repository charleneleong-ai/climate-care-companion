from dataclasses import dataclass, field
from datetime import date

from contracts.enums import (
    AdviceSource,
    AgeBand,
    Audience,
    AlertLevel,
    Aspect,
    Condition,
    DwellingType,
    ExposureSource,
    MedClass,
    ReasonCode,
    RedFlag,
    Tier,
)


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class Med:
    drug_name: str
    drug_class: MedClass


@dataclass(frozen=True, slots=True)
class Person:
    id: str
    name: str
    age_band: AgeBand
    lives_alone: bool
    mobility_limited: bool
    conditions: tuple[Condition, ...] = field(default=())
    medications: tuple[Med, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class Place:
    person_id: str
    postcode: str
    lat: float
    lon: float
    admin_district: str
    region: str
    dwelling_type: DwellingType
    floor: int
    aspect: Aspect
    has_cooling: bool
    heating_affordable: bool
    dwelling_offset: float


@dataclass(frozen=True, slots=True)
class ExposureFeatures:
    """L1 to L3. The only thing the scoring core knows about weather."""

    date: date
    overnight_min: float
    peak_apparent: float
    peak_air: float
    hours_above_26: int
    indoor_night_est: float
    """Modelled, not measured. Label as modelled wherever displayed (SC-5)."""
    indoor_day_est: float
    """Modelled, not measured. Label as modelled wherever displayed (SC-5)."""
    spell_day: int
    alert_level: AlertLevel
    source: ExposureSource


@dataclass(frozen=True, slots=True)
class Reason:
    code: ReasonCode
    title: str
    explanation: str
    weight: int


@dataclass(frozen=True, slots=True)
class VulnerabilityProfile:
    person_id: str
    score: int
    codes: tuple[ReasonCode, ...]


@dataclass(frozen=True, slots=True)
class Assessment:
    """L3 output.

    AC-2: the reasons array is the system of record for explanation. Nothing
    downstream re-derives risk from raw exposure.
    """

    tier: Tier
    risk_score: float
    exposure_score: int
    vulnerability_score: int
    reasons: tuple[Reason, ...]


@dataclass(frozen=True, slots=True)
class SelfReport:
    """Voice check-in outcome.

    Never enters risk fusion. A hot-bedroom answer corrects the modelled indoor
    estimate at L1; red flags and no-answer escalate at L4 (spec section 6).
    """

    person_id: str
    window: DateRange
    answered: bool
    bedroom_feels_hot: bool | None = None
    drinking_fluids: bool | None = None
    red_flags: tuple[RedFlag, ...] = field(default=())
    transcript_ref: str | None = None
    """A pointer, never transcript content. Recording a vulnerable person's voice
    is health and plausibly biometric data — out of scope until the DPIA (SC-6)."""


@dataclass(frozen=True, slots=True)
class AdviceItem:
    """One piece of advice, already in the voice of its audience.

    `text` and `watch_for` are deliberately separate. What to do and what to look
    out for are different instructions, and for some combinations the watch-for is
    the more important of the two — an anticholinergic suppresses sweating, so the
    usual first warning of overheating is absent rather than late.
    """

    code: str
    text: str
    watch_for: str | None
    escalate_to: str | None
    source: AdviceSource
    audience: Audience


@dataclass(frozen=True, slots=True)
class PreventionPlan:
    """What to do before the heat arrives, for one person and one audience.

    Prevention rather than response: it is built from a forecast warning with lead
    time attached, so the instructions are things that can still be done in advance
    — moving insulin off a windowsill, settling a fluid amount with the GP, cooling
    a room before the peak. An instruction that only makes sense once someone is
    already unwell belongs in the escalation ladder, not here.
    """

    person_id: str
    tier: Tier
    audience: Audience
    items: tuple[AdviceItem, ...]
    lead_time_hours: int = 0
    """Hours until the episode threshold is met. Zero means it is already here, and
    the plan is being read too late to prevent anything."""
    expected_peak: float | None = None
    alert_level: AlertLevel = AlertLevel.NOT_CHECKED
    """The regional warning, if any. Deliberately not a gate — the whole product
    argument is that personal risk is computed whether or not a region is alerted."""

    @property
    def is_preventive(self) -> bool:
        return self.lead_time_hours > 0

    @property
    def watch_points(self) -> tuple[str, ...]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in self.items:
            if item.watch_for and item.watch_for not in seen:
                seen.add(item.watch_for)
                ordered.append(item.watch_for)
        return tuple(ordered)

    @property
    def interactions(self) -> tuple[AdviceItem, ...]:
        """Advice that exists only because of a combination."""
        return tuple(i for i in self.items if i.source is AdviceSource.INTERACTION)

    def escalation_targets(self) -> tuple[str, ...]:
        return tuple(sorted({i.escalate_to for i in self.items if i.escalate_to}))
