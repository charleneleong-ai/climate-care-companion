from dataclasses import dataclass

from contracts import OrgType


@dataclass(frozen=True, slots=True)
class Org:
    id: str
    name: str
    type: OrgType
    area_codes: tuple[str, ...]
    """Every L6 query is scoped by these from the first commit. Retrofitting tenancy
    onto an existing assessment table is the expensive mistake."""


@dataclass(frozen=True, slots=True)
class Cohort:
    id: str
    org_id: str
    name: str


@dataclass(frozen=True, slots=True)
class CohortMember:
    cohort_id: str
    person_id: str
    consent_basis: str
    """No default. SC-6 is enforced by construction rather than remembered — you
    cannot add a person to a cohort without stating the lawful basis."""
