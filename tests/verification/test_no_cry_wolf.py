"""Spec section 13. A low-vulnerability persona must return Low on all 92 days.

False negatives are the dominant safety risk (SC-7), so thresholds are set to
over-warn. This gate is the counterweight: over-warning on genuinely benign weather
destroys the signal just as surely as missing a real episode.
"""

import pytest
from contracts import Tier
from core.vulnerability import VulnerabilityScorer
from persons.loader import PersonaLoader


@pytest.fixture(scope="module")
def people():
    return PersonaLoader().load()


def test_low_vulnerability_persona_never_alarms_across_the_season(
    scorer, benign_season, people
):
    profile = VulnerabilityScorer().profile(people["margaret"])
    tiers = [scorer.assess(day, profile).tier for day in benign_season]
    cried = sum(tier is not Tier.LOW for tier in tiers)
    assert cried == 0, f"cried wolf on {cried} of 92 benign days"


def test_even_the_frailest_persona_stays_low_in_benign_weather(
    scorer, benign_season, people
):
    """FR-18 across a whole season, not just one day. Frailty alone is not harm."""
    profile = VulnerabilityScorer().profile(people["doris"])
    assert profile.score == 10
    assert {scorer.assess(day, profile).tier for day in benign_season} == {Tier.LOW}


def test_every_persona_stays_low_across_the_benign_season(
    scorer, benign_season, people
):
    vulnerability = VulnerabilityScorer()
    for person_id, person in people.items():
        profile = vulnerability.profile(person)
        tiers = {scorer.assess(day, profile).tier for day in benign_season}
        assert tiers == {Tier.LOW}, f"{person_id} alarmed in benign weather: {tiers}"
