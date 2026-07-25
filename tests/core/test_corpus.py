import re

import pytest
from contracts import MedClass, ReasonCode
from core.corpus import Corpus

FORBIDDEN = re.compile(r"\b(stop|reduce|skip|halt|delay|alter)\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return Corpus.load()


def test_every_reason_code_has_title_and_explanation(corpus):
    assert set(corpus.reasons) == set(ReasonCode)
    for code, reason in corpus.reasons.items():
        assert reason.title.strip(), f"{code} has an empty title"
        assert reason.explanation.strip(), f"{code} has an empty explanation"


def test_every_reason_code_maps_to_at_least_one_action(corpus):
    """AC-3: a reason code with no action is a specification defect."""
    missing = [c for c in ReasonCode if not corpus.actions_for(c)]
    assert not missing, f"reason codes with no action: {sorted(missing)}"


def test_medication_actions_never_advise_altering_a_prescription(corpus):
    """SC-1. Zero matches required."""
    offending = [
        (row.reason_code, row.text)
        for row in corpus.actions
        if row.reason_code.startswith("med_") and FORBIDDEN.search(row.text)
    ]
    assert not offending, f"SC-1 violation: {offending}"


@pytest.mark.parametrize(
    "drug,expected",
    [
        ("furosemide", MedClass.DIURETIC),
        ("ramipril", MedClass.ACE_ARB),
        ("lithium carbonate", MedClass.LITHIUM),
        ("oxybutynin", MedClass.ANTICHOLINERGIC),
        ("bisoprolol", MedClass.BETA_BLOCKER),
        ("sertraline", MedClass.SSRI),
        ("olanzapine", MedClass.ANTIPSYCHOTIC),
        ("insulin", MedClass.HEAT_SENSITIVE),
    ],
)
def test_classify_resolves_spec_8_3_examples(corpus, drug, expected):
    assert corpus.classify(drug) is expected


def test_classify_is_case_insensitive(corpus):
    assert corpus.classify("Furosemide") is MedClass.DIURETIC


def test_unknown_drug_classifies_as_other_rather_than_raising(corpus):
    """A caregiver's typo must not take the whole assessment down."""
    assert corpus.classify("a drug nobody has heard of") is MedClass.OTHER


def test_load_raises_when_a_reason_code_is_missing_from_the_yaml(tmp_path):
    (tmp_path / "reasons.yaml").write_text("bedroom_warm:\n  title: t\n  explanation: e\n")
    (tmp_path / "actions.csv").write_text("reason_code,tier_min,text,escalate_to,ordering\n")
    (tmp_path / "med_classes.csv").write_text("drug_name,drug_class\n")
    with pytest.raises(ValueError, match="missing reason text"):
        Corpus.load(tmp_path)


def test_actions_for_returns_only_that_codes_rows(corpus):
    rows = corpus.actions_for(ReasonCode.MED_DIURETIC)
    assert rows
    assert {r.reason_code for r in rows} == {ReasonCode.MED_DIURETIC}
