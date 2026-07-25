import pytest
from checkin.questions import QuestionBank, Register
from contracts import Assessment, DateRange, Reason, ReasonCode, RedFlag, Tier
from datetime import date

WINDOW = DateRange(date(2025, 7, 19), date(2025, 7, 20))


@pytest.fixture(scope="module")
def bank() -> QuestionBank:
    return QuestionBank.load()


def assessment(tier: Tier, *codes: ReasonCode) -> Assessment:
    return Assessment(
        tier=tier, risk_score=6.0, exposure_score=3, vulnerability_score=10,
        reasons=tuple(Reason(c, "t", "e", 1) for c in codes),
    )


def codes_of(questionnaire) -> list[str]:
    return [q.code for q in questionnaire.questions]


# ----------------------------------------------------------------- selection

def test_low_tier_asks_nothing(bank):
    q = bank.build_for("doris", WINDOW, assessment(Tier.LOW, ReasonCode.MED_DIURETIC))
    assert q.questions == ()


def test_only_questions_for_the_persons_own_reason_codes_are_asked(bank):
    q = bank.build_for("doris", WINDOW, assessment(Tier.ELEVATED, ReasonCode.MED_DIURETIC))
    texts = [item.text for item in q.questions]
    assert any("drink" in t for t in texts)
    assert not any("ankles" in t for t in texts), "asked a cardiovascular question of someone without it"


def test_questions_with_no_reason_code_are_always_asked(bank):
    q = bank.build_for("m", WINDOW, assessment(Tier.ELEVATED, ReasonCode.LIVES_ALONE))
    assert "q_wellbeing" in codes_of(q)


def test_duplicate_question_text_is_asked_only_once(bank):
    """Five medication codes map to the same fluids question. Nobody should be
    asked the same thing five times."""
    q = bank.build_for(
        "doris", WINDOW,
        assessment(Tier.ELEVATED, ReasonCode.MED_DIURETIC, ReasonCode.MED_ACE_ARB,
                   ReasonCode.MED_LITHIUM, ReasonCode.RENAL),
    )
    texts = [item.text for item in q.questions]
    assert len(texts) == len(set(texts))


def test_questions_below_the_tier_threshold_are_not_asked(bank):
    elevated = bank.build_for("d", WINDOW, assessment(Tier.ELEVATED, ReasonCode.DEMENTIA))
    assert "q_rf_confusion" not in codes_of(elevated), "red-flag screen fired below High"


# ------------------------------------------------------------------ register

def test_dementia_selects_the_simplified_register(bank):
    q = bank.build_for("doris", WINDOW, assessment(Tier.ELEVATED, ReasonCode.DEMENTIA,
                                                   ReasonCode.MED_DIURETIC))
    assert q.register is Register.SIMPLE
    assert any(item.text == "Have you had a drink?" for item in q.questions)


def test_without_dementia_the_standard_register_is_used(bank):
    q = bank.build_for("h", WINDOW, assessment(Tier.ELEVATED, ReasonCode.MED_DIURETIC))
    assert q.register is Register.STANDARD
    assert any("in the last hour" in item.text for item in q.questions)


# --------------------------------------------------------------------- length

def test_the_questionnaire_is_capped_so_it_stays_answerable(bank):
    every_code = tuple(ReasonCode)
    q = bank.build_for("d", WINDOW, assessment(Tier.ELEVATED, *every_code))
    assert len(q.questions) <= bank.max_questions(Tier.ELEVATED, Register.STANDARD)


def test_the_simplified_register_is_capped_shorter(bank):
    """Someone with dementia will not complete a long questionnaire, and a
    half-finished one is worse than a short complete one."""
    assert bank.max_questions(Tier.HIGH, Register.SIMPLE) < bank.max_questions(
        Tier.HIGH, Register.STANDARD
    )


def test_red_flag_questions_are_never_dropped_by_the_cap(bank):
    """SC-3. A truncated questionnaire must not be how a red flag goes unasked."""
    every_code = tuple(ReasonCode)
    q = bank.build_for("d", WINDOW,
                       assessment(Tier.SEVERE, ReasonCode.DEMENTIA, *every_code))
    asked = codes_of(q)
    for code in ("q_rf_confusion", "q_rf_urine", "q_rf_skin"):
        assert code in asked, f"{code} was dropped by the length cap"


# ------------------------------------------------------- answers to SelfReport

def test_answers_become_a_self_report(bank):
    q = bank.build_for("doris", WINDOW,
                       assessment(Tier.ELEVATED, ReasonCode.BEDROOM_WARM,
                                  ReasonCode.MED_DIURETIC))
    report = q.to_self_report({"q_bedroom_warm": True, "q_fluids_diuretic": False})
    assert report.person_id == "doris"
    assert report.answered is True
    assert report.bedroom_feels_hot is True
    assert report.drinking_fluids is False


def test_no_answers_at_all_is_an_unanswered_call(bank):
    """A missed call during a risk window is the condition the system exists to
    catch, so it is a first-class outcome rather than an error."""
    q = bank.build_for("doris", WINDOW, assessment(Tier.HIGH, ReasonCode.BEDROOM_WARM))
    report = q.to_self_report({})
    assert report.answered is False
    assert report.bedroom_feels_hot is None
    assert report.red_flags == ()


def test_unanswered_individual_questions_stay_none(bank):
    q = bank.build_for("d", WINDOW, assessment(Tier.ELEVATED, ReasonCode.BEDROOM_WARM))
    report = q.to_self_report({"q_wellbeing": True, "q_bedroom_warm": None})
    assert report.answered is True
    assert report.bedroom_feels_hot is None


# -------------------------------------------------------------- red flags SC-3

def test_a_yes_polarity_red_flag_fires_on_yes(bank):
    q = bank.build_for("d", WINDOW, assessment(Tier.HIGH, ReasonCode.AGE_85_PLUS))
    report = q.to_self_report({"q_rf_confusion": True})
    assert RedFlag.CONFUSION in report.red_flags


def test_a_no_polarity_red_flag_fires_on_no(bank):
    """'Have you passed water today?' flags on NO. Getting this backwards would
    silently invert an SC-3 screen."""
    q = bank.build_for("d", WINDOW, assessment(Tier.HIGH, ReasonCode.AGE_85_PLUS))
    report = q.to_self_report({"q_rf_urine": False})
    assert RedFlag.NO_URINE_OUTPUT in report.red_flags


def test_a_no_polarity_red_flag_does_not_fire_on_yes(bank):
    q = bank.build_for("d", WINDOW, assessment(Tier.HIGH, ReasonCode.AGE_85_PLUS))
    report = q.to_self_report({"q_rf_urine": True})
    assert RedFlag.NO_URINE_OUTPUT not in report.red_flags


def test_an_unanswered_red_flag_question_does_not_fire(bank):
    """Silence is escalated by the no-answer path, not by inventing a red flag."""
    q = bank.build_for("d", WINDOW, assessment(Tier.HIGH, ReasonCode.AGE_85_PLUS))
    report = q.to_self_report({"q_rf_confusion": None, "q_rf_urine": None})
    assert report.red_flags == ()


def test_unrousable_has_no_question_because_it_cannot_be_self_reported(bank):
    """Someone who is unrousable cannot answer a question about being unrousable.
    That red flag is carried by the no-answer path instead."""
    assert all(row.red_flag is not RedFlag.UNROUSABLE for row in bank.rows)
