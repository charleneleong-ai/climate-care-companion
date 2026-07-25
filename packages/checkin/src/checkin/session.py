from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum, auto

from checkin.messages import ButtonMessage, TemplateMessage, decode_button_id, question_buttons
from checkin.questions import Questionnaire
from contracts import SelfReport


class SessionState(StrEnum):
    PENDING_OPENER = auto()
    """Nothing sent yet."""
    AWAITING_OPENER_REPLY = auto()
    """Template sent. Until they reply, the 24-hour window is shut and nothing
    further can be sent — this is the state a no-answer escalation fires from."""
    IN_PROGRESS = auto()
    COMPLETE = auto()
    ABANDONED = auto()
    """They engaged and then stopped, or never replied within the timeout."""


@dataclass(slots=True)
class CheckinSession:
    """One person's check-in conversation, advanced by inbound replies.

    Stateful by necessity: a messaging check-in is asynchronous. The questionnaire
    is fixed at construction, but which question is outstanding depends on replies
    that arrive minutes or hours later, possibly out of order.

    Every method takes `now` as an argument rather than reading the clock, so the
    whole state machine is testable and replayable.
    """

    questionnaire: Questionnaire
    opener: TemplateMessage
    no_reply_timeout: timedelta = timedelta(minutes=30)
    """Shorter than WhatsApp's 24-hour window on purpose. A check-in is about
    tonight, so silence stops being 'not yet' and becomes a signal quickly."""

    state: SessionState = SessionState.PENDING_OPENER
    cursor: int = 0
    answers: dict[str, bool | None] = field(default_factory=dict)
    opener_sent_at: datetime | None = None
    last_inbound_at: datetime | None = None

    WINDOW = timedelta(hours=24)
    """Meta's customer service window. Free-form messages are only permitted inside
    it, and it reopens on every inbound message."""

    @property
    def person_id(self) -> str:
        return self.questionnaire.person_id

    def window_open(self, now: datetime) -> bool:
        if self.last_inbound_at is None:
            return False
        return now - self.last_inbound_at < self.WINDOW

    def is_overdue(self, now: datetime) -> bool:
        """No reply for longer than the timeout. The no-answer escalation trigger."""
        reference = self.last_inbound_at or self.opener_sent_at
        if reference is None or self.state in (SessionState.COMPLETE, SessionState.ABANDONED):
            return False
        return now - reference >= self.no_reply_timeout

    @property
    def outstanding_question(self):
        if self.cursor >= len(self.questionnaire.questions):
            return None
        return self.questionnaire.questions[self.cursor]

    def next_message(self, now: datetime) -> TemplateMessage | ButtonMessage | None:
        """What to send right now, or None if nothing may be sent.

        Returns None rather than raising when the window is shut: a closed window is
        an ordinary state, not an error, and the caller escalates instead of retrying.
        """
        if self.state is SessionState.PENDING_OPENER:
            return self.opener
        if self.state is not SessionState.IN_PROGRESS:
            return None
        if not self.window_open(now):
            return None
        question = self.outstanding_question
        if question is None:
            return None
        return ButtonMessage(body=question.text, buttons=question_buttons(question.code))

    def record_sent(self, now: datetime) -> None:
        if self.state is SessionState.PENDING_OPENER:
            self.state = SessionState.AWAITING_OPENER_REPLY
            self.opener_sent_at = now

    def record_reply(self, button_id: str, now: datetime) -> None:
        """Fold an inbound button reply into the session.

        The button id carries its own question code, so a late reply to an earlier
        question is recorded against that question rather than the outstanding one.
        """
        code, answer = decode_button_id(button_id)
        self.last_inbound_at = now
        self.answers[code] = answer

        if self.state is SessionState.AWAITING_OPENER_REPLY:
            self.state = SessionState.IN_PROGRESS

        self.advance()

    def record_opener_acknowledged(self, now: datetime) -> None:
        """Any inbound message opens the window, not only a button press."""
        self.last_inbound_at = now
        if self.state is SessionState.AWAITING_OPENER_REPLY:
            self.state = SessionState.IN_PROGRESS

    def advance(self) -> None:
        while (
            self.cursor < len(self.questionnaire.questions)
            and self.questionnaire.questions[self.cursor].code in self.answers
        ):
            self.cursor += 1
        if self.cursor >= len(self.questionnaire.questions):
            self.state = SessionState.COMPLETE

    def abandon(self) -> None:
        self.state = SessionState.ABANDONED

    def to_self_report(self) -> SelfReport:
        """Whatever was gathered, including nothing.

        A partial check-in is still usable: a red flag answered before the person
        stopped replying matters just as much as one in a completed run.
        """
        return self.questionnaire.to_self_report(self.answers)
