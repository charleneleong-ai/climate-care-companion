from contracts import (
    Assessment,
    ExposureFeatures,
    Reason,
    ReasonCode,
    Tier,
    VulnerabilityProfile,
)
from core.corpus import Corpus
from core.rules import EXPOSURE_RULES, VULNERABILITY_RULES, ExposureRule, VulnerabilityRule


class RiskScorer:
    """L3 risk fusion.

    AC-1: no I/O, no database, no clock. The Corpus is injected at construction and
    supplies text only — it never influences the score, so assess() stays
    deterministic over its arguments and replays identically against archived
    weather (AC-5).
    """

    THRESHOLDS: tuple[tuple[float, Tier], ...] = (
        (9.0, Tier.SEVERE),
        (5.0, Tier.HIGH),
        (2.0, Tier.ELEVATED),
    )

    def __init__(
        self,
        corpus: Corpus,
        exposure_rules: tuple[ExposureRule, ...] = EXPOSURE_RULES,
        vulnerability_rules: tuple[VulnerabilityRule, ...] = VULNERABILITY_RULES,
    ) -> None:
        self.corpus = corpus
        self.exposure_rules = exposure_rules
        self.weights: dict[ReasonCode, int] = {
            rule.code: rule.weight for rule in (*exposure_rules, *vulnerability_rules)
        }

    @staticmethod
    def tier_for(risk: float) -> Tier:
        for floor, tier in RiskScorer.THRESHOLDS:
            if risk >= floor:
                return tier
        return Tier.LOW

    def build_reasons(self, codes: list[ReasonCode]) -> tuple[Reason, ...]:
        return tuple(
            Reason(
                code=code,
                title=self.corpus.reasons[code].title,
                explanation=self.corpus.reasons[code].explanation,
                weight=self.weights[code],
            )
            for code in codes
        )

    def assess(
        self, exposure: ExposureFeatures, vulnerability: VulnerabilityProfile
    ) -> Assessment:
        triggered = [rule for rule in self.exposure_rules if rule.predicate(exposure)]
        exposure_score = sum(rule.weight for rule in triggered)

        # FR-18: zero exposure is Low regardless of frailty. Vulnerability modifies
        # the effect of exposure; it is not itself a harm. Additive scoring would
        # place a frail person permanently at an elevated tier and destroy the signal.
        risk = (
            0.0
            if exposure_score == 0
            else exposure_score * (1 + vulnerability.score / 10)
        )

        codes = [rule.code for rule in triggered] + list(vulnerability.codes)
        return Assessment(
            tier=self.tier_for(risk),
            risk_score=risk,
            exposure_score=exposure_score,
            vulnerability_score=vulnerability.score,
            reasons=self.build_reasons(codes),
        )
