from dataclasses import dataclass

from contracts import Assessment


@dataclass(frozen=True, slots=True)
class Candidate:
    """A person considered for allocation, flattened to what the algorithms need."""

    person_id: str
    assessment: Assessment
    lives_alone: bool
    mobility_limited: bool
    lat: float
    lon: float
    has_cooling: bool


@dataclass(frozen=True, slots=True)
class Visit:
    person_id: str
    priority: float
    rationale: str
    """Why this person is at this position. A visit that cannot be defended to a
    councillor is a visit that will not survive a budget review."""


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    visits: tuple[Visit, ...]
    unvisited: int
    capacity: int


@dataclass(frozen=True, slots=True)
class UncoveredPerson:
    person_id: str
    nearest_km: float | None
    """None when no resource exists at all, which is a different problem from one
    that exists but is too far."""
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class CoverageReport:
    uncovered: tuple[UncoveredPerson, ...]
    covered_count: int
    considered: int
    radius_km: float


@dataclass(frozen=True, slots=True)
class SitingOption:
    resource_id: str
    newly_covered: int
