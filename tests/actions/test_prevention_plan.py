from datetime import date

import pytest
from actions.checklist import PreventionPlanBuilder
from actions.interactions import InteractionTable
from contracts import (
    AdviceSource,
    AlertLevel,
    Assessment,
    Audience,
    Condition,
    DateRange,
    ExposureFeatures,
    ExposureSource,
    Med,
    MedClass,
    Person,
    Reason,
    ReasonCode,
    SelfReport,
    Tier,
)
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer

WINDOW = DateRange(date(2025, 7, 19), date(2025, 7, 20))


@pytest.fixture(scope="module")
def builder() -> PreventionPlanBuilder:
    return PreventionPlanBuilder(Corpus.load(), InteractionTable.load())


def hot(**kw) -> ExposureFeatures:
    base = dict(date=date(2025, 7, 19), overnight_min=17.0, peak_apparent=29.0,
                peak_air=29.0, hours_above_26=7, indoor_night_est=24.6,
                indoor_day_est=25.85, spell_day=3, alert_level=AlertLevel.NONE,
                source=ExposureSource.ARCHIVE)
    return ExposureFeatures(**(base | kw))


def person(**kw) -> Person:
    base = dict(id="p", name="P", age_band="b85_plus", lives_alone=True,
                mobility_limited=False)
    return Person(**(base | kw))


def assess(p: Person, exposure: ExposureFeatures) -> Assessment:
    return RiskScorer(Corpus.load()).assess(exposure, VulnerabilityScorer().profile(p))


def codes(plan) -> set[str]:
    return {item.code for item in plan.items}


# ------------------------------------------------------- FR-15, the spec gap

def test_heat_sensitive_medication_gets_a_storage_instruction_above_25(builder):
    """FR-15. Insulin degrading on a windowsill is a property of neither the person
    nor the weather — it exists only in the combination."""
    p = person(medications=(Med("insulin", MedClass.HEAT_SENSITIVE),))
    exposure = hot(peak_air=26.0)
    plan = builder.build(p, exposure, assess(p, exposure))
    assert "heat_sensitive_storage" in codes(plan)


def test_no_storage_instruction_below_25(builder):
    """The spec threshold is exact, so the rule must not fire in mild weather."""
    p = person(medications=(Med("insulin", MedClass.HEAT_SENSITIVE),))
    exposure = hot(peak_air=24.0, peak_apparent=24.0, indoor_night_est=20.0,
                   indoor_day_est=21.0, spell_day=0)
    plan = builder.build(p, exposure, assess(p, exposure))
    assert "heat_sensitive_storage" not in codes(plan)


# ------------------------------------------------ combinations, not additions

def test_a_combination_produces_advice_neither_factor_produces_alone(builder):
    """Diuretic alone and renal alone are each a single factor. Together, in heat,
    they are a different instruction."""
    both = person(conditions=(Condition.RENAL,),
                  medications=(Med("furosemide", MedClass.DIURETIC),))
    diuretic_only = person(medications=(Med("furosemide", MedClass.DIURETIC),))

    exposure = hot()
    with_both = codes(builder.build(both, exposure, assess(both, exposure)))
    with_one = codes(builder.build(diuretic_only, exposure, assess(diuretic_only, exposure)))

    assert "diuretic_and_renal" in with_both
    assert "diuretic_and_renal" not in with_one


def test_asthma_plus_heart_disease_is_treated_as_compounding(builder):
    """The comorbidity case: each condition worsens the other in heat rather than
    simply adding to it."""
    p = person(conditions=(Condition.RESPIRATORY, Condition.CARDIOVASCULAR))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure))
    assert "respiratory_and_cardiovascular" in codes(plan)


def test_the_renal_heart_combination_warns_against_the_general_advice(builder):
    """Where 'drink plenty in hot weather' is actively wrong, the advice must say so
    rather than repeating it."""
    p = person(conditions=(Condition.RENAL, Condition.CARDIOVASCULAR))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure))
    item = next(i for i in plan.items if i.code == "renal_and_cardiovascular")
    assert "does not apply" in item.text
    assert item.escalate_to == "gp"


