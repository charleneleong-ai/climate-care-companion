"""NFR-07: tier must never be conveyed by colour alone.

Colour-blindness, greyscale printing and glare on a phone screen in a sunny
kitchen each defeat colour on its own, so every tier carries text and a shape too.
"""

from pathlib import Path

import pytest
from contracts import Tier

WEB = Path(__file__).resolve().parents[2] / "web"
TIER_JS = WEB / "shared" / "tier.js"
SURFACES = ["companion", "national", "explorer"]


@pytest.fixture(scope="module")
def tier_source() -> str:
    return TIER_JS.read_text()


@pytest.mark.parametrize("tier", list(Tier), ids=lambda t: t.name)
def test_every_tier_appears_in_the_shared_vocabulary(tier, tier_source):
    assert tier.name in tier_source, f"{tier.name} missing from the tier vocabulary"


def test_tier_vocabulary_defines_a_shape_channel(tier_source):
    assert "shape" in tier_source, "tier is conveyed by colour alone — NFR-07 violation"


def test_modelled_values_have_a_labelling_helper(tier_source):
    """SC-5: the label travels with the number rather than being remembered."""
    assert "renderModelled" in tier_source
    assert "Modelled estimate" in tier_source


@pytest.mark.parametrize("surface", SURFACES)
def test_surfaces_import_the_shared_vocabulary(surface):
    html = (WEB / surface / "index.html").read_text()
    assert "shared/tier" in html, f"{surface} does not use the shared tier component"


def test_companion_declares_accessible_minimums():
    """NFR-05 and NFR-06: 360px, >=16px body text, >=44px tap targets."""
    html = (WEB / "companion" / "index.html").read_text()
    assert "font-size:16px" in html
    assert "min-height:44px" in html
    assert "viewport" in html


def test_companion_caches_for_offline_use():
    """NFR-04: render a complete assessment with no network."""
    html = (WEB / "companion" / "index.html").read_text()
    assert "localStorage" in html


def test_companion_carries_the_not_medical_advice_statement():
    """SC-2."""
    html = (WEB / "companion" / "index.html").read_text()
    assert "not medical advice" in html.lower()
