from enum import IntEnum, StrEnum, auto


class Tier(IntEnum):
    """Spec 8.5. Ordered so comparisons express severity directly."""

    LOW = 0
    ELEVATED = 1
    HIGH = 2
    SEVERE = 3


class ReasonCode(StrEnum):
    # Exposure — spec 8.1
    NIGHT_NO_RECOVERY = auto()
    BEDROOM_UNSAFE = auto()
    BEDROOM_WARM = auto()
    PEAK_HEAT = auto()
    SUSTAINED_SPELL = auto()
    INDOOR_BELOW_18 = auto()
    INDOOR_BELOW_16 = auto()
    INDOOR_BELOW_12 = auto()
    # Vulnerability — spec 8.2
    AGE_85_PLUS = auto()
    AGE_75_84 = auto()
    LIVES_ALONE = auto()
    DEMENTIA = auto()
    CARDIOVASCULAR = auto()
    RENAL = auto()
    RESPIRATORY = auto()
    MOBILITY_LIMITED = auto()
    MED_LITHIUM = auto()
    MED_DIURETIC = auto()
    MED_ANTICHOLINERGIC = auto()
    MED_ANTIPSYCHOTIC = auto()
    MED_ACE_ARB = auto()
    MED_BETA_BLOCKER = auto()
    MED_SSRI = auto()


class AlertLevel(StrEnum):
    NONE = auto()
    YELLOW = auto()
    AMBER = auto()
    RED = auto()
    NOT_CHECKED = auto()
    """FR-12: degrade gracefully when the UKHSA feed is unavailable. Distinct from
    NONE, which asserts that no alert is in force."""


class ExposureSource(StrEnum):
    """Provenance only. Never changes behaviour — see AC-5.

    A fixture, a cache hit and a live call are indistinguishable to the scoring
    core, which is what lets a data source be swapped without downstream edits.
    """

    LIVE = auto()
    ARCHIVE = auto()
    CACHE = auto()
    FIXTURE = auto()
    SELF_REPORT = auto()


class AgeBand(StrEnum):
    UNDER_65 = auto()
    B65_74 = auto()
    B75_84 = auto()
    B85_PLUS = auto()


class Condition(StrEnum):
    DEMENTIA = auto()
    CARDIOVASCULAR = auto()
    RENAL = auto()
    RESPIRATORY = auto()


class MedClass(StrEnum):
    """Spec 8.3. Scoring is on class, never on drug name (FR-14)."""

    DIURETIC = auto()
    ANTICHOLINERGIC = auto()
    BETA_BLOCKER = auto()
    ACE_ARB = auto()
    ANTIPSYCHOTIC = auto()
    SSRI = auto()
    LITHIUM = auto()
    HEAT_SENSITIVE = auto()
    OTHER = auto()


class RedFlag(StrEnum):
    """SC-3 clinical red flags. This set only — nothing else routes to 999."""

    UNROUSABLE = auto()
    CONFUSION = auto()
    NO_URINE_OUTPUT = auto()
    HOT_DRY_SKIN = auto()


class OrgType(StrEnum):
    COUNCIL = auto()
    HOSPITAL = auto()
    CARE_HOME = auto()
    ICB = auto()
    """Declared, unimplemented. Scoping every L6 query by org from the first commit
    is the cheap half; retrofitting it later is the expensive half."""


class DwellingType(StrEnum):
    HOUSE = auto()
    FLAT = auto()
    BUNGALOW = auto()
    CARE_HOME = auto()


class Aspect(StrEnum):
    NORTH = auto()
    EAST = auto()
    SOUTH = auto()
    WEST = auto()
