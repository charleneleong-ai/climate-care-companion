"""
demo_compare.py — same condition, different risk.

Run with:
    uv run python scripts/demo_compare.py

Three sections, each making a different argument:

  1. THE POLYPHARMACY CASCADE
     Alan and Victor share cardiovascular disease. Alan is on one drug.
     Victor is on four. Each drug adds a new interaction chain. The demo
     builds Victor's plan one medicine at a time to show how risk compounds.

  2. DORMANT CONDITIONS ACTIVATED BY HEAT
     Reg's renal disease earns no advice in cool weather. On a hot day,
     combined with his diuretics and heart condition, it fires four
     interaction chains simultaneously. The condition was always there;
     the heat makes it matter.

  3. WHERE PERSONALISED ADVICE CONTRADICTS THE GENERIC MESSAGE
     Victor: the public message is "drink plenty." His plan says do not
     follow a general figure — the right amount points the opposite way
     to thirst.
     Sylvia: the public message is "your body will warn you." Her plan
     says the absence of sweat and heat-feeling are NOT reassurance.
"""

from datetime import date
from textwrap import fill, indent

from contracts import AlertLevel, ExposureFeatures, ExposureSource
from actions.interactions import InteractionTable
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from persons.loader import PersonaLoader

# --------------------------------------------------------------------------
# The fixture: 19 July 2025, Bedford, no regional heat-health alert issued.
# This is the spec §8.6 worked example and the headline demo date.
# --------------------------------------------------------------------------
BEDFORD_19_JULY_2025 = ExposureFeatures(
    date=date(2025, 7, 19),
    overnight_min=17.0,
    peak_apparent=29.0,
    peak_air=29.0,
    hours_above_26=7,
    indoor_night_est=24.6,
    indoor_day_est=25.85,
    spell_day=3,
    alert_level=AlertLevel.NONE,
    source=ExposureSource.ARCHIVE,
)

# Generic heat messages that the NHS / UKHSA issue to everyone.
GENERIC_HEAT_ADVICE = [
    "Drink plenty of fluids to stay hydrated.",
    "Stay out of the sun during the hottest part of the day.",
    "If you feel too warm, move to a cooler room.",
    "Your body will warn you when you are getting too hot — you will feel hot and start to sweat.",
    "Look out for signs of heat exhaustion: heavy sweating, dizziness, feeling faint.",
]

# Interactions where the personalised plan directly inverts a generic message.
CONTRADICTIONS = [
    {
        "persona": "victor",
        "generic": "Drink plenty of fluids to stay hydrated.",
        "why_wrong": (
            "Victor has renal disease and cardiovascular disease. Too little "
            "fluid strains the kidneys; too much overloads the heart. The safe "
            "amount is his GP's number, not a public figure. His furosemide "
            "increases fluid loss and his ramipril blunts thirst, so he can "
            "dehydrate without feeling it."
        ),
        "interaction_code": "renal_and_cardiovascular",
        "personalised_watch": (
            "Swollen ankles or breathlessness lying flat, which point the "
            "opposite way to thirst and dark urine. Report whichever you see "
            "rather than acting on one."
        ),
    },
    {
        "persona": "victor",
        "generic": "If you feel too warm, go for a gentle walk or get some fresh air.",
        "why_wrong": (
            "Victor's bisoprolol slows the heart's response to exertion and "
            "reduces blood flow to the skin, so he may not feel how hard his "
            "body is working. Exertion in heat without the usual warning "
            "signals is a cardiac risk, not a remedy."
        ),
        "interaction_code": "beta_blocker_exertion",
        "personalised_watch": (
            "Breathlessness or dizziness on standing, rather than the racing "
            "heart you would normally expect."
        ),
    },
    {
        "persona": "sylvia",
        "generic": "Your body will warn you when you are getting too hot — you will feel hot and start to sweat.",
        "why_wrong": (
            "Sylvia's olanzapine impairs the brain's temperature control, so "
            "she may not feel hot. Her oxybutynin suppresses sweating, removing "
            "the body's main cooling mechanism and its usual first warning sign. "
            "Feeling cool and not sweating is not reassurance — it is the danger."
        ),
        "interaction_code": "anticholinergic_absent_sweating",
        "personalised_watch": (
            "Hot, dry skin. Sweating is the usual first warning of overheating, "
            "and this medicine removes it — so its absence is not reassurance."
        ),
    },
    {
        "persona": "sylvia",
        "generic": "Look out for signs of heat exhaustion: heavy sweating and feeling faint.",
        "why_wrong": (
            "The standard signs are suppressed by Sylvia's medications. "
            "Sweating will not be present. The usual agitation or confusion "
            "signal may be masked by the antipsychotic. The caregiver must "
            "watch for behavioural change — not the physiological signs the "
            "public health message describes."
        ),
        "interaction_code": "antipsychotic_thermoregulation",
        "personalised_watch": ("Confusion, agitation, or a change in how they are behaving."),
    },
]

