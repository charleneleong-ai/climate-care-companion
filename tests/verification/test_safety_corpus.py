"""SC-1 merge gate. Zero matches required across the whole corpus.

The system shall never advise stopping, reducing, delaying or altering a prescribed
medication. Medication reason codes state the risk and direct the user to a
pharmacist or GP.

The word list lives in core.corpus as a single constant and is enforced at load
time. These tests assert the gate is wired to the real corpus — they do not restate
the list, because three copies with three different word lists is how a safety gate
silently weakens.
"""

from core.corpus import FORBIDDEN_MEDICATION_ADVICE, PROFESSIONALS


def test_no_medication_action_advises_altering_a_prescription(corpus):
    offending = [
        (row.reason_code, row.text)
        for row in corpus.medication_actions()
        if FORBIDDEN_MEDICATION_ADVICE.search(row.text)
    ]
    assert not offending, f"SC-1 violation: {offending}"


def test_medication_actions_direct_to_a_professional(corpus):
    """State the risk, then route. A risk with nobody to call is not an action."""
    med_rows = corpus.medication_actions()
    assert med_rows, "the corpus has no medication rows to check"
    for row in med_rows:
        assert row.escalate_to in PROFESSIONALS, (
            f"{row.reason_code} states a medication risk without routing to a professional"
        )


def test_no_reason_explanation_advises_altering_a_prescription(corpus):
    """Explanations are displayed too, so they carry the same constraint."""
    offending = [
        (code, reason.explanation)
        for code, reason in corpus.reasons.items()
        if code.startswith("med_")
        and FORBIDDEN_MEDICATION_ADVICE.search(reason.explanation)
    ]
    assert not offending, f"SC-1 violation in reason text: {offending}"
