"""Types crossing layer boundaries.

Zero third-party dependencies, permanently. Every track imports this module and
nothing else defines a type that crosses a layer boundary, which is what lets the
three tracks work in parallel without coordinating.
"""

from contracts.enums import (
    AgeBand,
    AlertLevel,
    Aspect,
    Condition,
    DwellingType,
    ExposureSource,
    MedClass,
    OrgType,
    ReasonCode,
    RedFlag,
    Tier,
)
from contracts.models import (
    Assessment,
    DateRange,
    ExposureFeatures,
    Med,
    Person,
    Place,
    Reason,
    SelfReport,
    VulnerabilityProfile,
)

__all__ = [
    "AgeBand",
    "AlertLevel",
    "Aspect",
    "Assessment",
    "Condition",
    "DateRange",
    "DwellingType",
    "ExposureFeatures",
    "ExposureSource",
    "Med",
    "MedClass",
    "OrgType",
    "Person",
    "Place",
    "Reason",
    "ReasonCode",
    "RedFlag",
    "SelfReport",
    "Tier",
    "VulnerabilityProfile",
]
