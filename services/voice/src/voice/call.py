"""The check-in as a phone call.

The same questionnaire the messaging channel sends, spoken aloud. It exists
because the people most at risk in a heat episode are the least likely to have a
smartphone — an 88-year-old with a landline is not an edge case here, she is the
median user.

Two things carry over from `checkin` unchanged, and both are the point:

- **Questions are selected, never generated.** `QuestionBank.build_for` picks
  from a validated bank against the live assessment, so an unsupervised call to
  a frail person is auditable line by line.
- **The simple register.** A dementia reason code shortens the call and switches
  every question to its one-clause phrasing. On a call that matters more than in
  text, because there is no re-reading.

Answers arrive as speech or a keypad press. Both are accepted: `<Gather>` with
`input="speech dtmf"` means someone who cannot hear the prompt can still press 1,
and someone who cannot use a keypad can still say yes.
"""

from datetime import date, timedelta
from xml.sax.saxutils import escape

from checkin.questions import Question, QuestionBank, Questionnaire
from contracts import DateRange

VOICE = "Polly.Amy-Neural"
"""A British voice. An American one reading UK health advice to an elderly
person in Bedford is a small thing that costs credibility immediately."""

ANSWER_BY_DIGIT = {"1": True, "2": False, "3": None}
YES_WORDS = frozenset({"yes", "yeah", "yep", "i have", "i did", "correct"})
NO_WORDS = frozenset({"no", "nope", "not yet", "i haven't", "i have not"})

GATHER_TIMEOUT = 6
"""Seconds to wait for an answer. Longer than a consumer IVR on purpose — the
target user is often slower to respond, and cutting them off mid-sentence is how
a check-in becomes a missed check-in."""


def questionnaire_for(bank: QuestionBank, person_id: str, assessment, today: date) -> Questionnaire:
    window = DateRange(start=today, end=today + timedelta(days=1))
    return bank.build_for(person_id, window, assessment)


def answer_from(speech: str | None, digits: str | None) -> bool | None:
    """Keypad first: it is unambiguous, and speech recognition on an elderly
    voice over a landline is the least reliable link in this chain."""
    if digits and digits in ANSWER_BY_DIGIT:
        return ANSWER_BY_DIGIT[digits]
    if not speech:
        return None
    said = speech.strip().lower().rstrip(".")
    if said in YES_WORDS or said.startswith("yes"):
        return True
    if said in NO_WORDS or said.startswith("no"):
        return False
    return None


class TwiMLBuilder:
    """Builds the call's XML. No network, no state — so it is testable in full."""

    def __init__(self, base_url: str, voice: str = VOICE) -> None:
        self.base_url = base_url.rstrip("/")
        self.voice = voice

    def say(self, text: str) -> str:
        return f'<Say voice="{self.voice}">{escape(text)}</Say>'

    def question(self, question: Question, index: int) -> str:
        """One question, with its answer prompt.

        `question.text` is already in the right register — `QuestionBank.build_for`
        resolves the simple phrasing when the assessment carries a dementia code,
        so there is nothing to choose between here.

        The prompt is spoken every time rather than once at the start. Someone who
        has been asked four questions has forgotten the instructions from the
        first, and repeating them costs six seconds.
        """
        text = question.text
        action = f"{self.base_url}/voice/answer?q={index}"
        # The keypad still answers — `dtmf` stays in the input list — it is simply
        # not announced. Reading "say yes, or press 1" before every question turns
        # a two-minute conversation into an automated menu, and the people this
        # calls are the ones most likely to hang up on one.
        # speechTimeout="auto" ends the turn as soon as the caller stops talking.
        # Without it Twilio falls back to `timeout`, so a one-word "yes" was
        # followed by six seconds of silence before the next question — which
        # reads as the line having gone dead, and is exactly when an elderly
        # caller hangs up.
        return (
            f'<Gather input="speech dtmf" numDigits="1" timeout="{GATHER_TIMEOUT}" '
            f'speechTimeout="auto" actionOnEmptyResult="true" '
            f'action="{escape(action)}" method="POST" language="en-GB">'
            f"{self.say(text)}"
            f"</Gather>"
            # Reached only when nothing was gathered. A silent answer is recorded
            # as "unsure" rather than dropped, because no answer from someone at
            # risk is itself information.
            f'<Redirect method="POST">{escape(action)}&amp;timeout=1</Redirect>'
        )

    def opening(self, name: str, count: int) -> str:
        """Said once. The only place the answering method is mentioned at all, and
        it is phrased as reassurance rather than instruction."""
        return self.say(
            f"Hello {name}. This is Climatise, calling because it is going to be hot "
            f"where you are. I have {count} quick question{'s' if count != 1 else ''}. "
            f"Just answer in your own words."
        )

    def closing(self, red_flag: bool) -> str:
        if red_flag:
            # SC-3: 999 is only ever named alongside an explicit red flag.
            return self.say(
                "Thank you. From what you have told me, please contact someone today. "
                "If you feel very unwell, confused, or stop passing water, call 999."
            )
        return self.say(
            "Thank you. That is all I needed. Someone will check the answers, and "
            "there is advice waiting for you in the Climatise app."
        )

    def document(self, *parts: str) -> str:
        return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"

    def hangup(self) -> str:
        return "<Hangup/>"
