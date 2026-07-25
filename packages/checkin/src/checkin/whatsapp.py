"""WhatsApp Cloud API channel.

Payload shapes target Graph API v21.0: a single POST to
`/{PHONE_NUMBER_ID}/messages` for every message type.

SC-6. The scaffold does not send to real people. `DryRunWhatsApp` is the default
and captures payloads instead of transmitting them, so the whole flow demonstrates
with no Meta account, no verified number and no message cost. `CloudApiWhatsApp`
refuses to construct without explicit credentials, and refuses to send to a number
that is not on an explicit allowlist — a fictional persona has no phone number, so
there is nothing to send to by accident.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from checkin.messages import ButtonMessage, TemplateMessage

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = "https://graph.facebook.com"

ALLOW_REAL_SENDS_ENV = "CLIMATISE_WHATSAPP_ALLOWED_RECIPIENTS"
"""Comma-separated E.164 numbers. Absent or empty means no real send is possible."""


class WhatsAppFormatter:
    """Builds Cloud API request bodies. No network, so the payloads are unit-testable."""

    @staticmethod
    def template(to: str, message: TemplateMessage) -> dict[str, Any]:
        if not message.is_bound:
            raise ValueError(
                f"template {message.name} has unbound variables "
                f"{message.variable_names}. Call bind() — sending a placeholder to a "
                f"vulnerable person is worse than not sending."
            )
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": message.name,
                "language": {"code": message.language},
            },
        }
        if message.variables:
            payload["template"]["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": value} for value in message.variables
                    ],
                }
            ]
        return payload

    @staticmethod
    def buttons(to: str, message: ButtonMessage) -> dict[str, Any]:
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": message.body},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": button.id, "title": button.title},
                        }
                        for button in message.buttons
                    ]
                },
            },
        }

    @classmethod
    def build(cls, to: str, message: TemplateMessage | ButtonMessage) -> dict[str, Any]:
        if isinstance(message, TemplateMessage):
            return cls.template(to, message)
        return cls.buttons(to, message)

    @staticmethod
    def parse_inbound(payload: dict[str, Any]) -> tuple[str, str | None]:
        """Extract (from_number, button_id) from a Cloud API webhook body.

        button_id is None for any inbound that is not a button press — a typed
        message, an image, a voice note. Those still open the 24-hour window, which
        is why the sender is returned regardless.
        """
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            message = value["messages"][0]
        except (KeyError, IndexError) as exc:
            raise ValueError(f"not a WhatsApp inbound message webhook: {exc}") from exc

        sender = message["from"]
        if message.get("type") == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                return sender, interactive["button_reply"]["id"]
        return sender, None


@runtime_checkable
class ConversationChannel(Protocol):
    """Asynchronous message delivery.

    Deliberately not VoiceChannel. A phone call is synchronous — ask, hear an
    answer. A message conversation is not: send, then wait for a webhook that may
    arrive in minutes or never. Collapsing the two would hide the case that matters
    most, which is the reply that never comes.
    """

    def send(self, to: str, message: TemplateMessage | ButtonMessage) -> str: ...


@dataclass(slots=True)
class DryRunWhatsApp:
    """Captures what would be sent. The default, and the demo path.

    Every payload is exactly what CloudApiWhatsApp would POST, so reviewing a
    transcript reviews the real thing.
    """

    sent: list[dict[str, Any]] = field(default_factory=list)

    def send(self, to: str, message: TemplateMessage | ButtonMessage) -> str:
        payload = WhatsAppFormatter.build(to, message)
        self.sent.append(payload)
        return f"dryrun-{len(self.sent)}"

    def transcript(self) -> list[str]:
        """Human-readable, for demoing without reading JSON."""
        lines: list[str] = []
        for payload in self.sent:
            if payload["type"] == "template":
                lines.append(f"[template {payload['template']['name']}]")
            else:
                body = payload["interactive"]["body"]["text"]
                titles = " / ".join(
                    b["reply"]["title"] for b in payload["interactive"]["action"]["buttons"]
                )
                lines.append(f"{body}  [{titles}]")
        return lines


class CloudApiWhatsApp:
    """Live sender. Constructing it requires credentials; sending requires an
    allowlisted recipient.

    Two independent guards because one is not enough for a system whose whole
    subject matter is vulnerable people: missing credentials fail closed, and an
    unlisted number fails closed even with valid credentials.
    """

    def __init__(
        self,
        phone_number_id: str | None = None,
        access_token: str | None = None,
        allowed_recipients: frozenset[str] | None = None,
        client: Any = None,
    ) -> None:
        self.phone_number_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
        self.access_token = access_token or os.environ.get("WHATSAPP_ACCESS_TOKEN")
        if not self.phone_number_id or not self.access_token:
            raise ValueError(
                "WhatsApp credentials are absent. Set WHATSAPP_PHONE_NUMBER_ID and "
                "WHATSAPP_ACCESS_TOKEN, or use DryRunWhatsApp. Never commit these."
            )
        self.allowed_recipients = (
            allowed_recipients
            if allowed_recipients is not None
            else self.allowlist_from_env()
        )
        self.client = client

    @staticmethod
    def allowlist_from_env() -> frozenset[str]:
        raw = os.environ.get(ALLOW_REAL_SENDS_ENV, "")
        return frozenset(number.strip() for number in raw.split(",") if number.strip())

    @property
    def url(self) -> str:
        return f"{GRAPH_BASE_URL}/{GRAPH_API_VERSION}/{self.phone_number_id}/messages"

    def send(self, to: str, message: TemplateMessage | ButtonMessage) -> str:
        if to not in self.allowed_recipients:
            raise PermissionError(
                f"{to} is not on the allowlist. SC-6: this build sends only to numbers "
                f"listed in {ALLOW_REAL_SENDS_ENV}, and only fictional personas are "
                f"seeded. Real recipients need a completed DPIA."
            )
        if self.client is None:
            raise RuntimeError("no HTTP client configured")
        response = self.client.post(
            self.url,
            json=WhatsAppFormatter.build(to, message),
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        response.raise_for_status()
        return response.json()["messages"][0]["id"]
