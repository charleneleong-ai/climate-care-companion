"""The monitoring page's cohort table must match the engine.

That table is a hand-copied snapshot of engine output, kept so the page renders
with no API call. The cost of that choice is drift, and the drift is invisible:
every number still looks like a number, the page still loads, and nobody
notices the register is quoting last month's scores.

It already happened. When the compounding rules landed, Victor's vulnerability
went 14 → 18 everywhere except here, so `/monitoring` — the view whose whole
argument is "assessed individually, these people are at risk" — was showing
figures the assessment no longer produced.

This recomputes them and fails on any disagreement.
"""

import re
from pathlib import Path

import pytest
from actions.checklist import PreventionPlanBuilder
from actions.interactions import InteractionTable
from contracts import Audience
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from api.main import heat_fixture_for
from persons.loader import PersonaLoader

PAGE = (
    Path(__file__).resolve().parents[2] / "web" / "app" / "src" / "app" / "monitoring" / "page.tsx"
)

ENTRY = re.compile(
    r"name: '(?P<name>\w+)',\s*"
    r"condition: '[^']*',\s*"
    r"tier: '(?P<tier>\w+)',\s*"
    r"vuln: (?P<vuln>\d+),\s*"
    r"interactions: (?P<items>\d+),",
)


@pytest.fixture(scope="module")
def published() -> dict[str, tuple[str, int, int]]:
    found = {
        m["name"]: (m["tier"], int(m["vuln"]), int(m["items"]))
        for m in ENTRY.finditer(PAGE.read_text())
    }
    assert found, "no cohort entries parsed — the table's shape changed, so this test is blind"
    return found


@pytest.fixture(scope="module")
def computed() -> dict[str, tuple[str, int, int]]:
    corpus = Corpus.load()
    scorer, vulnerability = RiskScorer(corpus), VulnerabilityScorer()
    planner = PreventionPlanBuilder(corpus, InteractionTable.load())
    out = {}
    personas = PersonaLoader()
    places = personas.places()
    for person in personas.load().values():
        # Per-person exposure, via the same helper the API uses. A single shared
        # fixture gives every persona a top-floor flat's bedroom, which changes
        # plan length for the people in bungalows and would report drift that is
        # only this test using a different building.
        day = heat_fixture_for(places[person.id].dwelling_offset)
        assessment = scorer.assess(day, vulnerability.profile(person))
        # CAREGIVER: the register is a professional view, and it is the audience
        # the published figures were generated against. CARED_FOR yields a
        # shorter plan, so picking the wrong one here silently redefines drift.
        plan = planner.build(person, day, assessment, Audience.CAREGIVER)
        out[person.name] = (
            assessment.tier.name.title(),
            assessment.vulnerability_score,
            len(plan.items),
        )
    return out


def test_every_published_person_is_a_real_persona(published, computed):
    assert set(published) <= set(computed)


@pytest.mark.parametrize("field", ["tier", "vulnerability", "plan items"])
def test_the_published_table_matches_the_engine(published, computed, field):
    index = ["tier", "vulnerability", "plan items"].index(field)
    wrong = {
        name: (row[index], computed[name][index])
        for name, row in published.items()
        if row[index] != computed[name][index]
    }
    assert not wrong, f"/monitoring shows a stale {field} — published vs engine: {wrong}"