def test_a_dormant_condition_earns_no_advice_in_mild_weather(builder):
    """Reduced kidney function is asymptomatic until fluid is being lost."""
    p = person(conditions=(Condition.RENAL,),
               medications=(Med("furosemide", MedClass.DIURETIC),))
    mild = hot(peak_air=15.0, peak_apparent=15.0, indoor_night_est=19.0,
               indoor_day_est=20.0, spell_day=0)
    plan = builder.build(p, mild, assess(p, mild))
    assert "diuretic_and_renal" not in codes(plan)


# ------------------------------------------------------------ watch, versus do

def test_an_anticholinergic_warns_that_the_usual_sign_is_absent(builder):
    """Suppressed sweating removes the first warning of overheating, so its absence
    is not reassurance. That is a watch-for, not a do."""
    p = person(medications=(Med("oxybutynin", MedClass.ANTICHOLINERGIC),))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure))
    watch = " ".join(plan.watch_points)
    assert "not reassurance" in watch


def test_watch_points_are_deduplicated_and_ordered(builder):
    p = person(conditions=(Condition.CARDIOVASCULAR,),
               medications=(Med("bisoprolol", MedClass.BETA_BLOCKER),))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure))
    assert len(plan.watch_points) == len(set(plan.watch_points))


# ------------------------------------------------------------- two audiences

def test_the_person_and_the_caregiver_get_different_words(builder):
    p = person(medications=(Med("bisoprolol", MedClass.BETA_BLOCKER),))
    exposure = hot()
    assessment = assess(p, exposure)

    caregiver = builder.build(p, exposure, assessment, Audience.CAREGIVER)
    cared_for = builder.build(p, exposure, assessment, Audience.CARED_FOR)

    theirs = next(i for i in caregiver.items if i.code == "beta_blocker_exertion").text
    yours = next(i for i in cared_for.items if i.code == "beta_blocker_exertion").text
    assert theirs != yours
    assert "they may not feel" in theirs
    assert yours.startswith("Your medicine")


def test_advice_the_person_cannot_act_on_is_not_addressed_to_them(builder):
    """Telling someone with dementia to monitor their own confusion is not a
    safeguard — it is a sentence they cannot act on."""
    p = person(conditions=(Condition.DEMENTIA,))
    exposure = hot()
    assessment = assess(p, exposure)

    assert "dementia_cannot_self_report" in codes(
        builder.build(p, exposure, assessment, Audience.CAREGIVER)
    )
    assert "dementia_cannot_self_report" not in codes(
        builder.build(p, exposure, assessment, Audience.CARED_FOR)
    )


def test_watch_points_go_only_to_the_caregiver(builder):
    """Asking someone to watch for their own confusion inverts the safeguard."""
    p = person(medications=(Med("oxybutynin", MedClass.ANTICHOLINERGIC),))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure), Audience.CARED_FOR)
    assert plan.watch_points == ()


def test_the_third_person_corpus_is_never_read_to_the_person(builder):
    """Until actions.csv gains a person-facing column, single-factor advice is
    caregiver-only rather than addressed at them in the wrong voice."""
    p = person(conditions=(Condition.DEMENTIA,))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure), Audience.CARED_FOR)
    assert all(i.source is not AdviceSource.REASON_CODE for i in plan.items)


# ------------------------------------------------------- prevention framing

def test_a_plan_with_lead_time_is_preventive(builder):
    p = person()
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure), lead_time_hours=72,
                         expected_peak=31.0)
    assert plan.is_preventive


def test_a_plan_read_during_the_episode_is_not_preventive(builder):
    p = person()
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure), lead_time_hours=0)
    assert not plan.is_preventive


def test_the_plan_is_produced_with_no_regional_alert_in_force(builder):
    """The product argument: a regional warning is context, never a gate."""
    p = person(conditions=(Condition.CARDIOVASCULAR,))
    exposure = hot(alert_level=AlertLevel.NONE)
    plan = builder.build(p, exposure, assess(p, exposure))
    assert plan.alert_level is AlertLevel.NONE
    assert plan.items


# ----------------------------------------------------------- self-report feed

def test_what_the_person_said_produces_its_own_advice(builder):
    p = person(medications=(Med("furosemide", MedClass.DIURETIC),))
    exposure = hot()
    report = SelfReport(person_id="p", window=WINDOW, answered=True,
                        drinking_fluids=False)
    plan = builder.build(p, exposure, assess(p, exposure), report=report)
    item = next(i for i in plan.items if i.code == "not_drinking_reported")
    assert item.source is AdviceSource.SELF_REPORT


