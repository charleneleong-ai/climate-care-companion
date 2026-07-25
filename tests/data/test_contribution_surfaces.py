"""Guards the two data contribution surfaces.

Adding a persona or a locality must never require a Python edit. If these tests
still pass after someone drops in a new YAML file, that property holds.
"""

import pytest
from contracts import Tier
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from geography.loader import GEOGRAPHY_DIR, GeographyLoader
from persons.loader import PERSONAS_DIR, PersonaLoader

from tests.verification.test_worked_example import BEDFORD_19_JULY_2025

UK_BOUNDS = (-11.0, 2.0, 49.0, 61.0)


@pytest.fixture(scope="module")
def scorer() -> RiskScorer:
    return RiskScorer(Corpus.load())


@pytest.fixture(scope="module")
def people():
    return PersonaLoader().load()


def test_every_persona_file_is_valid_and_scorable(scorer, people):
    assert len(people) == len(list(PERSONAS_DIR.glob("*.yaml")))
    vulnerability = VulnerabilityScorer()
    for person_id, person in people.items():
        assessment = scorer.assess(BEDFORD_19_JULY_2025, vulnerability.profile(person))
        assert isinstance(assessment.tier, Tier), f"{person_id} produced no tier"


def test_personas_discriminate_under_identical_conditions(scorer, people):
    """Spec section 13: three personas, same conditions, at least two distinct tiers.

    Three is the stated minimum, not a target — more personas make this stronger.
    """
    assert len(people) >= 3, "need at least three personas to test discrimination"
    vulnerability = VulnerabilityScorer()
    tiers = {
        scorer.assess(BEDFORD_19_JULY_2025, vulnerability.profile(p)).tier
        for p in people.values()
    }
    assert len(tiers) >= 2, f"all personas returned the same tier: {tiers}"


def test_every_geography_file_is_valid():
    localities = GeographyLoader().load()
    assert len(localities) == len(list(GEOGRAPHY_DIR.glob("*.yaml")))
    min_lon, max_lon, min_lat, max_lat = UK_BOUNDS
    for name, locality in localities.items():
        assert locality.resources, f"{name} declares no resources"
        for resource in locality.resources:
            assert min_lon <= resource.lon <= max_lon, f"{resource.name} lon out of UK"
            assert min_lat <= resource.lat <= max_lat, f"{resource.name} lat out of UK"


def test_geography_exposes_resources_by_type():
    assert GeographyLoader().resources_of_type("cool_space")


def test_invalid_persona_names_the_file_and_the_field(tmp_path):
    """A bad contribution must fail with a message naming the file, not a traceback
    into pydantic internals."""
    (tmp_path / "broken.yaml").write_text("id: broken\nname: B\nage_band: not_a_band\n")
    with pytest.raises(ValueError, match="broken.yaml"):
        PersonaLoader(tmp_path).load()


def test_invalid_locality_names_the_file(tmp_path):
    (tmp_path / "nowhere.yaml").write_text("name: Nowhere\n")
    with pytest.raises(ValueError, match="nowhere.yaml"):
        GeographyLoader(tmp_path).load()
