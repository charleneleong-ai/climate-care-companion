from collections.abc import Sequence

from allocation.distance import haversine_km
from allocation.models import (
    AllocationPlan,
    Candidate,
    CoverageReport,
    SitingOption,
    UncoveredPerson,
    Visit,
)
from contracts import Tier
from geography.loader import Resource


class AllocationEngine:
    """Turns risk tiers into deployment decisions.

    Pure over its arguments, so it replays against historical seasons: "what optimal
    deployment on 17 July 2025 would have looked like" is a runnable demo rather
    than an assertion.

    The weights are constructor parameters rather than module constants because they
    are policy decisions a council may need to defend or change — not physics.
    """

    TIER_WEIGHT: dict[Tier, float] = {
        Tier.LOW: 0.0,
        Tier.ELEVATED: 1.0,
        Tier.HIGH: 3.0,
        Tier.SEVERE: 5.0,
    }

    def __init__(
        self,
        isolation_factor: float = 2.0,
        mobility_factor: float = 1.2,
        no_cooling_factor: float = 1.15,
    ) -> None:
        """isolation_factor defaults above the Severe/High tier ratio (5/3 = 1.67),
        so living alone can outrank one full tier step. Below 1.67 tier dominates
        and the layer reverts to ranking on risk observed rather than harm averted.
        """
        self.isolation_factor = isolation_factor
        self.mobility_factor = mobility_factor
        self.no_cooling_factor = no_cooling_factor

    def priority_of(self, candidate: Candidate) -> float:
        """Harm averted per visit, not risk observed.

        A Severe-tier person with a live-in carer is already being watched, so the
        marginal value of a council visit is lower than for a High-tier person
        living alone whom nobody is checking.
        """
        score = self.TIER_WEIGHT[candidate.assessment.tier]
        if score == 0.0:
            return 0.0
        if candidate.lives_alone:
            score *= self.isolation_factor
        if candidate.mobility_limited:
            score *= self.mobility_factor
        if not candidate.has_cooling:
            score *= self.no_cooling_factor
        return score

    @staticmethod
    def rationale_for(candidate: Candidate) -> str:
        parts = [f"{candidate.assessment.tier.name.lower()} tier"]
        if candidate.lives_alone:
            parts.append("lives alone")
        if candidate.mobility_limited:
            parts.append("mobility limited")
        if not candidate.has_cooling:
            parts.append("no cooling at home")
        return ", ".join(parts)

    def rank_visits(self, candidates: Sequence[Candidate], capacity: int) -> AllocationPlan:
        """Order a cohort for a fixed number of welfare visits.

        Low tier is never scheduled. FR-18 already established it means no action
        beyond routine, and a visit spent there is a visit not spent elsewhere.
        """
        eligible = [
            (priority, candidate)
            for candidate in candidates
            if (priority := self.priority_of(candidate)) > 0.0
        ]
        eligible.sort(key=lambda pair: (-pair[0], pair[1].person_id))
        chosen = eligible[:capacity]
        return AllocationPlan(
            visits=tuple(
                Visit(
                    person_id=candidate.person_id,
                    priority=round(priority, 3),
                    rationale=self.rationale_for(candidate),
                )
                for priority, candidate in chosen
            ),
            unvisited=len(eligible) - len(chosen),
            capacity=capacity,
        )

    @staticmethod
    def nearest_km(candidate: Candidate, resources: Sequence[Resource]) -> float | None:
        if not resources:
            return None
        return min(haversine_km(candidate.lat, candidate.lon, r.lat, r.lon) for r in resources)

    def coverage_gap(
        self,
        candidates: Sequence[Candidate],
        resources: Sequence[Resource],
        radius_km: float,
        min_tier: Tier,
    ) -> CoverageReport:
        """Who is at or above min_tier and beyond reach of any resource.

        Someone with cooling at home counts as covered — the resource they need is
        the one they already have.
        """
        considered = [c for c in candidates if c.assessment.tier >= min_tier]
        uncovered: list[UncoveredPerson] = []
        covered = 0

        for candidate in considered:
            if candidate.has_cooling:
                covered += 1
                continue
            distance = self.nearest_km(candidate, resources)
            if distance is not None and distance <= radius_km:
                covered += 1
            else:
                uncovered.append(
                    UncoveredPerson(
                        person_id=candidate.person_id,
                        nearest_km=distance,
                        lat=candidate.lat,
                        lon=candidate.lon,
                    )
                )

        return CoverageReport(
            uncovered=tuple(uncovered),
            covered_count=covered,
            considered=len(considered),
            radius_km=radius_km,
        )

    @staticmethod
    def siting_delta(
        report: CoverageReport, sites: Sequence[Resource], radius_km: float
    ) -> tuple[SitingOption, ...]:
        """Marginal coverage gained per candidate site, best first.

        Greedy and single-site: it answers "which one site helps most", not "which
        set of three". Set cover is the right model for the latter and is a v0.2
        concern.
        """
        options = [
            SitingOption(
                resource_id=site.id,
                newly_covered=sum(
                    1
                    for person in report.uncovered
                    if haversine_km(person.lat, person.lon, site.lat, site.lon) <= radius_km
                ),
            )
            for site in sites
        ]
        options.sort(key=lambda option: (-option.newly_covered, option.resource_id))
        return tuple(options)
