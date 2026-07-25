from contracts import Assessment, Tier
from core.corpus import Corpus


class CheckinScript:
    """Chooses which corpus rows the caller hears.

    The governing constraint of spec section 6: this **selects** utterances, it
    never **composes** them. Every line is a row that already passed the SC-1 safety
    grep, so the agent cannot say something novel about a medicine because it cannot
    compose a novel sentence at all.

    This costs conversational range and buys a system auditable line by line. For a
    tool speaking unsupervised to an 88-year-old about their health, that is the
    correct trade.

    KNOWN GAP — Track A's first job. The action corpus is written in the third
    person, for the caregiver: "they may not feel like drinking", "offer fluids
    regularly". Read verbatim to the cared-for person those lines are wrong, and in
    the dementia case actively confusing. The corpus needs a second person-facing
    column, and this class needs to select it. Until then treat the utterances as
    caregiver-facing and the voice path as a scaffold, not a script.
    """

    TIER_BY_NAME: dict[str, Tier] = {
        "low": Tier.LOW,
        "elevated": Tier.ELEVATED,
        "high": Tier.HIGH,
        "severe": Tier.SEVERE,
    }

    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus

    @property
    def all_utterances(self) -> frozenset[str]:
        """The closed set. The agent can say these strings and nothing else."""
        return frozenset(row.text for row in self.corpus.actions)

    def utterances_for(self, assessment: Assessment) -> tuple[str, ...]:
        """Rows matching this assessment's reason codes, in corpus order.

        Low tier places no call at all — ringing someone to tell them nothing is
        wrong is how a system trains people to ignore it.
        """
        if assessment.tier is Tier.LOW:
            return ()
        codes = {reason.code for reason in assessment.reasons}
        rows = sorted(
            (
                row
                for row in self.corpus.actions
                if row.reason_code in codes
                and assessment.tier >= self.TIER_BY_NAME[row.tier_min]
            ),
            key=lambda row: row.ordering,
        )
        seen: set[str] = set()
        chosen: list[str] = []
        for row in rows:
            if row.text not in seen:
                seen.add(row.text)
                chosen.append(row.text)
        return tuple(chosen)
