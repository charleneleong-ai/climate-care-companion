"""The generated files must match the Python they came from.

Without this, someone edits a threshold in core/rules.py, forgets to regenerate,
and the companion silently keeps scoring on the old value — which is exactly how
the COLD_GUARD came to exist in one engine and not the other.

The check regenerates in memory and compares. It never writes, so a stale file
fails the build rather than being quietly fixed underneath the author.
"""

from core.corpus import Corpus
from core.export import CORPUS_PATH, RULES_PATH, RuleExporter

REGENERATE = "stale — run: uv run python -m core.export"


def exporter() -> RuleExporter:
    return RuleExporter(Corpus.load())


def test_the_generated_rules_match_the_python_tables():
    assert RULES_PATH.exists(), REGENERATE
    expected = exporter().render(exporter().rules_document())
    assert RULES_PATH.read_text() == expected, f"{RULES_PATH.name} is {REGENERATE}"


def test_the_parity_corpus_matches_what_python_scores_today():
    assert CORPUS_PATH.exists(), REGENERATE
    expected = exporter().render(exporter().corpus_document())
    assert CORPUS_PATH.read_text() == expected, f"{CORPUS_PATH.name} is {REGENERATE}"


def test_the_corpus_pins_boundaries_rather_than_the_comfortable_middle():
    """A parity corpus of easy cases proves nothing. These are the inputs where two
    independent implementations could plausibly disagree."""
    names = {case["name"] for case in exporter().corpus_document()["cases"]}
    assert {
        "spec_8_6_worked_example",
        "zero_exposure_frail_person_stays_low",
        "cold_guard_suppresses_on_a_mild_day",
        "cold_codes_fire_in_genuine_cold",
    } <= names


def test_every_exported_rule_carries_its_explanation():
    """The companion renders these to a caregiver, so a rule exported without text
    would surface as a blank reason."""
    document = exporter().rules_document()
    for rule in document["exposure_rules"] + document["vulnerability_rules"]:
        assert rule["title"].strip(), f"{rule['code']} exported with no title"
        assert rule["why"].strip(), f"{rule['code']} exported with no explanation"
