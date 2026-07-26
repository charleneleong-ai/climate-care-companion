import dataclasses
from datetime import date

import pytest
from contracts import (
    AgeBand,
    AlertLevel,
    Assessment,
    ExposureFeatures,
    ExposureSource,
    Person,
    Reason,
    Tier,
    VulnerabilityProfile,
)

MODELS = [ExposureFeatures, Assessment, Person, Reason, VulnerabilityProfile]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_models_are_frozen_and_slotted(model):
    assert model.__dataclass_params__.frozen, f"{model.__name__} must be immutable"
    assert getattr(model, "__slots__", None) is not None


def test_assessment_reasons_is_a_tuple_and_cannot_be_mutated():
    a = Assessment(
        tier=Tier.LOW, risk_score=0.0, exposure_score=0, vulnerability_score=7, reasons=()
    )
    assert isinstance(a.reasons, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.tier = Tier.SEVERE


def test_exposure_features_carries_provenance_and_alert():
    e = ExposureFeatures(
        date=date(2025, 7, 19),
        overnight_min=17.0,
        peak_apparent=29.0,
        peak_air=29.0,
        hours_above_26=6,
        indoor_night_est=24.6,
        indoor_day_est=25.85,
        spell_day=3,
        alert_level=AlertLevel.NONE,
        source=ExposureSource.FIXTURE,
    )
    assert e.source is ExposureSource.FIXTURE
    assert e.alert_level is AlertLevel.NONE


def test_person_collections_default_to_empty_not_none():
    p = Person(
        id="p1", name="Doris", age_band=AgeBand.B85_PLUS, lives_alone=True, mobility_limited=False
    )
    assert p.medications == ()
    assert p.conditions == ()
