"""When advice stops being enough.

The failure this guards is subtle and one-directional: the system talking itself
out of a visit. Every test below asks whether some piece of apparent reassurance
is allowed to lower the response, and the answer is almost always no.
"""

from datetime import date

import pytest
from actions.escalation import EscalationPolicy, Responder, Urgency
from contracts import (
    AgeBand,
    Condition,
    DateRange,
    Med,
    MedClass,
    Person,
    RedFlag,
    SelfReport,
    Tier,
)

TODAY = date(2026, 7, 26)
WINDOW = DateRange(start=TODAY, end=TODAY)


@pytest.fixture
def policy() -> EscalationPolicy:
    return EscalationPolicy()


def someone(*conditions: Condition, name: str = "Doris") -> Person:
    return Person(
        id=name.lower(),
        name=name,
        age_band=AgeBand.B85_PLUS,
        lives_alone=True,
        mobility_limited=False,
        conditions=tuple(conditions),
        medications=(Med("furosemide", MedClass.DIURETIC),),
    )


def answered_with(*flags: RedFlag) -> SelfReport:
    return SelfReport(person_id="doris", window=WINDOW, answered=True, red_flags=tuple(flags))


NO_ANSWER = SelfReport(person_id="doris", window=WINDOW, answered=False)
ANSWERED = SelfReport(person_id="doris", window=WINDOW, answered=True)


class TestSilence:
    """A missed check-in is the condition the product exists to catch."""

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            (Tier.ELEVATED, Urgency.VISIT_TODAY),
            (Tier.HIGH, Urgency.VISIT_NOW),
            (Tier.SEVERE, Urgency.VISIT_NOW),
        ],
    )
    def test_no_answer_during_a_risk_window_sends_someone(self, policy, tier, expected):
        decision = policy.decide(someone(), tier, report=NO_ANSWER, has_caregiver=True)
        assert decision.urgency is expected
        assert decision.needs_visit

    def test_no_answer_at_low_risk_is_not_an_escalation(self, policy):
        """Not every unanswered phone is an emergency. Ringing again tomorrow is
        the proportionate response to a mild day."""
        decision = policy.decide(someone(), Tier.LOW, report=NO_ANSWER, has_caregiver=True)
        assert decision.urgency is Urgency.NONE

    def test_the_reason_says_go_round_rather_than_retry(self, policy):
        decision = policy.decide(someone(), Tier.HIGH, report=NO_ANSWER, has_caregiver=True)
        assert "go round" in decision.reason


class TestUnreliableSelfReport:
    """The heart of it: an answer is only evidence if the answerer can give one."""

    def test_a_reassuring_answer_from_someone_with_dementia_still_sends_someone(self, policy):
        """The live insight this module was written for. "She said she's fine" is
        not evidence she is, and must not talk anyone out of the visit."""
        decision = policy.decide(
            someone(Condition.DEMENTIA), Tier.HIGH, report=ANSWERED, has_caregiver=True
        )
        assert decision.needs_visit
        assert "may not notice" in decision.reason

    def test_the_same_answer_from_someone_who_can_report_does_not(self, policy):
        """The contrast that makes the rule meaningful rather than blanket
        caution — otherwise every High tier would demand a visit."""
        decision = policy.decide(
            someone(Condition.CARDIOVASCULAR),
            Tier.HIGH,
            report=ANSWERED,
            has_caregiver=True,
        )
        assert not decision.needs_visit

    def test_severe_sends_someone_regardless_of_who_answered(self, policy):
        decision = policy.decide(
            someone(Condition.CARDIOVASCULAR),
            Tier.SEVERE,
            report=ANSWERED,
            has_caregiver=True,
        )
        assert decision.needs_visit