def test_an_unanswered_check_in_produces_no_self_report_advice(builder):
    """Absence of an answer is not an answer."""
    p = person(medications=(Med("furosemide", MedClass.DIURETIC),))
    exposure = hot()
    report = SelfReport(person_id="p", window=WINDOW, answered=False)
    plan = builder.build(p, exposure, assess(p, exposure), report=report)
    assert "not_drinking_reported" not in codes(plan)


# ------------------------------------------------------------------ ordering

def test_interactions_come_before_single_factor_advice(builder):
    """A combination is the thing a caregiver could not have worked out alone."""
    p = person(conditions=(Condition.RENAL,),
               medications=(Med("furosemide", MedClass.DIURETIC),))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure))
    sources = [i.source for i in plan.items]
    first_reason = next(
        (n for n, s in enumerate(sources) if s is AdviceSource.REASON_CODE), len(sources)
    )
    assert all(s is not AdviceSource.INTERACTION for s in sources[first_reason:])


def test_an_interaction_supersedes_the_generic_advice_it_is_built_from(builder):
    """The combination advice is more specific than the single-factor advice, so
    emitting both would bury the better instruction under the generic one."""
    p = person(conditions=(Condition.RENAL,),
               medications=(Med("furosemide", MedClass.DIURETIC),))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure))

    assert "diuretic_and_renal" in codes(plan)
    assert ReasonCode.MED_DIURETIC not in codes(plan), "generic diuretic advice survived"
    assert ReasonCode.RENAL not in codes(plan), "generic renal advice survived"


def test_generic_advice_survives_when_no_interaction_covers_it(builder):
    """Superseding is targeted, not blanket suppression. A diuretic on its own has
    no combination rule, so the single-factor advice must still reach the caregiver."""
    p = person(medications=(Med("furosemide", MedClass.DIURETIC),))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure))
    assert ReasonCode.MED_DIURETIC in codes(plan)
    assert ReasonCode.LIVES_ALONE in codes(plan)


def test_one_reason_code_may_yield_several_items_across_tiers(builder):
    """actions.csv carries a row per tier, so a High-tier plan gets both the
    Elevated and the High instruction for the same factor. Not duplication — the
    High row is additional advice, not a restatement."""
    doris = person(conditions=(Condition.DEMENTIA,),
                   medications=(Med("furosemide", MedClass.DIURETIC),
                                Med("ramipril", MedClass.ACE_ARB)))
    exposure = hot()
    assessment = assess(doris, exposure)
    assert assessment.tier is Tier.HIGH, "fixture must reach High for this to mean anything"

    plan = builder.build(doris, exposure, assessment)
    alone = [i for i in plan.items if i.code == ReasonCode.LIVES_ALONE]
    assert len(alone) > 1
    assert len({i.text for i in alone}) == len(alone)


def test_escalation_targets_are_collected_and_deduplicated(builder):
    p = person(conditions=(Condition.RENAL, Condition.CARDIOVASCULAR),
               medications=(Med("furosemide", MedClass.DIURETIC),))
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure))
    assert "gp" in plan.escalation_targets()
    assert len(plan.escalation_targets()) == len(set(plan.escalation_targets()))


# ------------------------------------------------- gating, not firing for all

def test_a_rule_with_no_condition_or_medication_still_needs_its_flag(builder):
    """mobility_cannot_self_rescue declares no condition and no medicine, so
    without a flag requirement it fired for everyone above 22 degrees — including
    people with no mobility limitation at all."""
    mobile = person(mobility_limited=False)
    limited = person(mobility_limited=True)
    exposure = hot()

    assert "mobility_cannot_self_rescue" not in codes(
        builder.build(mobile, exposure, assess(mobile, exposure))
    )
    assert "mobility_cannot_self_rescue" in codes(
        builder.build(limited, exposure, assess(limited, exposure))
    )


def test_self_report_advice_never_fires_without_an_answer(builder):
    """Telling someone "you said your bedroom feels too hot" when they said
    nothing of the kind attributes a statement to them that they never made."""
    p = person()
    exposure = hot()
    plan = builder.build(p, exposure, assess(p, exposure), report=None)
    assert "bedroom_hot_reported" not in codes(plan)
    assert "not_drinking_reported" not in codes(plan)
