"""The prompts offered before anyone types.

Source-grep rather than behavioural: there is no JS test runner in this repo,
and a wiring check that the safety gate exists is worth more than nothing while
that stays true. It cannot prove the filter fires — see the caveat on the last
test — so it pins the parts whose absence would be silent.

The property that matters: "How much should I be drinking?" must not be offered
to someone on a fluid restriction. For Victor — heart failure, a diuretic,
reduced kidney function — "drink plenty" is the wrong advice, and the demo is
built around exactly that inversion. Offering the question as a one-tap chip
invites the answer the rest of the system exists to avoid giving.
"""

from pathlib import Path

import pytest

SUGGESTIONS = Path(__file__).resolve().parents[2] / "web" / "app" / "src" / "lib" / "suggestions.ts"


@pytest.fixture(scope="module")
def source() -> str:
    return SUGGESTIONS.read_text()


def test_the_fluid_restriction_gate_exists(source):
    assert "fluidIsRestricted" in source


@pytest.mark.parametrize("factor", ["renal", "cardiovascular", "diuretic"])
def test_the_gate_reads_the_factors_that_define_a_restriction(source, factor):
    """Renal disease, or heart disease plus a diuretic. Losing any one of these
    from the predicate widens who gets offered the unsafe prompt."""
    gate = source[source.index("const fluidIsRestricted") : source.index("const RULES")]
    assert factor in gate


def test_the_general_drink_prompt_is_filtered_by_that_gate(source):
    """The general list still carries the drink question, because it is useful
    to most people. This asserts it is removed rather than the whole prompt
    being dropped for everyone."""
    body = source[source.index("export function suggestionsFor") :]
    assert "fluidIsRestricted(profile)" in body
    assert "drink" in body


def test_every_rule_records_why_it_exists(source):
    """`because` is not decoration — these are clinical judgements about which
    question to put in front of someone, and the next person to reword one
    needs to know what it was for."""
    table = source[source.index("const RULES") : source.index("const GENERAL")]
    assert table.count("because:") == table.count("when:") == table.count("text:") > 0


def test_polypharmacy_has_a_prompt_of_its_own(source):
    """The engine scores overlapping medicines; the assistant should offer to
    talk about them rather than leaving the reader to think of it."""
    assert "medicines work against each other" in source


def test_this_file_cannot_prove_the_filter_actually_fires(source):
    """Deliberate placeholder, kept so the gap is visible in the suite rather
    than only in a comment.

    These are string checks against source. They would pass if the predicate
    were inverted, or never called. The real fix is a JS test runner, and until
    there is one this file records that the coverage is wiring-only.
    """
    assert "suggestionsFor" in source
