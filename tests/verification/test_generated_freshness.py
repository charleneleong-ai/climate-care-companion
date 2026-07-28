"""The generated files must match the Python they came from.

Without this, someone edits a threshold in core/rules.py, forgets to regenerate,
and the companion silently keeps scoring on the old value — which is exactly how
the COLD_GUARD came to exist in one engine and not the other.

The check regenerates in memory and compares. It never writes, so a stale file
fails the build rather than being quietly fixed underneath the author.
"""

from core.corpus import Corpus
from actions.export import CLINICAL_PATH, ClinicalExporter
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


def test_the_generated_clinical_content_matches_the_interaction_table():
    """Exported from actions rather than core: actions depends on core, so core
    cannot depend on actions without a circular package dependency."""
    assert CLINICAL_PATH.exists(), REGENERATE
    exporter = ClinicalExporter.load()
    assert CLINICAL_PATH.read_text() == exporter.render(), (
        f"{CLINICAL_PATH.name} is stale — run: uv run python -m actions.export"
    )


def test_every_interaction_exports_its_gating():
    """A rule exported without requires_flags or requires_self_report fires for
    everyone in the front end. Both have caused that already."""
    for rule in ClinicalExporter.load().document()["interactions"]:
        assert "requires_flags" in rule, f"{rule['code']} exported without flag gating"
        assert "requires_self_report" in rule, f"{rule['code']} exported without self-report gating"


def test_the_generated_questions_match_the_bank():
    """The front end selects from the same validated bank, or the closed-set
    property that makes an unsupervised questionnaire safe does not hold."""
    from checkin.export import QUESTIONS_PATH, QuestionExporter

    assert QUESTIONS_PATH.exists(), REGENERATE
    assert QUESTIONS_PATH.read_text() == QuestionExporter.load().render(), (
        f"{QUESTIONS_PATH.name} is stale — run: uv run python -m checkin.export"
    )
