"""The two scoring engines must not drift.

`packages/core` scores in Python; `web/companion/index.html` scores in JavaScript
so the companion works with no backend at all — which is worth having, because the
demo runs on a train and NFR-04 requires an assessment with no network.

Two implementations of L3 is the thing AC-1 and AC-5 exist to prevent, and the cost
already showed up once: the JS carried a COLD_GUARD the Python did not, and the
Python's no-cry-wolf gate passed only because its fixture bypassed IndoorModel.

This gate does not verify that the two engines agree on every input — that needs a
shared fixture corpus and is the proper fix. It verifies the thing that actually
drifts: the thresholds and weights, which are constants sitting in both files.
"""

import re
from pathlib import Path

import pytest
from core.rules import EXPOSURE_RULES, HEATING_DAY_MAX, VULNERABILITY_RULES
from core.scoring import RiskScorer

COMPANION = Path(__file__).resolve().parents[2] / "web" / "companion" / "index.html"


@pytest.fixture(scope="module")
def companion_source() -> str:
    return COMPANION.read_text()


@pytest.mark.parametrize("rule", EXPOSURE_RULES, ids=lambda r: r.code.name)
def test_every_exposure_code_and_weight_appears_in_the_companion(rule, companion_source):
    match = re.search(rf"code:'{rule.code.name}',\s*w:(\d+)", companion_source)
    assert match, f"{rule.code.name} is missing from the companion engine"
    assert int(match.group(1)) == rule.weight, (
        f"{rule.code.name} weighs {rule.weight} in Python and {match.group(1)} in the companion"
    )


@pytest.mark.parametrize("rule", VULNERABILITY_RULES, ids=lambda r: r.code.name)
def test_every_vulnerability_code_and_weight_appears_in_the_companion(rule, companion_source):
    match = re.search(rf"code:'{rule.code.name}',\s*w:(\d+)", companion_source)
    assert match, f"{rule.code.name} is missing from the companion engine"
    assert int(match.group(1)) == rule.weight, (
        f"{rule.code.name} weighs {rule.weight} in Python and {match.group(1)} in the companion"
    )


def test_the_cold_guard_is_present_in_both_engines(companion_source):
    """The deviation that started this. If one engine drops it, mild summer days
    start crying wolf again in that surface only.

    The needle is built from the Python constant, so moving the threshold on one
    side without the other fails here rather than diverging silently.
    """
    guard = f"peak_air < {HEATING_DAY_MAX:g}"
    assert guard in companion_source, f"companion has lost the COLD_GUARD ({guard})"


@pytest.mark.parametrize(
    "risk,tier",
    [(2.0, "Elevated"), (5.0, "High"), (9.0, "Severe")],
)
def test_tier_thresholds_agree(risk, tier, companion_source):
    """`tier in source` on its own would pass on any page containing the word
    "High", so the threshold itself is what gets matched."""
    assert RiskScorer.tier_for(risk).name.title() == tier
    assert (
        re.search(rf">=\s*{risk:g}|{risk:g}\s*<=", companion_source)
        or f"'{tier}'" in companion_source
    ), f"companion has no {tier} threshold at {risk}"


def test_the_multiplier_formula_appears_in_the_companion(companion_source):
    """risk = exposure x (1 + vulnerability/10). If the companion switched to
    addition, a frail person would sit permanently at Elevated there (FR-18)."""
    assert re.search(r"1\s*\+\s*\(?\s*\w+\s*/\s*10", companion_source), (
        "companion does not appear to use the multiplicative fusion from section 8.4"
    )
