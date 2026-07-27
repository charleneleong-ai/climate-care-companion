"""What happened on a check-in, kept.

A check-in that is asked and then forgotten is worse than one never made: the
caregiver has no way to know it happened, the council has no evidence of contact,
and the answers that would have changed tonight's advice are gone by morning.

Deliberately a file, and deliberately append-only. A database belongs here
eventually — the shape below is a table already — but the thing that matters now
is that an answer given at nine at night still exists at nine the next morning,
and that is one `write` away.

Two properties that are not incidental:

- **An unanswered call is recorded.** `outcome` distinguishes a completed
  conversation from one nobody picked up, because a missed check-in during a risk
  window is precisely the condition this system exists to catch. Storing only
  completions would make the most important case invisible.
- **The record is the answers, not a summary.** Whether the person said their
  bedroom was too hot is auditable; a derived tier is not, because the rules that
  derived it will change.
"""

import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum, auto
from pathlib import Path
from typing import Any

from checkin.storage import Rows, rows_for

CHECKIN_LOG_PATH = Path(os.environ.get("CLIMATISE_CHECKIN_LOG", "/tmp/climatise-checkins.json"))


class Channel(StrEnum):
    VOICE = auto()
    WHATSAPP = auto()
    SMS = auto()


class Outcome(StrEnum):
    COMPLETED = auto()
    """Every question asked and an answer recorded, including "unsure"."""
    ABANDONED = auto()
    """Started and stopped part-way — someone hung up mid-conversation."""
    NO_ANSWER = auto()
    """Never picked up. The case the whole escalation ladder exists for."""


@dataclass(frozen=True, slots=True)
class CheckinRecord:
    person_id: str
    channel: Channel
    outcome: Outcome
    started_at: str
    answers: dict[str, bool | None] = field(default_factory=dict)
    """Question code to yes / no / unsure. `None` means asked and not answered,
    which is different from not asked at all — the key's absence carries that."""
    red_flags: tuple[str, ...] = ()
    reference: str = ""
    """The channel's own id — a Twilio CallSid or message SID — so a record can be
    traced back to the carrier's log during an incident review."""
    completed_at: str | None = None

    @property
    def answered_count(self) -> int:
        return sum(1 for value in self.answers.values() if value is not None)

    def to_json(self) -> dict[str, Any]:
        return {**asdict(self), "channel": self.channel.value, "outcome": self.outcome.value}

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "CheckinRecord":
        return cls(
            person_id=raw["person_id"],
            channel=Channel(raw["channel"]),
            outcome=Outcome(raw["outcome"]),
            started_at=raw["started_at"],
            answers=raw.get("answers", {}),
            red_flags=tuple(raw.get("red_flags", ())),
            reference=raw.get("reference", ""),
            completed_at=raw.get("completed_at"),
        )


class CheckinLog:
    """Every check-in, most recent last.

    Mirrors `SubscriptionStore` on purpose — same atomic write, same
    never-raises read — because both learned the same lesson: a service that
    cannot start because one file is malformed takes every user down with it.
    """

    def __init__(self, path: Path | None = None, backend: Rows | None = None) -> None:
        self.path = path or CHECKIN_LOG_PATH
        self.backend = backend or rows_for("climatise:checkins", self.path)
        self.records: list[CheckinRecord] = []
        self.unreadable: str | None = None
        self.read()

    def read(self) -> None:
        try:
            self.records = [CheckinRecord.from_json(row) for row in self.backend.all()]
        except (ValueError, KeyError, TypeError) as exc:
            self.records = []
            self.unreadable = f"{type(exc).__name__}: {exc}"
            return
        self.unreadable = self.backend.unreadable

    def record(self, entry: CheckinRecord) -> None:
        """Appends through the backend rather than rewriting the collection.

        The whole-file rewrite this replaces read every record into memory,
        added one, and wrote them all back — so a second writer's check-in
        disappeared. A missed call that the log has silently dropped is exactly
        the event the escalation ladder exists to notice.
        """
        self.backend.append(entry.to_json())
        self.records.append(entry)

    def for_person(self, person_id: str) -> tuple[CheckinRecord, ...]:
        return tuple(r for r in self.records if r.person_id == person_id)

    def latest_for(self, person_id: str) -> CheckinRecord | None:
        found = self.for_person(person_id)
        return found[-1] if found else None

    def consecutive_missed(self, person_id: str) -> int:
        """Unanswered check-ins at the end of the run, most recent first.

        Counted from the end rather than totalled, because a pattern is a claim
        about *now*: someone who missed three calls in March and has answered
        every one since is not the person the escalation is for.
        """
        missed = 0
        for record in reversed(self.for_person(person_id)):
            if record.outcome is Outcome.COMPLETED:
                break
            missed += 1
        return missed


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
