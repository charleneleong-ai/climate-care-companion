"""When advice is not enough and somebody has to go round.

The rest of the system answers "what should be done?". This answers a different
question — "is telling anyone still sufficient?" — and the two come apart in
exactly the cases that matter most.

Three ideas the rules encode:

**A reassuring answer is not reassurance if the person cannot reliably give one.**
Someone with dementia saying they feel fine is not evidence that they are. The
check-in still runs, because the attempt itself is informative, but a good answer
from someone who cannot self-report must never *lower* the response. Treating all
self-reports as equally trustworthy is how a system talks itself out of the visit
it should have made.

**Silence is the loudest signal.** A missed call during a risk window is the
condition this whole product exists to catch. It is not a failed delivery to be
retried quietly; it is the strongest single reason to send someone.

**Somebody nearby beats somebody official.** A caregiver who can be at the door
in ten minutes is a better response than a council referral that lands tomorrow.
Council welfare is what the people with nobody get, and they are precisely the
ones the register exists to surface.

SC-3 governs the top of the ladder: 999 is named only alongside an explicit red
flag, never inferred from a tier.
"""

from dataclasses import dataclass
from enum import IntEnum

from contracts import Person, RedFlag, SelfReport, Tier


class Urgency(IntEnum):
    """Ordered so the strongest reason wins when several apply."""

    NONE = 0
    MENTION = 1
    """Worth a call or a text. No visit implied."""
    VISIT_TODAY = 2
    """Somebody should lay eyes on them before the evening."""
    VISIT_NOW = 3
    """Nobody knows how they are, and the conditions are dangerous."""
    EMERGENCY = 4
    """An explicit red flag. 999."""


class Responder(IntEnum):
    NOBODY = 0
    CAREGIVER = 1
    COUNCIL = 2
    """No caregiver on record. The council view exists to find these people."""
    AMBULANCE = 3


@dataclass(frozen=True, slots=True)
class Escalation:
    urgency: Urgency
    responder: Responder
    reason: str
    """One sentence, addressed to whoever reads the alert. Plain language, because
    it is quoted verbatim into a message and nobody should have to decode it."""
    detail: str = ""
    """The bare symptom phrase, for templates whose own wording supplies the
    sentence around it. Kept separate from `reason` because dropping a full
    sentence into "has reported ___" produces both broken grammar and a second
    "call 999" — which is how an urgent message starts looking automated."""

    @property
    def needs_visit(self) -> bool:
        return self.urgency >= Urgency.VISIT_TODAY


NO_ESCALATION = Escalation(Urgency.NONE, Responder.NOBODY, "")

CANNOT_SELF_REPORT = "dementia"
"""The condition after which an answer stops being evidence about the answerer.

Named as a constant rather than inlined because the list will grow — delirium and
advanced frailty belong here too — and every addition is a clinical judgement
that should be reviewed in one place.
"""


class EscalationPolicy:
    """Decides whether somebody has to attend in person.

    Deliberately separate from the prevention plan. A plan says what to do; this
    says whether anyone is in a position to do it. For a person living alone with
    dementia those are different answers, and collapsing them is how the advice
    ends up addressed to somebody who cannot act on it.
    """

    def decide(
        self,
        person: Person,
        tier: Tier,
        report: SelfReport | None,
        has_caregiver: bool,
        consecutive_missed: int = 0,
    ) -> Escalation:
        """`report` is None when no check-in was attempted, which is not the same
        as one that went unanswered — `SelfReport.answered` carries that.

        `consecutive_missed` counts unanswered check-ins including this one, read
        from the check-in log. A second silence in a row is a different fact from
        a first: one missed call is a person who was in the garden, two is a
        pattern, and the response should not be identical.
        """
        responder = Responder.CAREGIVER if has_caregiver else Responder.COUNCIL

        # SC-3. A red flag outranks everything, including a calm tier — the flags
        # describe a body in trouble now, not a forecast.
        flags = tuple(report.red_flags) if report else ()
        if flags:
            described = self.describe(flags)
            return Escalation(
                Urgency.EMERGENCY,
                Responder.AMBULANCE,
                f"They reported {described}. This needs 999 now.",
                detail=described,
            )

        if tier is Tier.LOW:
            return NO_ESCALATION

        # Silence during a risk window. Nobody knows how they are, and the reasons
        # someone does not answer overlap heavily with the reasons to worry.
        if report is not None and not report.answered:
            repeated = consecutive_missed >= 2
            urgent = repeated or tier >= Tier.HIGH
            times = f" This is {consecutive_missed} missed check-ins in a row." if repeated else ""
            return Escalation(
                Urgency.VISIT_NOW if urgent else Urgency.VISIT_TODAY,
                responder,
                f"Nobody answered the check-in and conditions are {tier.name.title()}."
                f"{times} Please go round rather than trying again.",
            )

        # Answered, but by someone whose answer cannot carry the weight. The visit
        # stands on the tier alone; what they said does not lower it.
        if self.cannot_self_report(person) and tier >= Tier.HIGH:
            return Escalation(
                Urgency.VISIT_TODAY,
                responder,
                "They answered, but memory problems mean they may not notice or "
                "report feeling unwell. Someone should check on them in person.",
            )

        if tier is Tier.SEVERE:
            return Escalation(
                Urgency.VISIT_TODAY,
                responder,
                "Conditions are Severe tonight. Someone should see them today.",
            )

        return Escalation(
            Urgency.MENTION,
            responder,
            f"Conditions are {tier.name.title()}. Worth a call this afternoon.",
        )

    @staticmethod
    def cannot_self_report(person: Person) -> bool:
        return any(c.value == CANNOT_SELF_REPORT for c in person.conditions)

    @staticmethod
    def describe(flags: tuple[RedFlag, ...]) -> str:
        words = {
            RedFlag.UNROUSABLE: "they could not be roused",
            RedFlag.CONFUSION: "new confusion",
            RedFlag.NO_URINE_OUTPUT: "not passing water",
            RedFlag.HOT_DRY_SKIN: "hot, dry skin",
        }
        return ", ".join(words.get(flag, flag.value) for flag in flags)
