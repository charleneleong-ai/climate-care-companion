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

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum, auto
from pathlib import Path
from threading import Lock
from typing import Any

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

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CHECKIN_LOG_PATH
        self.records: list[CheckinRecord] = []
        self.lock = Lock()
        self.unreadable: str | None = None
        self.read()

    def read(self) -> None:
        if not self.path.exists():
            return
        try:
            rows = json.loads(self.path.read_text() or "[]")
            self.records = [CheckinRecord.from_json(row) for row in rows]
            self.unreadable = None
        except (ValueError, KeyError, TypeError) as exc:
            self.records = []
            self.unreadable = f"{type(exc).__name__}: {exc}"

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([r.to_json() for r in self.records], indent=2)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(payload)
        temporary.replace(self.path)

    def record(self, entry: CheckinRecord) -> None:
        with self.lock:
            self.records.append(entry)
            self.write()

    def for_person(self, person_id: str) -> tuple[CheckinRecord, ...]:
        return tuple(r for r in self.records if r.person_id == person_id)

    def latest_for(self, person_id: str) -> CheckinRecord | None:
        found = self.for_person(person_id)
        return found[-1] if found else None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
