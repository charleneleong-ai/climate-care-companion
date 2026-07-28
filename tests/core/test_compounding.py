"""Several factors together are not the same as several factors separately.

Every other vulnerability rule asks "does this person have X?", and the score is
their sum — arithmetic that treats each factor as acting alone. Three conditions
and three heat-acting medicine classes overlap in the systems heat already
strains, so the sum understates the person carrying all of them.

These rules exist to say that, and the tests below pin the two things most
likely to go quietly wrong: the threshold, and what counts as one factor.
"""

import pytest
from contracts import AgeBand, Condition, Med, MedClass, Person, ReasonCode
from core.vulnerability import VulnerabilityScorer


def person(conditions=(), med_classes=()) -> Person:
    return Person(
        id="test",
        name="Test",
        age_band=AgeBand.B65_74,
        lives_alone=False,
        mobility_limited=False,
        conditions=tuple(conditions),
        medications=tuple(Med(f"drug-{i}", c) for i, c in enumerate(med_classes)),
    )


@pytest.fixture(scope="module")
def scorer() -> VulnerabilityScorer:
    return VulnerabilityScorer()


def codes(scorer: VulnerabilityScorer, p: Person) -> set[ReasonCode]:
    return set(scorer.profile(p).codes)


CONDITIONS = (Condition.CARDIOVASCULAR, Condition.RENAL, Condition.RESPIRATORY)
CLASSES = (MedClass.DIURETIC, MedClass.ACE_ARB, MedClass.SSRI)


class TestMultimorbidity:
    @pytest.mark.parametrize("count", [0, 1, 2])
    def test_below_three_conditions_does_not_fire(self, scorer, count):
        assert ReasonCode.MULTIMORBIDITY not in codes(scorer, person(CONDITIONS[:count]))

    def test_three_conditions_fires(self, scorer):
        assert ReasonCode.MULTIMORBIDITY in codes(scorer, person(CONDITIONS))

    def test_it_adds_to_the_individual_conditions_rather_than_replacing_them(self, scorer):
        """The compounding is on top of each condition's own weight, not instead
        of it — otherwise naming the overlap would discount the parts."""
        found = codes(scorer, person(CONDITIONS))
        assert {ReasonCode.CARDIOVASCULAR, ReasonCode.RENAL, ReasonCode.RESPIRATORY} <= found


class TestPolypharmacy:
    @pytest.mark.parametrize("count", [0, 1, 2])
    def test_below_three_classes_does_not_fire(self, scorer, count):
        assert ReasonCode.MED_POLYPHARMACY not in codes(scorer, person(med_classes=CLASSES[:count]))

    def test_three_classes_fires(self, scorer):
        assert ReasonCode.MED_POLYPHARMACY in codes(scorer, person(med_classes=CLASSES))

    def test_repeats_of_one_class_are_one_mechanism(self, scorer):
        """Four medicines, all diuretics, is a single mechanism dosed four times.
        Counting medicines rather than classes would call that polypharmacy and
        score someone on one drug type as though they were on four."""
        four_of_a_kind = person(med_classes=(MedClass.DIURETIC,) * 4)
        assert ReasonCode.MED_POLYPHARMACY not in codes(scorer, four_of_a_kind)

    def test_only_heat_relevant_classes_count(self, scorer):
        """The threshold is 3 rather than the conventional 5 precisely because
        every class counted here already acts on heat. A medicine the model does
        not track must not push someone over the line."""
        tracked_pair = person(med_classes=(MedClass.DIURETIC, MedClass.SSRI))
        assert ReasonCode.MED_POLYPHARMACY not in codes(scorer, tracked_pair)


def test_carrying_both_burdens_scores_higher_than_either(scorer):
    """Victor is the case this was built for: three conditions and four medicine
    classes. He should separate from someone carrying one of the two."""
    conditions_only = scorer.profile(person(CONDITIONS)).score
    medicines_only = scorer.profile(person(med_classes=CLASSES)).score
    both = scorer.profile(person(CONDITIONS, CLASSES)).score

    assert both > conditions_only
    assert both > medicines_only
