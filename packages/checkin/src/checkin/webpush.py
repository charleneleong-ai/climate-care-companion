"""Web Push — the channel that reaches the installed app itself.

Twilio reaches a phone number. This reaches the app on the home screen, which
matters because it is the only channel where tapping the alert lands the reader
on the plan rather than on a wall of text they have to act on from memory.

Deliberately NOT a `ConversationChannel`. It looked like one for a while, and the
conformance was actively dangerous: that interface addresses a recipient by phone
number and carries no tier, so the adapter had to invent one — it hardcoded High,
and the service worker reads exactly that field to decide whether a notification
overrides quieting. A Severe alert would have arrived silently, which is the one
outcome this system exists to prevent. Push is addressed by (person, audience)
and needs the real tier, so it is its own thing.

The other real difference is that a subscription can die — a browser expires it,
a phone is replaced — and the push service says so with a 404 or 410. That is a
normal end of life, not an error, and the store prunes rather than retrying
forever.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from checkin.messages import ButtonMessage, TemplateMessage
from checkin.storage import Fields, fields_for
from contracts import Audience, Tier

SUBSCRIPTIONS_PATH = Path(os.environ.get("CLIMATISE_PUSH_STORE", "/tmp/climatise-push.json"))
"""A file, because the scaffold has no database and a subscription that vanishes
on restart makes the feature impossible to demonstrate twice."""

GONE = (404, 410)
"""The push service telling us this endpoint will never work again."""


@dataclass(frozen=True, slots=True)
class PushSubscription:
    """What the browser hands over when someone allows notifications."""

    endpoint: str
    p256dh: str
    auth: str
    person_id: str
    audience: Audience

    def to_webpush_info(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "p256dh": self.p256dh,
            "auth": self.auth,
            "person_id": self.person_id,
            "audience": self.audience.value,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "PushSubscription":
        return cls(
            endpoint=raw["endpoint"],
            p256dh=raw["p256dh"],
            auth=raw["auth"],
            person_id=raw["person_id"],
            audience=Audience(raw["audience"]),
        )


class SubscriptionStore:
    """Who has the app installed, and as whom.

    Keyed by endpoint rather than by person: one caregiver may look after two
    people from one phone, and one person may be watched from a daughter's phone
    and a care home tablet at once.
    """

    def __init__(self, path: Path | None = None, backend: Fields | None = None) -> None:
        self.path = path or SUBSCRIPTIONS_PATH
        self.backend = backend or fields_for("climatise:push", self.path)
        self.subscriptions: dict[str, PushSubscription] = {}
        self.unreadable: str | None = None
        """Set when the store could not be parsed, so a caller can report a
        degraded store instead of guessing why nobody is registered."""
        self.read()

    def read(self) -> None:
        """Never raises.

        The API holds one of these as a module-level singleton, so a truncated
        store used to mean the service failed to import — and every phone that
        had registered went dark permanently, with no way for anyone to notice
        except alerts that stopped arriving. A store that has lost its contents
        is bad; a store that takes the whole service down with it is worse.
        """
        try:
            self.subscriptions = {
                endpoint: PushSubscription.from_json(row)
                for endpoint, row in self.backend.all().items()
            }
        except (ValueError, KeyError, TypeError) as exc:
            self.subscriptions = {}
            self.unreadable = f"{type(exc).__name__}: {exc}"
            return
        self.unreadable = self.backend.unreadable

    def add(self, subscription: PushSubscription) -> None:
        """Writes one endpoint's entry, not the whole map.

        Rewriting the map is what made this unsafe to run in more than one
        place: two people installing the app in the same second each wrote back
        a copy that omitted the other.
        """
        self.backend.put(subscription.endpoint, subscription.to_json())
        self.subscriptions[subscription.endpoint] = subscription

    def remove(self, endpoint: str) -> None:
        if self.subscriptions.pop(endpoint, None) is not None:
            self.backend.drop(endpoint)

    def for_person(self, person_id: str, audience: Audience) -> tuple[PushSubscription, ...]:
        return tuple(
            s
            for s in self.subscriptions.values()
            if s.person_id == person_id and s.audience is audience
        )


@dataclass(frozen=True, slots=True)
class PushPayload:
    """What the service worker renders. Deliberately small.

    `tier` travels as its own field rather than being inferred from the wording,
    because the worker uses it to decide whether the notification overrides
    quieting — and a Severe that arrives silently is the failure this system
    exists to prevent.
    """

    title: str
    body: str
    tier: Tier
    person_id: str
    url: str = "/companion"

    def encode(self) -> str:
        return json.dumps(
            {
                "title": self.title,
                "body": self.body,
                "tier": self.tier.name.title(),
                "personId": self.person_id,
                "url": self.url,
            }
        )


@dataclass(frozen=True, slots=True)
class PushOutcome:
    """What happened to one device.

    Carries the failure rather than raising it, so a caller can see that two of
    three phones were reached — which is the difference between "the alert went
    out" and "the alert went nowhere".
    """

    endpoint: str
    status: int | None
    """None when the send failed before any HTTP response — a bad key, a DNS
    failure. Distinct from a 500, which means the push service was reached."""
    error: str | None
    should_prune: bool

    @property
    def delivered(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


class WebPushChannel:
    """Sends to every device registered for a person and audience.

    Credentials absent means construction fails, matching TwilioChannel — a
    channel that silently does nothing is worse than one that refuses to exist.
    """

    def __init__(
        self,
        store: SubscriptionStore | None = None,
        vapid_private_key: str | None = None,
        vapid_subject: str | None = None,
        sender: Any = None,
    ) -> None:
        self.store = store or SubscriptionStore()
        self.vapid_private_key = vapid_private_key or os.environ.get("VAPID_PRIVATE_KEY")
        self.vapid_subject = vapid_subject or os.environ.get(
            "VAPID_SUBJECT", "mailto:hello@climatise.example"
        )
        if not self.vapid_private_key:
            raise ValueError(
                "VAPID_PRIVATE_KEY is absent. Generate a key pair with "
                "`uv run python -m checkin.vapid` and set it, or use a "
                "recording channel in tests."
            )
        # Injected by tests so no network call is made.
        self.sender = sender

    def push(self, subscription: PushSubscription, payload: PushPayload) -> int:
        arguments: dict[str, Any] = {
            "subscription_info": subscription.to_webpush_info(),
            "data": payload.encode(),
            "vapid_private_key": self.vapid_private_key,
            "vapid_claims": {"sub": self.vapid_subject},
        }
        if self.sender is not None:
            return self.sender(**arguments)

        # Imported here so the rest of the package stays importable without the
        # optional dependency.
        from pywebpush import webpush

        return webpush(**arguments).status_code

    def send_to(
        self, person_id: str, audience: Audience, payload: PushPayload
    ) -> tuple["PushOutcome", ...]:
        """One outcome per device. Never raises on a single device's failure.

        The bug this exists to prevent: one unusable subscription — an expired
        endpoint, a corrupted key — used to raise straight out of the loop, so a
        dead phone in someone's record silenced every *other* device on that
        record and took the sweep down with it. On a safety system the failure of
        one recipient must never become the failure of all of them.

        An empty tuple means nobody has the app installed, which is a real state
        worth surfacing rather than an error.
        """
        outcomes: list[PushOutcome] = []
        for subscription in self.store.for_person(person_id, audience):
            outcome = self.push_one(subscription, payload)
            if outcome.should_prune:
                self.store.remove(subscription.endpoint)
            outcomes.append(outcome)
        return tuple(outcomes)

    def push_one(self, subscription: PushSubscription, payload: PushPayload) -> "PushOutcome":
        try:
            status = self.push(subscription, payload)
        except Exception as exc:
            # A key that will not deserialise is as final as a 410 — it cannot
            # start working, so it is pruned rather than retried every three
            # hours for the life of the deployment.
            return PushOutcome(
                endpoint=subscription.endpoint,
                status=None,
                error=f"{type(exc).__name__}: {exc}",
                should_prune=isinstance(exc, ValueError),
            )
        return PushOutcome(
            endpoint=subscription.endpoint,
            status=status,
            error=None,
            should_prune=status in GONE,
        )

    @staticmethod
    def rendered(message: TemplateMessage | ButtonMessage) -> str:
        """Substitute WhatsApp's positional variables into the approved body.

        Only ever performed on an already-approved template with already-bound
        values — this fills placeholders, it does not write text.
        """
        if isinstance(message, ButtonMessage):
            return message.body
        if not message.is_bound:
            raise ValueError(
                f"refusing to push unbound template {message.name} — it would send "
                f"its own placeholders"
            )
        body = message.body
        for index, value in enumerate(message.variables, start=1):
            body = body.replace(f"{{{{{index}}}}}", value)
        return body
