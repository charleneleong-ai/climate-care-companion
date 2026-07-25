import pytest
from allocation.models import Candidate
from allocation.plans import AllocationEngine
from contracts import Assessment, Tier
from geography.loader import Resource


@pytest.fixture(scope="module")
def engine() -> AllocationEngine:
    return AllocationEngine()


def candidate(
    person_id: str,
    tier: Tier,
    *,
    alone: bool = True,
    mobility_limited: bool = False,
    lat: float = 52.13,
    lon: float = -0.46,
    has_cooling: bool = False,
) -> Candidate:
    return Candidate(
        person_id=person_id,
        assessment=Assessment(tier=tier, risk_score=float(tier) * 3, exposure_score=3,
                              vulnerability_score=10, reasons=()),
        lives_alone=alone,
        mobility_limited=mobility_limited,
        lat=lat,
        lon=lon,
        has_cooling=has_cooling,
    )


def cool_space(resource_id: str, lat: float, lon: float) -> Resource:
    return Resource(id=resource_id, type="cool_space", name=resource_id, lat=lat,
                    lon=lon, opening_hours="09:00-17:00", area_code="E07000032")


def test_higher_tier_outranks_lower_tier_all_else_equal(engine):
    plan = engine.rank_visits(
        [candidate("low", Tier.ELEVATED), candidate("high", Tier.SEVERE)], capacity=2)
    assert [v.person_id for v in plan.visits] == ["high", "low"]


def test_isolation_can_outrank_a_higher_tier(engine):
    """The design claim: optimise harm averted per visit, not risk observed.

    Severe-supported scores 5.0 x 1.15 = 5.75. High-alone scores
    3.0 x 2.0 x 1.15 = 6.90. The visit is worth more to the person nobody watches.
    """
    plan = engine.rank_visits(
        [candidate("severe_supported", Tier.SEVERE, alone=False),
         candidate("high_alone", Tier.HIGH, alone=True)],
        capacity=2,
    )
    assert plan.visits[0].person_id == "high_alone"


def test_lowering_the_isolation_factor_reverts_to_ranking_on_tier():
    """Guards the policy decision. Below the Severe/High ratio, tier dominates and
    the layer stops optimising for harm averted."""
    plan = AllocationEngine(isolation_factor=1.0).rank_visits(
        [candidate("severe_supported", Tier.SEVERE, alone=False),
         candidate("high_alone", Tier.HIGH, alone=True)],
        capacity=2,
    )
    assert plan.visits[0].person_id == "severe_supported"


def test_capacity_is_respected_and_the_remainder_is_reported(engine):
    plan = engine.rank_visits(
        [candidate(f"p{i}", Tier.HIGH) for i in range(10)], capacity=4)
    assert len(plan.visits) == 4
    assert plan.unvisited == 6
    assert plan.capacity == 4


def test_low_tier_is_never_scheduled_even_with_spare_capacity(engine):
    plan = engine.rank_visits(
        [candidate("a", Tier.LOW), candidate("b", Tier.LOW)], capacity=10)
    assert plan.visits == ()
    assert plan.unvisited == 0


def test_every_visit_carries_its_justification(engine):
    plan = engine.rank_visits(
        [candidate("a", Tier.SEVERE, mobility_limited=True)], capacity=1)
    rationale = plan.visits[0].rationale
    assert "severe" in rationale
    assert "mobility limited" in rationale
    assert "lives alone" in rationale


def test_ranking_is_stable_for_equal_priorities(engine):
    plan = engine.rank_visits(
        [candidate("zoe", Tier.HIGH), candidate("amy", Tier.HIGH)], capacity=2)
    assert [v.person_id for v in plan.visits] == ["amy", "zoe"]


def test_coverage_gap_finds_people_beyond_the_radius(engine):
    report = engine.coverage_gap(
        [candidate("near", Tier.SEVERE, lat=52.1364, lon=-0.4669),
         candidate("far", Tier.SEVERE, lat=52.5000, lon=-0.4669)],
        [cool_space("lib", 52.1364, -0.4669)], radius_km=1.0, min_tier=Tier.HIGH)
    assert {u.person_id for u in report.uncovered} == {"far"}
    assert report.covered_count == 1
    assert report.considered == 2


def test_coverage_gap_ignores_people_below_the_minimum_tier(engine):
    report = engine.coverage_gap(
        [candidate("mild", Tier.ELEVATED, lat=52.5, lon=-0.46)],
        [cool_space("lib", 52.1364, -0.4669)], radius_km=1.0, min_tier=Tier.HIGH)
    assert report.uncovered == ()
    assert report.considered == 0


def test_person_with_cooling_at_home_is_already_covered(engine):
    """The resource they need is the one they already have."""
    report = engine.coverage_gap(
        [candidate("cooled", Tier.SEVERE, lat=52.5, lon=-0.46, has_cooling=True)],
        [cool_space("lib", 52.1364, -0.4669)], radius_km=1.0, min_tier=Tier.HIGH)
    assert report.uncovered == ()
    assert report.covered_count == 1


def test_uncovered_person_reports_no_nearest_when_no_resources_exist(engine):
    """No resource at all is a different problem from one that is too far."""
    report = engine.coverage_gap(
        [candidate("alone", Tier.SEVERE)], [], radius_km=1.0, min_tier=Tier.HIGH)
    assert report.uncovered[0].nearest_km is None


def test_siting_delta_ranks_candidate_sites_by_people_newly_covered(engine):
    people = [candidate(f"p{i}", Tier.SEVERE, lat=52.50, lon=-0.46) for i in range(3)]
    people.append(candidate("lonely", Tier.SEVERE, lat=53.00, lon=-0.46))
    report = engine.coverage_gap(people, [], radius_km=1.0, min_tier=Tier.HIGH)

    options = engine.siting_delta(
        report,
        [cool_space("cluster", 52.50, -0.46), cool_space("outlier", 53.00, -0.46)],
        radius_km=1.0,
    )
    assert [o.resource_id for o in options] == ["cluster", "outlier"]
    assert options[0].newly_covered == 3
    assert options[1].newly_covered == 1


def test_siting_delta_with_no_uncovered_people_returns_zero_gain(engine):
    report = engine.coverage_gap([], [], radius_km=1.0, min_tier=Tier.HIGH)
    options = engine.siting_delta(
        report, [cool_space("anywhere", 52.5, -0.46)], radius_km=1.0)
    assert all(o.newly_covered == 0 for o in options)
