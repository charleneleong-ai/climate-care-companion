"""How each person wants to be reached, and when.

Not a settings screen for its own sake. The channel *is* the intervention here:
an 88-year-old with a landline and no smartphone is unreachable by push and
illiterate to WhatsApp, while her daughter reads neither at work but answers a
phone. Sending everyone the same thing on the same channel is how a system with
correct advice still fails to deliver any of it.

Three things are separate on purpose:

- **Channel per audience.** The caregiver and the cared-for person are reached
  differently far more often than not.
- **A daily call time.** A check-in at 3pm during a heat episode is worth more
  than one at 9am, but a call at 8pm to someone who goes to bed at seven is a
  fright rather than a service.
- **Quiet hours that alerts may cross.** A routine check-in respects them; a
  Severe transition does not. Somebody deciding they would rather not be woken
  should not thereby opt out of the one message that matters.
"""

import csv
from dataclasses import dataclass, field
from datetime import time
from enum import StrEnum, auto
from pathlib import Path

from contracts import Audience

PREFERENCES_PATH = Path(__file__).resolve().parents[4] / "data" / "seed" / "preferences.csv"


class Channel(StrEnum):
    VOICE = auto()
    WHATSAPP = auto()
    SMS = auto()
    PUSH = auto()
    NONE = auto()
    """Explicitly opted out. Distinct from an absent row, which means nobody has
    asked them yet — and which should prompt asking rather than silence."""


DEFAULT_CALL_TIME = time(15, 0)
"""Mid-afternoon: past the point a hot day has built up, with enough of the day
left to act on the answer."""

DEFAULT_QUIET_START, DEFAULT_QUIET_END = time(21, 0), time(8, 0)


@dataclass(frozen=True, slots=True)
class ChannelPreference:
    person_id: str
    audience: Audience
    channel: Channel
    call_time: time = DEFAULT_CALL_TIME
    quiet_start: time = DEFAULT_QUIET_START
    quiet_end: time = DEFAULT_QUIET_END
    daily_checkin: bool = False
    """Whether to call every day during a risk window, rather than only when the
    tier rises. Opt-in — a daily call nobody asked for is a nuisance that gets
    the number blocked."""

    def in_quiet_hours(self, at: time) -> bool:
        if self.quiet_start <= self.quiet_end:
            return self.quiet_start <= at < self.quiet_end
        # Wraps midnight, which is the normal case for 21:00–08:00.
        return at >= self.quiet_start or at < self.quiet_end

    def may_disturb(self, at: time, urgent: bool) -> bool:
        """Urgent overrides quiet hours. That is the whole point of the flag —
        the alternative is a preference that silently suppresses the alert the
        person most needed."""
        return urgent or not self.in_quiet_hours(at)


def parse_time(raw: str, fallback: time) -> time:
    if not raw.strip():
        return fallback
    hour, _, minute = raw.partition(":")
    return time(int(hour), int(minute or 0))


class PreferenceBook:
    """Lookup from (person, audience) to how they want to be contacted.

    A missing row is deliberately not a default-to-everything: `preference_for`
    returns None, and callers decide. Guessing that someone wants a phone call is
    how a service becomes the thing people complain about.
    """

    def __init__(self, preferences: tuple[ChannelPreference, ...]) -> None:
        self.by_key = {(p.person_id, p.audience): p for p in preferences}

    @classmethod
    def load(cls, path: Path | None = None) -> "PreferenceBook":
        with (path or PREFERENCES_PATH).open(newline="") as handle:
            rows = csv.DictReader(row for row in handle if not row.startswith("#"))
            return cls(
                tuple(
                    ChannelPreference(
                        person_id=row["person_id"],
                        audience=Audience(row["audience"]),
                        channel=Channel(row["channel"]),
                        call_time=parse_time(row.get("call_time", ""), DEFAULT_CALL_TIME),
                        quiet_start=parse_time(row.get("quiet_start", ""), DEFAULT_QUIET_START),
                        quiet_end=parse_time(row.get("quiet_end", ""), DEFAULT_QUIET_END),
                        daily_checkin=row.get("daily_checkin", "").strip().lower()
                        in {"1", "true", "yes"},
                    )
                    for row in rows
                )
            )

    def preference_for(self, person_id: str, audience: Audience) -> ChannelPreference | None:
        return self.by_key.get((person_id, audience))

    def daily_callees(self) -> tuple[ChannelPreference, ...]:
        return tuple(
            p for p in self.by_key.values() if p.daily_checkin and p.channel is Channel.VOICE
        )
