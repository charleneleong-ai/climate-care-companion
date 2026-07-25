"""Types crossing layer boundaries.

Zero third-party dependencies, permanently. Every track imports this module and
nothing else defines a type that crosses a layer boundary, which is what lets the
three tracks work in parallel without coordinating.
"""

from contracts.enums import (
    AdviceSource,
    AgeBand,
    Audience,
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
    AdviceItem,
    Assessment,
    DateRange,
    ExposureFeatures,
    Med,
    Person,
    Place,
    PreventionPlan,
    Reason,
    SelfReport,
    VulnerabilityProfile,
)

__all__ = [
    "AdviceItem",
    "AdviceSource",
    "AgeBand",
    "Audience",
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
    "PreventionPlan",
    "Reason",
    "ReasonCode",
    "RedFlag",
    "SelfReport",
    "Tier",
    "VulnerabilityProfile",
]
