"""
demo_compare.py — same condition, different risk.

Run with:
    uv run python scripts/demo_compare.py

Shows two pairs side-by-side on 19 July 2025 (Bedford, no regional alert):

  CARDIOVASCULAR:  Alan (ELEVATED) vs Victor (HIGH)
  DEMENTIA:        Pat  (ELEVATED) vs Doris  (HIGH)

Both people in each pair share the same primary diagnosis. The tier
difference comes entirely from compounding factors: polypharmacy,
comorbidities, living situation, and housing. That is the product argument.
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

PAIRS = [
    {
        "title": "CARDIOVASCULAR — same condition, different risk",
        "condition": "cardiovascular",
        "low": "alan",
        "high": "victor",
        "contrast": (
            "Alan: cardiovascular only, on bisoprolol, lives with family, "
            "has cooling, ground-floor north-facing house.\n"
            "Victor: cardiovascular + renal + COPD, on furosemide + ramipril "
            "+ bisoprolol + citalopram, alone, 2nd-floor south flat, no cooling.\n"
            "The generic heat alert reaches both. The personalised plan is "
            "completely different."
        ),
    },
    {
        "title": "DEMENTIA — same condition, different risk",
        "condition": "dementia",
        "low": "pat",
        "high": "doris",
        "contrast": (
            "Pat: early-onset dementia, no medications, lives with spouse, "
            "has cooling, ground-floor east bungalow.\n"
            "Doris: dementia + COPD + mobility-limited, on furosemide + "
            "ramipril + sertraline, alone, 3rd-floor south flat, no cooling.\n"
            "Dementia alone is not the lethal factor — it is dementia combined "
            "with no caregiver, no cooling, polypharmacy, and a hot building."
        ),
    },
]

WIDTH = 74


def _divider(char="─"):
    return char * WIDTH


def _header(text):
    pad = (WIDTH - len(text) - 2) // 2
    return f"{'═' * pad} {text} {'═' * (WIDTH - pad - len(text) - 2)}"


def _tier_badge(tier_name):
    badges = {"LOW": "⬜ LOW", "ELEVATED": "🟡 ELEVATED", "HIGH": "🔴 HIGH", "SEVERE": "🚨 SEVERE"}
    return badges.get(tier_name, tier_name)


def _wrap(text, width=WIDTH - 4, prefix="  "):
    return indent(fill(text, width), prefix)


def run():
    loader = PersonaLoader()
    people = loader.load()
    places = loader.places()
    vuln = VulnerabilityScorer()
    scorer = RiskScorer(Corpus.load())
    table = InteractionTable.load()

    print()
    print(_header("DEMO: SAME CONDITION · DIFFERENT RISK"))
    print(f"  Date: 19 July 2025 · Bedford · Alert level: NONE")
    print(
        _wrap(
            "A regional heat-health alert was not issued on this day. "
            "The system computed personal risk anyway.",
        )
    )

    for pair in PAIRS:
        print()
        print(_divider("═"))
        print(f"  {pair['title']}")
        print(_divider())
        print()
        print(_wrap(pair["contrast"]))
        print()

        for pid in (pair["low"], pair["high"]):
            p = people[pid]
            pl = places[pid]
            prof = vuln.profile(p)
            assessment = scorer.assess(BEDFORD_19_JULY_2025, prof)
            interactions = table.matching(BEDFORD_19_JULY_2025, p, assessment.tier)

            label = "LOW RISK PROFILE " if pid == pair["low"] else "HIGH RISK PROFILE"
            conditions = "·".join(c.value for c in p.conditions) or "none"
            print(f"  ┌─ {label}: {p.name.upper()} ({conditions})")
            print(
                f"  │  Tier      {_tier_badge(assessment.tier.name)}"
                f"   Vuln {prof.score}   Risk {assessment.risk_score:.1f}"
            )
            print(f"  │  Meds      {', '.join(m.drug_name for m in p.medications) or 'none'}")
            cooling = "cooling" if pl.has_cooling else "no cooling"
            print(
                f"  │  Housing   {pl.dwelling_type.value}, floor {pl.floor}, "
                f"{pl.aspect.value}-facing, {cooling}"
            )
            print(f"  │  Alone     {'yes' if p.lives_alone else 'no'}")

            if not interactions:
                print("  │  Advice    Standard heat guidance applies.")
            else:
                print(f"  │  Interactions fired ({len(interactions)}):")
                for rule in interactions:
                    print(f"  │    [{rule.code}]")
                    if rule.watch_for:
                        wrapped = fill(rule.watch_for, WIDTH - 14)
                        lines = wrapped.splitlines()
                        print(f"  │      watch: {lines[0]}")
                        for line in lines[1:]:
                            print(f"  │             {line}")
                    if rule.escalate_to:
                        print(f"  │      → escalate to {rule.escalate_to}")
            print("  └" + _divider()[2:])
            print()

    print(_divider("═"))
    print()
    print(
        _wrap(
            "The condition on the front of the notes is the same. "
            "The risk is not. "
            "A generic alert reaches both people with the same message. "
            "This system reaches each person with the right one."
        )
    )
    print()


if __name__ == "__main__":
    run()
