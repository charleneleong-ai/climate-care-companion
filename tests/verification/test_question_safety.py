"""Merge gate for the personalised questionnaire.

Personalisation is selection from a validated bank, never generation. These assert
that property holds and that SC-3 screening cannot be silently lost.
"""

import pytest
from checkin.questions import QuestionBank, Register
from contracts import Assessment, Reason, ReasonCode, RedFlag, Tier
from core.corpus import FORBIDDEN_MEDICATION_ADVICE

SELF_REPORTABLE_FLAGS = {RedFlag.CONFUSION, RedFlag.NO_URINE_OUTPUT, RedFlag.HOT_DRY_SKIN}


@pytest.fixture(scope="module")
def bank() -> QuestionBank:
    return QuestionBank.load()


def test_no_question_can_advise_altering_a_prescription(bank):
    """SC-1. A question is not a route around the medication constraint."""
    offending = [
        (row.code, text)
        for row in bank.rows
        for text in (row.text, row.text_simple)
        if FORBIDDEN_MEDICATION_ADVICE.search(text)
    ]
    assert not offending, f"SC-1 violation in questions: {offending}"


def test_every_question_is_answerable_yes_or_no(bank):
    """ConsoleVoice maps replies onto a closed set. An open question produces text
    the system would have to interpret, which is exactly what section 6 forbids."""
    for row in bank.rows:
        for text in (row.text, row.text_simple):
            assert text.rstrip().endswith("?"), f"{row.code} is not a question: {text!r}"
            opener = text.split()[0].lower()
            assert opener not in {"what", "how", "why", "when", "where", "who"}, (
                f"{row.code} is open-ended and cannot be answered yes or no: {text!r}"
            )


def test_every_question_has_both_registers(bank):
    """A missing simplified phrasing would silently fall back to a two-clause
    question for someone with dementia."""
    for row in bank.rows:
        assert row.text.strip(), f"{row.code} has no standard phrasing"
        assert row.text_simple.strip(), f"{row.code} has no simplified phrasing"


SUBORDINATORS = (" rather than", " whether", " unless", " although", " which", " while")


def test_the_simplified_phrasing_is_a_single_clause(bank):
    """Comprehension, not brevity.

    Length is the wrong proxy: "Have you been to the toilet today?" is longer than
    "Have you passed water today?" and unambiguously simpler, because the second is
    clinical euphemism. What actually matters is that the simplified phrasing is one
    clause someone can hold in mind while answering.
    """
    for row in bank.rows:
        simple = row.text_simple
        assert "," not in simple, f"{row.code}'s simplified phrasing has a second clause"
        for word in SUBORDINATORS:
            assert word not in simple.lower(), (
                f"{row.code}'s simplified phrasing subordinates on {word.strip()!r}"
            )


@pytest.mark.parametrize("flag", sorted(SELF_REPORTABLE_FLAGS), ids=lambda f: f.name)
def test_every_self_reportable_red_flag_has_a_screen(bank, flag):
    """SC-3. Escalation to 999 is only permitted alongside an explicit red flag, so
    a flag with no question is a flag that can never be established."""
    assert any(row.red_flag is flag for row in bank.rows), f"no question screens for {flag}"


def test_unrousable_is_carried_by_the_no_answer_path_not_a_question(bank):
    """Someone unrousable cannot answer a question about being unrousable. Asking it
    would return None and read as 'not flagged', which is the dangerous direction."""
    assert all(row.red_flag is not RedFlag.UNROUSABLE for row in bank.rows)


def test_red_flag_screens_survive_the_length_cap(bank):
    """A truncated questionnaire must never be how an SC-3 screen goes unasked."""
    every_code = tuple(ReasonCode)
    assessment = Assessment(
        tier=Tier.SEVERE, risk_score=20.0, exposure_score=8, vulnerability_score=15,
        reasons=tuple(Reason(c, "t", "e", 1) for c in every_code),
    )
    from contracts import DateRange
    from datetime import date

    questionnaire = bank.build_for(
        "stress", DateRange(date(2025, 7, 19), date(2025, 7, 20)), assessment
    )
    screened = {q.red_flag for q in questionnaire.questions if q.red_flag}
    assert screened == SELF_REPORTABLE_FLAGS


def test_red_flag_polarity_is_declared_for_every_screen(bank):
    """'Have you passed water today?' flags on no; 'do you feel muddled?' flags on
    yes. Inferring this would invert a screen the first time someone adds a
    negatively-phrased question."""
    urine = next(row for row in bank.rows if row.red_flag is RedFlag.NO_URINE_OUTPUT)
    confusion = next(row for row in bank.rows if row.red_flag is RedFlag.CONFUSION)
    assert urine.red_flag_when is False
    assert confusion.red_flag_when is True


def test_a_question_writing_to_an_unknown_field_refuses_to_load(tmp_path):
    path = tmp_path / "questions.csv"
    path.write_text(
        "code,reason_code,tier_min,text,text_simple,answer_field,red_flag,red_flag_when,ordering\n"
        'q_bad,,elevated,"Are you alright?","Alright?",not_a_field,,,10\n'
    )
    with pytest.raises(ValueError, match="not a SelfReport field"):
        QuestionBank.load(path)


