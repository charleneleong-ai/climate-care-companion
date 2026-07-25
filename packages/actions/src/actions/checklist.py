"""Prevention plans — what to do before the heat arrives.

Built from a warning with lead time attached, not from conditions already present.
The chain the whole system exists to run:

    heat warning (lead time)  ->  prevention plan  ->  check-in  ->  allocation

Three sources of advice, in descending specificity:

1. **Interactions.** Heat plus a condition plus a medicine. These come first because
   they are the ones a caregiver could not have worked out from a leaflet, and the
   ones where general advice is sometimes actively wrong.
2. **Reason codes.** The one-to-one corpus, for factors that stand alone.
3. **Self-report.** What the person actually said, which outranks any estimate about
   them.

Every plan is built for one audience. The same interaction produces different words
for the caregiver and for the person, and some produce words for only one of them.
"""

from actions.interactions import InteractionTable
from contracts import (
    AdviceItem,
    AdviceSource,
    Assessment,
    Audience,
    ExposureFeatures,
    Person,
    PreventionPlan,
    SelfReport,
    Tier,
)
from core.corpus import Corpus


class PreventionPlanBuilder:
    """Turns a warning plus a person into advice addressed to a named audience.

    FR-19: derived solely from reason codes and the interaction table. AC-2 holds —
    nothing here re-derives risk from raw exposure, since the tier arrives already
    decided by the scoring core.
    """

    TIER_BY_NAME: dict[str, Tier] = {
        "low": Tier.LOW,
        "elevated": Tier.ELEVATED,
        "high": Tier.HIGH,
        "severe": Tier.SEVERE,
    }

    def __init__(self, corpus: Corpus, interactions: InteractionTable) -> None:
        self.corpus = corpus
        self.interactions = interactions

    def build(
        self,
        person: Person,
        exposure: ExposureFeatures,
        assessment: Assessment,
        audience: Audience = Audience.CAREGIVER,
        report: SelfReport | None = None,
        lead_time_hours: int = 0,
        expected_peak: float | None = None,
    ) -> PreventionPlan:
        items = self.interaction_items(person, exposure, assessment, audience, report)
        covered = {item.code for item in items}
        items.extend(self.reason_items(assessment, audience, covered))

        return PreventionPlan(
            person_id=person.id,
            tier=assessment.tier,
            audience=audience,
            items=tuple(items),
            lead_time_hours=lead_time_hours,
            expected_peak=expected_peak,
            alert_level=exposure.alert_level,
        )

    def interaction_items(
        self,
        person: Person,
        exposure: ExposureFeatures,
        assessment: Assessment,
        audience: Audience,
        report: SelfReport | None,
    ) -> list[AdviceItem]:
        items: list[AdviceItem] = []
        for rule in self.interactions.matching(exposure, person, assessment.tier, report):
            text = rule.text_for(audience)
            if not text:
                # Deliberately not addressed to this audience. Telling someone with
                # dementia to monitor their own confusion is not a safeguard.
                continue
            items.append(
                AdviceItem(
                    code=rule.code,
                    text=text,
                    watch_for=rule.watch_for if audience is Audience.CAREGIVER else None,
                    escalate_to=rule.escalate_to,
                    source=(
                        AdviceSource.SELF_REPORT
                        if rule.requires_self_report
                        else AdviceSource.INTERACTION
                    ),
                    audience=audience,
                )
            )
        return items

    def reason_items(
        self, assessment: Assessment, audience: Audience, already_covered: set[str]
    ) -> list[AdviceItem]:
        """Single-factor advice, for anything the interactions did not already cover.

        Only the caregiver receives these. The corpus is written in the third
        person, so reading it to the cared-for person would address them as someone
        else — the fix is a person-facing column, which Track A owns.
        """
        if audience is not Audience.CAREGIVER:
            return []

        codes = {reason.code for reason in assessment.reasons}
        rows = sorted(
            (
                row
                for row in self.corpus.actions
                if row.reason_code in codes
                and assessment.tier >= self.TIER_BY_NAME[row.tier_min]
                and row.reason_code not in already_covered
            ),
            key=lambda row: row.ordering,
        )
        return [
            AdviceItem(
                code=row.reason_code,
                text=row.text,
                watch_for=None,
                escalate_to=row.escalate_to or None,
                source=AdviceSource.REASON_CODE,
                audience=audience,
            )
            for row in rows
        ]
