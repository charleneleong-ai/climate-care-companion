"""Every stub must fail loudly and name its owning track.

ChecklistBuilder is gone from this list: it became PreventionPlanBuilder and is
implemented, so its coverage lives in tests/actions.

These stay red until claimed. A contributor picking up a track turns exactly the
tests listed against it in CONTRIBUTING.md.
"""

import pytest
from contracts import OrgType
from org.models import Cohort, CohortMember, Org
from org.views import CareHomeView, CouncilView, HospitalView
from predictors.backtest import SeasonBacktest
from predictors.cold_lag import ColdLagTracker
from predictors.heatwave import EnsembleHeatwave
from predictors.indoor import LearnedIndoor

STUBS = [
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


def test_cohort_membership_requires_a_consent_basis():
    """SC-6 enforced structurally, not remembered."""
    with pytest.raises(TypeError):
        CohortMember(cohort_id="c", person_id="p")
