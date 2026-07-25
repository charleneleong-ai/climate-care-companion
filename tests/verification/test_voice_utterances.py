"""Merge gate. The voice agent selects from the corpus — it never composes.

This is what makes the spec section 6 constraint enforceable rather than
aspirational: the agent cannot acquire the ability to compose a sentence without
one of these going red.
"""

import pytest
from checkin.script import CheckinScript
from contracts import Assessment, Reason, ReasonCode, Tier
from core.corpus import FORBIDDEN_MEDICATION_ADVICE, PROFESSIONALS, Corpus


@pytest.fixture(scope="module")
def script() -> CheckinScript:
    return CheckinScript(Corpus.load())


def test_every_possible_utterance_is_sourced_from_the_action_corpus(script):
    corpus_text = {row.text for row in script.corpus.actions}
    unsourced = script.all_utterances - corpus_text
    assert not unsourced, f"utterances not traceable to the corpus: {unsourced}"


def test_no_utterance_can_advise_altering_a_prescription(script):
    """SC-1, enforced on the spoken surface specifically."""
    offending = [
        u for u in script.all_utterances if FORBIDDEN_MEDICATION_ADVICE.search(u)
    ]
    assert not offending, f"SC-1 violation in voice utterances: {offending}"


def test_selected_utterances_are_a_subset_of_the_closed_set(script):
    assessment = Assessment(
        tier=Tier.HIGH, risk_score=6.0, exposure_score=3, vulnerability_score=10,
        reasons=(Reason(ReasonCode.MED_DIURETIC, "t", "e", 2),),
    )
    assert set(script.utterances_for(assessment)) <= script.all_utterances


def test_every_medication_utterance_routes_to_a_professional(script):
    """SC-1: state the risk, then direct to a pharmacist or GP. Never advise a change."""
    med_rows = script.corpus.medication_actions()
    assert med_rows
    for row in med_rows:
        assert row.escalate_to in PROFESSIONALS, (
            f"{row.reason_code} states a medication risk with no professional to call"
        )