WIDTH = 76


def _divider(char="─"):
    return char * WIDTH


def _header(text):
    pad = (WIDTH - len(text) - 2) // 2
    return f"{'═' * pad} {text} {'═' * (WIDTH - pad - len(text) - 2)}"


def _tier_badge(tier_name):
    badges = {
        "LOW": "⬜ LOW",
        "ELEVATED": "🟡 ELEVATED",
        "HIGH": "🔴 HIGH",
        "SEVERE": "🚨 SEVERE",
    }
    return badges.get(tier_name, tier_name)


def _wrap(text, width=WIDTH - 4, prefix="  "):
    return indent(fill(text, width), prefix)


def _print_profile(p, pl, prof, assessment, interactions, label):
    conditions = "·".join(c.value for c in p.conditions) or "none"
    print(f"  ┌─ {label}: {p.name.upper()} ({conditions})")
    print(
        f"  │  Tier   {_tier_badge(assessment.tier.name)}"
        f"   Vuln {prof.score}   Risk {assessment.risk_score:.1f}"
    )
    print(f"  │  Meds   {', '.join(m.drug_name for m in p.medications) or 'none'}")
    print(f"  │  Alone  {'yes — no one will notice' if p.lives_alone else 'no'}")
    if not interactions:
        print("  │  → Standard heat guidance applies.")
    else:
        print(f"  │  → {len(interactions)} interaction(s) fired:")
        for rule in interactions:
            print(f"  │    [{rule.code}]")
            if rule.watch_for:
                lines = fill(rule.watch_for, WIDTH - 14).splitlines()
                print(f"  │      watch: {lines[0]}")
                for line in lines[1:]:
                    print(f"  │             {line}")
    print("  └" + _divider()[2:])
    print()


