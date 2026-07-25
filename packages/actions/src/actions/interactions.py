"""Interaction rules — advice that exists only in combination.

The scoring core treats vulnerabilities as independent and additive, which is
right for producing a tier: a diuretic contributes 2, dementia contributes 2, and
they multiply exposure. But advice is not additive. "You take a diuretic" and "it
is hot" produce one instruction each; *heat plus a diuretic plus reduced kidney
function* produces a different instruction that neither implies on its own.

This is also where a dormant condition becomes live. Reduced kidney function is
asymptomatic in ordinary weather and only narrows the margin once fluid is being
lost — so it earns no advice in March and specific advice in July.

SC-1 applies unchanged: nothing here suggests altering a prescription, and every
medication interaction routes to a pharmacist or GP. The table is enforced at load.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from contracts import (
    Audience,
    ReasonCode,
    Condition,
    ExposureFeatures,
    MedClass,
    Person,
    SelfReport,
    Tier,
)
from core.corpus import FORBIDDEN_MEDICATION_ADVICE, PROFESSIONALS

INTERACTIONS_PATH = (
    Path(__file__).resolve().parents[4] / "data" / "seed" / "interactions.csv"
)

TIER_BY_NAME: dict[str, Tier] = {
    "low": Tier.LOW,
    "elevated": Tier.ELEVATED,
    "high": Tier.HIGH,
    "severe": Tier.SEVERE,
}

SELF_REPORT_ANSWERS: dict[str, bool] = {"yes": True, "no": False}


@dataclass(frozen=True, slots=True)
class InteractionRule:
    code: str
    min_peak_air: float | None
    max_indoor_day: float | None
    requires_conditions: frozenset[Condition]
    requires_med_classes: frozenset[MedClass]
    requires_flags: frozenset[str]
    """Boolean attributes on Person — mobility_limited, lives_alone. Without
    these a rule with no condition and no medication requirement fires for
    everyone, which is how the mobility rule came to apply to all comers."""
    requires_self_report: tuple[str, bool] | None
    supersedes: frozenset[ReasonCode]
    """Reason codes this rule replaces. The combination advice is more specific
    than the single-factor advice it is built from, so emitting both would bury
    the better instruction under the generic one."""
    min_tier: Tier
    advice_caregiver: str
    advice_person: str | None
    """None where the instruction is not one the person can act on themselves.
    A blank is a deliberate decision, not missing data."""
    watch_for: str | None
    escalate_to: str | None
    ordering: int

    @property
    def is_medication_advice(self) -> bool:
        return bool(self.requires_med_classes)

    def text_for(self, audience: Audience) -> str | None:
        if audience is Audience.CAREGIVER:
            return self.advice_caregiver
        return self.advice_person

    def applies(
        self,
        exposure: ExposureFeatures,
        person: Person,
        tier: Tier,
        report: SelfReport | None,
    ) -> bool:
        """Every declared requirement must hold. Absent requirements do not constrain."""
        if tier < self.min_tier:
            return False
        if self.min_peak_air is not None and exposure.peak_air < self.min_peak_air:
            return False
        if self.max_indoor_day is not None and exposure.indoor_day_est > self.max_indoor_day:
            return False
        if not self.requires_conditions <= set(person.conditions):
            return False
        held = {med.drug_class for med in person.medications}
        if not self.requires_med_classes <= held:
            return False
        if not all(getattr(person, flag, False) for flag in self.requires_flags):
            return False
        return self.self_report_matches(report)

    def self_report_matches(self, report: SelfReport | None) -> bool:
        if self.requires_self_report is None:
            return True
        if report is None or not report.answered:
            return False
        field, expected = self.requires_self_report
        return getattr(report, field, None) is expected


class InteractionTable:
    """Loads and validates the interaction rules."""

    def __init__(self, rules: tuple[InteractionRule, ...]) -> None:
        self.rules = rules

    @classmethod
    def load(cls, path: Path | None = None) -> "InteractionTable":
        table = cls(cls.read_rules(path or INTERACTIONS_PATH))
        table.check_medication_safety()
        return table

    @staticmethod
    def read_rules(path: Path) -> tuple[InteractionRule, ...]:
        with path.open(newline="") as fh:
            return tuple(
                InteractionRule(
                    code=row["code"],
                    min_peak_air=float(row["min_peak_air"]) if row["min_peak_air"] else None,
                    max_indoor_day=(
                        float(row["max_indoor_day"]) if row["max_indoor_day"] else None
                    ),
                    requires_conditions=frozenset(
                        Condition(c) for c in InteractionTable.split(row["requires_conditions"])
                    ),
                    requires_med_classes=frozenset(
                        MedClass(m)
                        for m in InteractionTable.split(row["requires_med_classes"])
                    ),
                    requires_flags=frozenset(
                        InteractionTable.split(row["requires_flags"])
                    ),
                    requires_self_report=InteractionTable.parse_self_report(
                        row["requires_self_report"]
                    ),
                    supersedes=frozenset(
                        ReasonCode(c)
                        for c in InteractionTable.split(row["supersedes"])
                    ),
                    min_tier=TIER_BY_NAME[row["min_tier"]],
                    advice_caregiver=row["advice_caregiver"],
                    advice_person=row["advice_person"] or None,
                    watch_for=row["watch_for"] or None,
                    escalate_to=row["escalate_to"] or None,
                    ordering=int(row["ordering"]),
                )
                for row in csv.DictReader(fh)
            )

    @staticmethod
    def split(value: str) -> list[str]:
        return [part.strip() for part in value.split(";") if part.strip()]

    @staticmethod
    def parse_self_report(value: str) -> tuple[str, bool] | None:
        if not value:
            return None
        field, _, answer = value.partition(":")
        if answer not in SELF_REPORT_ANSWERS:
            raise ValueError(f"self-report condition {value!r} must end in :yes or :no")
        return field, SELF_REPORT_ANSWERS[answer]

    def check_medication_safety(self) -> None:
        """SC-1 at load. An interaction is not a route around the constraint."""
        for rule in self.rules:
            for text in (rule.advice_caregiver, rule.advice_person or "", rule.watch_for or ""):
                if FORBIDDEN_MEDICATION_ADVICE.search(text):
                    raise ValueError(
                        f"SC-1 violation in interaction {rule.code}: advice must never "
                        f"suggest changing a prescription — {text!r}"
                    )
            if rule.is_medication_advice and rule.escalate_to not in PROFESSIONALS:
                raise ValueError(
                    f"SC-1 violation in interaction {rule.code}: a medication "
                    f"interaction must route to a pharmacist or GP, "
                    f"got {rule.escalate_to!r}"
                )

    def matching(
        self,
        exposure: ExposureFeatures,
        person: Person,
        tier: Tier,
        report: SelfReport | None = None,
    ) -> tuple[InteractionRule, ...]:
        return tuple(
            sorted(
                (r for r in self.rules if r.applies(exposure, person, tier, report)),
                key=lambda r: r.ordering,
            )
        )
