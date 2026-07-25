"""Every stub must fail loudly and name its owning track.

ChecklistBuilder is gone from this list: it became PreventionPlanBuilder and is
implemented, so its coverage lives in tests/actions.

These stay red until claimed. A contributor picking up a track turns exactly the
tests listed against it in CONTRIBUTING.md.
"""

import pytest
from actions.notify import NotificationPolicy
from contracts import OrgType
from org.models import Cohort, CohortMember, Org
from org.views import CareHomeView, CouncilView, HospitalView
from predictors.backtest import SeasonBacktest
from predictors.cold_lag import ColdLagTracker
from predictors.heatwave import EnsembleHeatwave
from predictors.indoor import LearnedIndoor

STUBS = [
    (NotificationPolicy().should_notify, "Track A"),
    (CouncilView().render, "Track B"),
    (HospitalView().render, "Track B"),
    (CareHomeView().render, "Track B"),
    (ColdLagTracker().track, "Track B"),
    (SeasonBacktest().run, "Track B"),
    (LearnedIndoor().estimate, "Track B"),
]


@pytest.mark.parametrize("fn,track", STUBS, ids=lambda v: getattr(v, "__qualname__", v))
def test_stub_raises_and_names_its_owner(fn, track):
    with pytest.raises(NotImplementedError, match=track):
        fn()


def test_ensemble_predictor_stub_names_track_b():
    with pytest.raises(NotImplementedError, match="Track B"):
        EnsembleHeatwave().forecast([30.0], horizon_days=1)


def test_three_tenant_types_are_implemented_and_icb_is_declared():
    assert {OrgType.COUNCIL, OrgType.HOSPITAL, OrgType.CARE_HOME} <= set(OrgType)
    assert OrgType.ICB in OrgType


def test_cohort_membership_requires_a_consent_basis():
    """SC-6 enforced structurally, not remembered."""
    with pytest.raises(TypeError):
        CohortMember(cohort_id="c", person_id="p")


def test_cohort_membership_accepts_an_explicit_basis():
    member = CohortMember(cohort_id="c", person_id="p", consent_basis="explicit consent")
    assert member.consent_basis


def test_org_scopes_by_area_codes():
    org = Org(id="o", name="Bedford Borough Council", type=OrgType.COUNCIL,
              area_codes=("E07000032",))
    assert org.area_codes == ("E07000032",)


def test_cohort_belongs_to_exactly_one_org():
    cohort = Cohort(id="c1", org_id="o1", name="Adult social care caseload")
    assert cohort.org_id == "o1"
