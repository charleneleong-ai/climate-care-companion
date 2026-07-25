from typing import Protocol, runtime_checkable


@runtime_checkable
class VoiceChannel(Protocol):
    def say(self, utterance: str) -> None: ...

    def ask(self, question: str) -> bool | None: ...


class ConsoleVoice:
    """Prints the transcript and reads replies.

    Ships green so the entire check-in flow is testable and demoable with no
    telephony account, no phone number and no per-minute cost. A real provider
    implements the same Protocol.
    """

    YES = frozenset({"yes", "yeah", "yep", "y"})
    NO = frozenset({"no", "nope", "n"})

    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = list(replies or [])
        self.transcript: list[str] = []

    def say(self, utterance: str) -> None:
        self.transcript.append(utterance)
        print(f"  [voice] {utterance}")

    def ask(self, question: str) -> bool | None:
        """An unrecognised reply is no-answer, never free text to be interpreted.

        Speech recognition maps onto a closed response set. Anything outside it is
        treated as silence, which under SC-7's over-warn bias escalates rather than
        being guessed at.
        """
        self.transcript.append(question)
        reply = self.replies.pop(0) if self.replies else input(f"  [voice] {question} ")
        normalised = reply.strip().lower()
        if normalised in self.YES:
            return True
        if normalised in self.NO:
            return False
        return None
