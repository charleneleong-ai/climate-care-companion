"""Spec 8.1 and 8.2 as declarative data.

Every threshold is a value on a dataclass, not a number buried in a lambda. That
matters for two reasons beyond tidiness:

- The tables can be diffed line by line against the specification during review.
- They can be **exported**. The companion at web/companion scores in JavaScript so
  it works with no backend (NFR-04), which means L3 exists twice — the thing AC-1
  and AC-5 exist to prevent. Declarative rules let both engines read one generated
  source, so the constants cannot drift even though the code is duplicated.

See core.export and docs/deviations.md.
"""

from dataclasses import dataclass
from enum import StrEnum, auto

from contracts import AgeBand, Condition, ExposureFeatures, MedClass, Person, ReasonCode

HEATING_DAY_MAX = 18.0
"""COLD_GUARD. Above this outdoor peak a cold-code trigger is an artefact of the
FR-11 formula rather than a cold home — see docs/deviations.md."""


@dataclass(frozen=True, slots=True)
class Bound:
    """One numeric constraint on an ExposureFeatures field.

    `minimum` is inclusive and `maximum` exclusive, which is how section 8.1 states
    its bands: `24 <= indoor_night < 26`.
    """

    field: str
    minimum: float | None = None
    maximum: float | None = None

    def holds(self, exposure: ExposureFeatures) -> bool:
        value = getattr(exposure, self.field)
        if self.minimum is not None and value < self.minimum:
            return False
        return not (self.maximum is not None and value >= self.maximum)


@dataclass(frozen=True, slots=True)
class ExposureRule:
    code: ReasonCode
    bounds: tuple[Bound, ...]
    """Every bound must hold. An empty tuple would always fire, so there are none."""
    weight: int

    def applies(self, exposure: ExposureFeatures) -> bool:
        return all(bound.holds(exposure) for bound in self.bounds)


class VulnKind(StrEnum):
    AGE_BAND = auto()
    FLAG = auto()
    """A boolean attribute on Person — lives_alone, mobility_limited."""
    CONDITION = auto()
    MED_CLASS = auto()


@dataclass(frozen=True, slots=True)
class VulnerabilityRule:
    code: ReasonCode
    kind: VulnKind
    value: str
    weight: int

    def applies(self, person: Person) -> bool:
        match self.kind:
            case VulnKind.AGE_BAND:
                return person.age_band == self.value
            case VulnKind.FLAG:
                return bool(getattr(person, self.value))
            case VulnKind.CONDITION:
                return Condition(self.value) in person.conditions
            case VulnKind.MED_CLASS:
                return any(
                    med.drug_class == MedClass(self.value) for med in person.medications
                )
        return False


# Spec 8.2, transcribed row for row.
VULNERABILITY_RULES: tuple[VulnerabilityRule, ...] = (
    VulnerabilityRule(ReasonCode.AGE_85_PLUS, VulnKind.AGE_BAND, AgeBand.B85_PLUS, 3),
    VulnerabilityRule(ReasonCode.AGE_75_84, VulnKind.AGE_BAND, AgeBand.B75_84, 2),
    VulnerabilityRule(ReasonCode.LIVES_ALONE, VulnKind.FLAG, "lives_alone", 2),
    VulnerabilityRule(ReasonCode.DEMENTIA, VulnKind.CONDITION, Condition.DEMENTIA, 2),
    VulnerabilityRule(
        ReasonCode.CARDIOVASCULAR, VulnKind.CONDITION, Condition.CARDIOVASCULAR, 2
    ),
    VulnerabilityRule(ReasonCode.RENAL, VulnKind.CONDITION, Condition.RENAL, 2),
    VulnerabilityRule(
        ReasonCode.RESPIRATORY, VulnKind.CONDITION, Condition.RESPIRATORY, 1
    ),
    VulnerabilityRule(ReasonCode.MOBILITY_LIMITED, VulnKind.FLAG, "mobility_limited", 1),
    VulnerabilityRule(ReasonCode.MED_LITHIUM, VulnKind.MED_CLASS, MedClass.LITHIUM, 3),
    VulnerabilityRule(ReasonCode.MED_DIURETIC, VulnKind.MED_CLASS, MedClass.DIURETIC, 2),
    VulnerabilityRule(
        ReasonCode.MED_ANTICHOLINERGIC, VulnKind.MED_CLASS, MedClass.ANTICHOLINERGIC, 2
    ),
    VulnerabilityRule(
        ReasonCode.MED_ANTIPSYCHOTIC, VulnKind.MED_CLASS, MedClass.ANTIPSYCHOTIC, 2
    ),
    VulnerabilityRule(ReasonCode.MED_ACE_ARB, VulnKind.MED_CLASS, MedClass.ACE_ARB, 1),
    VulnerabilityRule(
        ReasonCode.MED_BETA_BLOCKER, VulnKind.MED_CLASS, MedClass.BETA_BLOCKER, 1
    ),
    VulnerabilityRule(ReasonCode.MED_SSRI, VulnKind.MED_CLASS, MedClass.SSRI, 1),
)

# Spec 8.1. SUSTAINED_SPELL's "peak >= 24" is read as peak_apparent — the reading
# that reproduces the section 8.6 worked example, where 29 apparent triggers it.
#
# The three cold codes carry the COLD_GUARD bound on peak_air. See docs/deviations.md.
EXPOSURE_RULES: tuple[ExposureRule, ...] = (
    ExposureRule(
        ReasonCode.NIGHT_NO_RECOVERY, (Bound("overnight_min", minimum=20),), 3
    ),
    ExposureRule(
        ReasonCode.BEDROOM_UNSAFE, (Bound("indoor_night_est", minimum=26),), 3
    ),
    ExposureRule(
        ReasonCode.BEDROOM_WARM, (Bound("indoor_night_est", 24, 26),), 1
    ),
    ExposureRule(ReasonCode.PEAK_HEAT, (Bound("peak_apparent", minimum=30),), 2),
    ExposureRule(
        ReasonCode.SUSTAINED_SPELL,
        (Bound("spell_day", minimum=3), Bound("peak_apparent", minimum=24)),
        2,
    ),
    ExposureRule(
        ReasonCode.INDOOR_BELOW_18,
        (
            Bound("peak_air", maximum=HEATING_DAY_MAX),
            Bound("indoor_day_est", 16, 18),
        ),
        2,
    ),
    ExposureRule(
        ReasonCode.INDOOR_BELOW_16,
        (
            Bound("peak_air", maximum=HEATING_DAY_MAX),
            Bound("indoor_day_est", 12, 16),
        ),
        3,
    ),
    ExposureRule(
        ReasonCode.INDOOR_BELOW_12,
        (
            Bound("peak_air", maximum=HEATING_DAY_MAX),
            Bound("indoor_day_est", maximum=12),
        ),
        4,
    ),
)