def section_polypharmacy_cascade(people, places, vuln, scorer, table):
    """Section 1: build Victor's risk one drug at a time."""
    print(_divider("═"))
    print("  SECTION 1 — THE POLYPHARMACY CASCADE")
    print("  Same condition (cardiovascular). Each drug added creates a new")
    print("  interaction chain the previous drug did not.")
    print(_divider())
    print()

    from contracts import AgeBand, Condition, Med, MedClass, Person
    from persons.loader import load_dwelling_offsets, PersonaFile
    import yaml
    from pathlib import Path

    victor_full = people["victor"]
    alan = people["alan"]
    alan_place = places["alan"]
    victor_place = places["victor"]

    # Progressive builds: start from Alan's profile, add Victor's meds one by one
    stages = [
        {
            "label": "Stage 0 — cardiovascular + bisoprolol only (Alan)",
            "person": alan,
            "place": alan_place,
        },
        {
            "label": "Stage 1 — + furosemide (water tablet)",
            "person": Person(
                id="_stage1",
                name="Victor",
                age_band=AgeBand.B75_84,
                lives_alone=True,
                mobility_limited=False,
                conditions=(Condition.CARDIOVASCULAR,),
                medications=(
                    Med("bisoprolol", MedClass.BETA_BLOCKER),
                    Med("furosemide", MedClass.DIURETIC),
                ),
            ),
            "place": victor_place,
        },
        {
            "label": "Stage 2 — + ramipril (ACE inhibitor) + renal disease",
            "person": Person(
                id="_stage2",
                name="Victor",
                age_band=AgeBand.B75_84,
                lives_alone=True,
                mobility_limited=False,
                conditions=(Condition.CARDIOVASCULAR, Condition.RENAL),
                medications=(
                    Med("bisoprolol", MedClass.BETA_BLOCKER),
                    Med("furosemide", MedClass.DIURETIC),
                    Med("ramipril", MedClass.ACE_ARB),
                ),
            ),
            "place": victor_place,
        },
        {
            "label": "Stage 3 — + COPD (respiratory)",
            "person": Person(
                id="_stage3",
                name="Victor",
                age_band=AgeBand.B75_84,
                lives_alone=True,
                mobility_limited=False,
                conditions=(
                    Condition.CARDIOVASCULAR,
                    Condition.RENAL,
                    Condition.RESPIRATORY,
                ),
                medications=(
                    Med("bisoprolol", MedClass.BETA_BLOCKER),
                    Med("furosemide", MedClass.DIURETIC),
                    Med("ramipril", MedClass.ACE_ARB),
                ),
            ),
            "place": victor_place,
        },
        {
            "label": "Stage 4 — + citalopram (SSRI) — Victor in full",
            "person": victor_full,
            "place": victor_place,
        },
    ]

    prev_codes: set[str] = set()
    for stage in stages:
        p = stage["person"]
        prof = vuln.profile(p)
        assessment = scorer.assess(BEDFORD_19_JULY_2025, prof)
        interactions = table.matching(BEDFORD_19_JULY_2025, p, assessment.tier)
        codes = {r.code for r in interactions}
        new_codes = codes - prev_codes

        print(f"  ▸ {stage['label']}")
        print(
            f"    {_tier_badge(assessment.tier.name)}"
            f"  Vuln {prof.score}  Risk {assessment.risk_score:.1f}"
            f"  → {len(interactions)} interaction(s)"
        )
        if new_codes:
            for rule in interactions:
                if rule.code in new_codes:
                    marker = "  ← NEW"
                    print(f"    [{rule.code}]{marker}")
        else:
            print("    (no new interactions from this addition)")
        print()
        prev_codes = codes


def section_dormant_conditions(people, places, vuln, scorer, table):
    """Section 2: same person, cool day vs hot day."""
    print(_divider("═"))
    print("  SECTION 2 — DORMANT CONDITIONS ACTIVATED BY HEAT")
    print("  Reg has renal disease. In cool weather it earns no advice.")
    print("  On a hot day it fires four interaction chains. The condition")
    print("  was always there; the heat makes it clinically active.")
    print(_divider())
    print()

    reg = people["reg"]
    prof = vuln.profile(reg)

    # Cool March day — well below all interaction thresholds
    COOL_MARCH_DAY = ExposureFeatures(
        date=date(2025, 3, 15),
        overnight_min=4.0,
        peak_apparent=10.0,
        peak_air=10.0,
        hours_above_26=0,
        indoor_night_est=16.5,
        indoor_day_est=17.0,
        spell_day=0,
        alert_level=AlertLevel.NONE,
        source=ExposureSource.ARCHIVE,
    )

    for label, exposure in [
        ("15 March 2025 (cool day, 10°C peak)", COOL_MARCH_DAY),
        ("19 July 2025 (heat episode, 29°C peak, no alert)", BEDFORD_19_JULY_2025),
    ]:
        assessment = scorer.assess(exposure, prof)
        interactions = table.matching(exposure, reg, assessment.tier)
        print(f"  ▸ {label}")
        print(
            f"    {_tier_badge(assessment.tier.name)}"
            f"  Vuln {prof.score} (unchanged — the conditions are always present)"
        )
        if not interactions:
            print("    Interactions fired: none")
            print("    Renal disease earns no specific advice in cool weather.")
            print("    The diuretic combination is unremarkable at 10°C.")
        else:
            print(f"    Interactions fired: {len(interactions)}")
            for rule in interactions:
                print(f"    [{rule.code}]")
                if rule.watch_for:
                    lines = fill(rule.watch_for, WIDTH - 10).splitlines()
                    print(f"      watch: {lines[0]}")
                    for line in lines[1:]:
                        print(f"             {line}")
        print()


