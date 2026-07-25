"""Spec 8.1 and 8.2 transcribed as data.

Table-driven rather than branching, so adding a rule is a data edit and the tables
are diffable line by line against the specification during review.
"""

from collections.abc import Callable
from dataclasses import dataclass

from contracts import AgeBand, Condition, ExposureFeatures, MedClass, Person, ReasonCode


@dataclass(frozen=True, slots=True)
class VulnerabilityRule:
    code: ReasonCode
    predicate: Callable[[Person], bool]
    weight: int


@dataclass(frozen=True, slots=True)
class ExposureRule:
    code: ReasonCode
    predicate: Callable[[ExposureFeatures], bool]
    weight: int


def has_condition(condition: Condition) -> Callable[[Person], bool]:
    return lambda person: condition in person.conditions


def has_med_class(med_class: MedClass) -> Callable[[Person], bool]:
    return lambda person: any(med.drug_class is med_class for med in person.medications)


VULNERABILITY_RULES: tuple[VulnerabilityRule, ...] = (
    VulnerabilityRule(ReasonCode.AGE_85_PLUS, lambda p: p.age_band is AgeBand.B85_PLUS, 3),
    VulnerabilityRule(ReasonCode.AGE_75_84, lambda p: p.age_band is AgeBand.B75_84, 2),
    VulnerabilityRule(ReasonCode.LIVES_ALONE, lambda p: p.lives_alone, 2),
    VulnerabilityRule(ReasonCode.DEMENTIA, has_condition(Condition.DEMENTIA), 2),
    VulnerabilityRule(ReasonCode.CARDIOVASCULAR, has_condition(Condition.CARDIOVASCULAR), 2),
    VulnerabilityRule(ReasonCode.RENAL, has_condition(Condition.RENAL), 2),
    VulnerabilityRule(ReasonCode.RESPIRATORY, has_condition(Condition.RESPIRATORY), 1),
    VulnerabilityRule(ReasonCode.MOBILITY_LIMITED, lambda p: p.mobility_limited, 1),
    VulnerabilityRule(ReasonCode.MED_LITHIUM, has_med_class(MedClass.LITHIUM), 3),
    VulnerabilityRule(ReasonCode.MED_DIURETIC, has_med_class(MedClass.DIURETIC), 2),
    VulnerabilityRule(
        ReasonCode.MED_ANTICHOLINERGIC, has_med_class(MedClass.ANTICHOLINERGIC), 2
    ),
    VulnerabilityRule(
        ReasonCode.MED_ANTIPSYCHOTIC, has_med_class(MedClass.ANTIPSYCHOTIC), 2
    ),
    VulnerabilityRule(ReasonCode.MED_ACE_ARB, has_med_class(MedClass.ACE_ARB), 1),
    VulnerabilityRule(ReasonCode.MED_BETA_BLOCKER, has_med_class(MedClass.BETA_BLOCKER), 1),
    VulnerabilityRule(ReasonCode.MED_SSRI, has_med_class(MedClass.SSRI), 1),
)

HEATING_DAY_MAX = 18.0
"""Above this outdoor peak, a cold-code trigger is a modelling artefact rather than
a cold home. See COLD_GUARD below."""

# SUSTAINED_SPELL's "peak >= 24" is read as peak_apparent. That is the reading which
# reproduces the section 8.6 worked example, where 29 degrees apparent triggers it.
EXPOSURE_RULES: tuple[ExposureRule, ...] = (
    ExposureRule(ReasonCode.NIGHT_NO_RECOVERY, lambda e: e.overnight_min >= 20, 3),
    ExposureRule(ReasonCode.BEDROOM_UNSAFE, lambda e: e.indoor_night_est >= 26, 3),
    ExposureRule(ReasonCode.BEDROOM_WARM, lambda e: 24 <= e.indoor_night_est < 26, 1),
    ExposureRule(ReasonCode.PEAK_HEAT, lambda e: e.peak_apparent >= 30, 2),
    ExposureRule(
        ReasonCode.SUSTAINED_SPELL,
        lambda e: e.spell_day >= 3 and e.peak_apparent >= 24,
        2,
    ),
    # COLD_GUARD — a documented deviation from spec 8.1.
    #
    # The FR-11 indoor formula returns a value well below the outdoor maximum in
    # mild weather: a night of 12 and a day of 19 gives a modelled indoor day of
    # 16.55 in an ordinary bungalow. Read literally, section 8.1 therefore fires
    # INDOOR_BELOW_18 on a pleasant British summer afternoon, which fails the
    # specification's own no-cry-wolf criterion in section 13.
    #
    # Cold codes are therefore evaluated only when outdoor peak air is below 18 —
    # a day on which heating is plausible at all. The alternative fixes are worse:
    # changing the FR-11 coefficients would break the section 8.6 worked example,
    # and lowering the cold thresholds would under-warn in genuine cold.
    #
    # Found by the JS prototype in web/companion, which had reached this
    # conclusion independently. See docs/deviations.md.
    ExposureRule(
        ReasonCode.INDOOR_BELOW_18,
        lambda e: e.peak_air < HEATING_DAY_MAX and 16 <= e.indoor_day_est < 18,
        2,
    ),
    ExposureRule(
        ReasonCode.INDOOR_BELOW_16,
        lambda e: e.peak_air < HEATING_DAY_MAX and 12 <= e.indoor_day_est < 16,
        3,
    ),
    ExposureRule(
        ReasonCode.INDOOR_BELOW_12,
        lambda e: e.peak_air < HEATING_DAY_MAX and e.indoor_day_est < 12,
        4,
    ),
)
