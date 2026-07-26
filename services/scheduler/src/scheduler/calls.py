"""Placing the daily check-in call.

The sweep decides *whether* someone needs contacting. This decides *how*, and for
the voice channel it hands the conversation to `services/voice` — the call itself
is a dialogue, and a dialogue cannot be composed in advance the way a message can.

So this module is deliberately thin: it dials, and points Twilio at the endpoint
that already knows how to hold the conversation. Everything about which questions
get asked stays in `checkin`, where it is validated.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from checkin.preferences import Channel, ChannelPreference, PreferenceBook
from checkin.twilio import TwilioSendError
from contracts import Audience, Tier
from scheduler.contacts import ContactBook


@dataclass(frozen=True, slots=True)
class PlacedCall:
    person_id: str
    audience: Audience
    to: str
    call_sid: str


@dataclass(frozen=True, slots=True)
class CallOutcome:
    placed: tuple[PlacedCall, ...]
    skipped: tuple[tuple[str, str], ...]
    """(person_id, reason). Quiet hours, no contact, opted out — all normal, and
    all worth surfacing rather than dropping, because "nobody was called today"
    should be explicable."""


class CallDispatcher:
    """Dials, and lets the voice service do the talking."""

    def __init__(
        self,
        contacts: ContactBook,
        preferences: PreferenceBook,
        voice_base_url: str,
        caller_id: str,
        client: Any,
        account_sid: str,
        auth_token: str,
    ) -> None:
        self.contacts = contacts
        self.preferences = preferences
        self.voice_base_url = voice_base_url.rstrip("/")
        self.caller_id = caller_id
        self.client = client
        self.account_sid = account_sid
        self.auth_token = auth_token

    @property
    def url(self) -> str:
        return f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls.json"

    def place(self, preference: ChannelPreference, urgent: bool, now: datetime) -> PlacedCall:
        contact = self.contacts.get(preference.person_id, preference.audience)
        if contact is None:
            raise LookupError(f"no contact for {preference.person_id}")

        # The person id rides on the URL so the voice service asks *their*
        # questions rather than a hardcoded persona's.
        answer_url = (
            f"{self.voice_base_url}/voice/checkin?person={preference.person_id}"
            f"&urgent={'1' if urgent else '0'}"
        )
        response = self.client.post(
            self.url,
            auth=(self.account_sid, self.auth_token),
            data={
                "To": contact.msisdn,
                "From": self.caller_id,
                "Url": answer_url,
                "StatusCallback": f"{self.voice_base_url}/voice/status",
                "StatusCallbackEvent": "completed",
                "StatusCallbackMethod": "POST",
                # A frail person needs longer to reach the phone than the default
                # 60 seconds allows, and hanging up early records a no-answer that
                # never had a chance.
                "Timeout": "45",
            },
        )
        if response.status_code >= 400:
            raise TwilioSendError.from_response(response)
        return PlacedCall(
            person_id=preference.person_id,
            audience=preference.audience,
            to=contact.msisdn,
            call_sid=response.json()["sid"],
        )

    def daily_round(self, now: datetime, tier_by_person: dict[str, Tier]) -> CallOutcome:
        """Everyone who asked for a daily call, and is due one.

        Tier gates it: a daily check-in during a heat episode is a service, the
        same call on a mild Tuesday is a nuisance that gets the number blocked.
        """
        placed: list[PlacedCall] = []
        skipped: list[tuple[str, str]] = []

        for preference in self.preferences.daily_callees():
            tier = tier_by_person.get(preference.person_id, Tier.LOW)
            if tier is Tier.LOW:
                skipped.append((preference.person_id, "low risk, no call needed"))
                continue

            urgent = tier is Tier.SEVERE
            if not preference.may_disturb(now.time(), urgent):
                skipped.append((preference.person_id, "quiet hours"))
                continue
            if preference.channel is not Channel.VOICE:
                skipped.append((preference.person_id, f"prefers {preference.channel.value}"))
                continue

            try:
                placed.append(self.place(preference, urgent, now))
            except (LookupError, TwilioSendError) as exc:
                # One person's failure never becomes everyone's — the same rule
                # the sweep learned the hard way.
                skipped.append((preference.person_id, f"{type(exc).__name__}: {exc}"))

        return CallOutcome(placed=tuple(placed), skipped=tuple(skipped))