def section_advice_contradiction(people, table):
    """Section 3: generic advice vs what the personalised plan actually says."""
    print(_divider("═"))
    print("  SECTION 3 — WHERE PERSONALISED ADVICE CONTRADICTS THE GENERIC MESSAGE")
    print("  The NHS / UKHSA issues the same heat guidance to everyone.")
    print("  For some people that guidance is not just insufficient — it is wrong.")
    print(_divider())
    print()

    victor = people["victor"]
    sylvia = people["sylvia"]
    victor_assessment = RiskScorer(Corpus.load()).assess(
        BEDFORD_19_JULY_2025, VulnerabilityScorer().profile(victor)
    )
    victor_interactions = {
        r.code: r for r in table.matching(BEDFORD_19_JULY_2025, victor, victor_assessment.tier)
    }
    sylvia_assessment = RiskScorer(Corpus.load()).assess(
        BEDFORD_19_JULY_2025, VulnerabilityScorer().profile(sylvia)
    )
    sylvia_interactions = {
        r.code: r for r in table.matching(BEDFORD_19_JULY_2025, sylvia, sylvia_assessment.tier)
    }
    all_interactions = {**victor_interactions, **sylvia_interactions}

    for c in CONTRADICTIONS:
        pid = c["persona"]
        p = people[pid]
        rule = all_interactions.get(c["interaction_code"])
        print(f"  ▸ {p.name} ({', '.join(co.value for co in p.conditions)})")
        print()
        print(f"  Generic advice:")
        for line in fill(c["generic"], WIDTH - 6).splitlines():
            print(f'    "{line}"')
        print()
        print(f"  Why it is wrong for {p.name}:")
        for line in fill(c["why_wrong"], WIDTH - 4).splitlines():
            print(f"    {line}")
        print()
        print(f"  Personalised watch-for (from [{c['interaction_code']}]):")
        for line in fill(c["personalised_watch"], WIDTH - 4).splitlines():
            print(f"    ⚠ {line}")
        if rule and rule.escalate_to:
            print(f"    → escalate to {rule.escalate_to}")
        print()
        print(_divider("·"))
        print()


def run():
    loader = PersonaLoader()
    people = loader.load()
    places = loader.places()
    vuln = VulnerabilityScorer()
    scorer = RiskScorer(Corpus.load())
    table = InteractionTable.load()

    print()
    print(_header("DEMO: SAME CONDITION · DIFFERENT RISK"))
    print(f"  19 July 2025 · Bedford · Regional alert: NONE")
    print(
        _wrap(
            "No heat-health alert was issued on this day. The system computed personal risk anyway."
        )
    )
    print()

    section_polypharmacy_cascade(people, places, vuln, scorer, table)
    print()
    section_dormant_conditions(people, places, vuln, scorer, table)
    print()
    section_advice_contradiction(people, table)

    print(_divider("═"))
    print()
    print(
        _wrap(
            "The condition on the front of the notes is the same. "
            "The risk is not. "
            "The generic alert reaches both people with the same message. "
            "For some of them, that message is not just insufficient — "
            "it is wrong."
        )
    )
    print()


if __name__ == "__main__":
    run()
