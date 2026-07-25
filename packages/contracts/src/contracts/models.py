from dataclasses import dataclass, field
from datetime import date

from contracts.enums import (
    AgeBand,
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
