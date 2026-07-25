import pytest
from contracts import AgeBand, ExposureSource, MedClass, ReasonCode, Tier

EXPOSURE_CODES = {
    "NIGHT_NO_RECOVERY", "BEDROOM_UNSAFE", "BEDROOM_WARM", "PEAK_HEAT",
    "SUSTAINED_SPELL", "INDOOR_BELOW_18", "INDOOR_BELOW_16", "INDOOR_BELOW_12",
}
VULNERABILITY_CODES = {
    "AGE_85_PLUS", "AGE_75_84", "LIVES_ALONE", "DEMENTIA", "CARDIOVASCULAR",
    "RENAL", "RESPIRATORY", "MOBILITY_LIMITED", "MED_LITHIUM", "MED_DIURETIC",
    "MED_ANTICHOLINERGIC", "MED_ANTIPSYCHOTIC", "MED_ACE_ARB",
    "MED_BETA_BLOCKER", "MED_SSRI",
}


def test_reason_codes_match_spec_tables_exactly():
    assert {c.name for c in ReasonCode} == EXPOSURE_CODES | VULNERABILITY_CODES


def test_tiers_order_low_to_severe():
    assert [t.name for t in Tier] == ["LOW", "ELEVATED", "HIGH", "SEVERE"]
    assert Tier.LOW < Tier.SEVERE


@pytest.mark.parametrize("member", ["LIVE", "ARCHIVE", "CACHE", "FIXTURE", "SELF_REPORT"])
def test_exposure_source_records_provenance(member):
    assert member in ExposureSource.__members__


def test_med_classes_cover_spec_8_3():
    assert {c.name for c in MedClass} >= {
        "DIURETIC", "ANTICHOLINERGIC", "BETA_BLOCKER", "ACE_ARB",
        "ANTIPSYCHOTIC", "SSRI", "LITHIUM", "HEAT_SENSITIVE",
    }


def test_age_bands_are_ordered_and_disjoint():
    assert [b.name for b in AgeBand] == ["UNDER_65", "B65_74", "B75_84", "B85_PLUS"]