class TestRedFlags:
    """SC-3: 999 is named only alongside an explicit flag, never inferred."""

    @pytest.mark.parametrize("flag", list(RedFlag))
    def test_any_red_flag_is_an_emergency(self, policy, flag):
        decision = policy.decide(
            someone(), Tier.ELEVATED, report=answered_with(flag), has_caregiver=True
        )
        assert decision.urgency is Urgency.EMERGENCY
        assert decision.responder is Responder.AMBULANCE

    def test_a_red_flag_outranks_a_calm_tier(self, policy):
        """The flags describe a body in trouble now; the tier is a forecast."""
        decision = policy.decide(
            someone(),
            Tier.LOW,
            report=answered_with(RedFlag.NO_URINE_OUTPUT),
            has_caregiver=True,
        )
        assert decision.urgency is Urgency.EMERGENCY

    def test_999_is_never_named_without_one(self, policy):
        for tier in (Tier.ELEVATED, Tier.HIGH, Tier.SEVERE):
            for answered in (True, False):
                decision = policy.decide(
                    someone(Condition.DEMENTIA),
                    tier,
                    report=ANSWERED if answered else NO_ANSWER,
                    has_caregiver=True,
                )
                assert "999" not in decision.reason

    def test_the_flag_is_named_in_plain_words(self, policy):
        """A caregiver reading this at speed should not have to decode
        "no_urine_output"."""
        decision = policy.decide(
            someone(),
            Tier.HIGH,
            report=answered_with(RedFlag.NO_URINE_OUTPUT),
            has_caregiver=True,
        )
        assert "not passing water" in decision.reason


class TestWhoResponds:
    """Somebody nearby beats somebody official."""

    def test_a_caregiver_is_asked_first(self, policy):
        decision = policy.decide(someone(), Tier.HIGH, report=NO_ANSWER, has_caregiver=True)
        assert decision.responder is Responder.CAREGIVER

    def test_someone_with_nobody_falls_to_the_council(self, policy):
        """These are exactly the people the register exists to surface."""
        decision = policy.decide(someone(), Tier.HIGH, report=NO_ANSWER, has_caregiver=False)
        assert decision.responder is Responder.COUNCIL

    def test_low_risk_asks_nobody(self, policy):
        decision = policy.decide(someone(), Tier.LOW, report=ANSWERED, has_caregiver=True)
        assert decision.responder is Responder.NOBODY
        assert not decision.needs_visit


class TestHistory:
    """A pattern is a different fact from an incident."""

    def test_one_missed_call_on_a_mild_risk_asks_for_a_visit_today(self, policy):
        """Someone was in the garden. Proportionate, not alarming."""
        decision = policy.decide(
            someone(), Tier.ELEVATED, report=NO_ANSWER, has_caregiver=True, consecutive_missed=1
        )
        assert decision.urgency is Urgency.VISIT_TODAY

    def test_two_in_a_row_escalates_even_at_the_same_tier(self, policy):
        """The tier has not moved; what changed is that nobody has confirmed how
        she is for two windows running."""
        decision = policy.decide(
            someone(), Tier.ELEVATED, report=NO_ANSWER, has_caregiver=True, consecutive_missed=2
        )
        assert decision.urgency is Urgency.VISIT_NOW

    def test_the_pattern_is_stated_so_the_reader_can_judge_it(self, policy):
        decision = policy.decide(
            someone(), Tier.ELEVATED, report=NO_ANSWER, has_caregiver=True, consecutive_missed=3
        )
        assert "3 missed check-ins in a row" in decision.reason

    def test_history_cannot_lower_a_response(self, policy):
        """A run of answered check-ins is not evidence about tonight — the whole
        point is that conditions changed."""
        calm = policy.decide(
            someone(Condition.DEMENTIA),
            Tier.HIGH,
            report=ANSWERED,
            has_caregiver=True,
            consecutive_missed=0,
        )
        assert calm.needs_visit


class TestWording:
    """The message is read at speed by a frightened person. It has to parse."""

    def test_the_emergency_detail_is_a_phrase_not_a_sentence(self, policy):
        """It is dropped into "has reported ___", so a full sentence there gives
        "has reported They reported new confusion." and a second "call 999"."""
        decision = policy.decide(
            someone(), Tier.HIGH, report=answered_with(RedFlag.CONFUSION), has_caregiver=True
        )
        assert decision.detail == "new confusion"
        assert "999" not in decision.detail
        assert not decision.detail.endswith(".")

    def test_several_flags_read_as_a_list(self, policy):
        decision = policy.decide(
            someone(),
            Tier.HIGH,
            report=answered_with(RedFlag.CONFUSION, RedFlag.NO_URINE_OUTPUT),
            has_caregiver=True,
        )
        assert decision.detail == "new confusion, not passing water"

    def test_non_emergencies_carry_no_detail(self, policy):
        decision = policy.decide(someone(), Tier.HIGH, report=NO_ANSWER, has_caregiver=True)
        assert decision.detail == ""
