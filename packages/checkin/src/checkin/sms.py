"""SMS channel.

Not a downgrade from WhatsApp — for this population it is the wider net. The 85+
cohort is the group least likely to have a smartphone at all, and a basic handset
takes SMS. WhatsApp buys interactive buttons; SMS buys reach.

The same ButtonMessage renders for both. Questionnaire and session are unchanged,
which is the point of the channel abstraction.

Provider note: GOV.UK Notify is the right live provider for a UK public-sector
deployment — free at public-sector volumes, built for exactly this, and it avoids
routing citizens' health-adjacent messages through a US commercial gateway. The
generic HTTP sender below is provider-shaped so Notify, Twilio or Vonage all fit.
"""

import os
from dataclasses import dataclass, field
from typing import Any

from checkin.messages import ButtonMessage, TemplateMessage, encode_button_id

GSM7_SEGMENT = 160
"""Single-segment limit for the GSM-7 alphabet. Concatenated messages cost a
segment each and arrive as one message on most handsets, but not all — an older
phone may show three fragments out of order."""

MAX_SEGMENTS = 2
"""A check-in question that needs three fragments is too long to answer."""

ALLOWED_RECIPIENTS_ENV = "CLIMATISE_SMS_ALLOWED_RECIPIENTS"

REPLY_TOKENS: dict[str, bool | None] = {
    "yes": True, "y": True, "1": True, "yeah": True, "yep": True,
    "no": False, "n": False, "2": False, "nope": False,
    "unsure": None, "3": None, "dunno": None, "?": None,
}
"""Deliberately generous on the yes/no side. Someone typing on a numeric keypad at
eighty-eight will not match a strict grammar, and a rejected reply reads to them as
being ignored."""


class SmsFormatter:
    """Renders channel-agnostic messages as plain text, and parses replies back.

    SMS has no interactive buttons, so the options become numbered text and the
    reply is free text mapped onto the same closed set the voice channel uses.
    """

    @staticmethod
    def render(message: TemplateMessage | ButtonMessage) -> str:
        if isinstance(message, TemplateMessage):
            if not message.is_bound:
                raise ValueError(
                    f"template {message.name} has unbound variables "
                    f"{message.variable_names}. Call bind() first."
                )
            body = message.body
            for index, value in enumerate(message.variables, start=1):
                body = body.replace(f"{{{{{index}}}}}", value)
            return body
        options = " ".join(
            f"{n}={button.title}" for n, button in enumerate(message.buttons, start=1)
        )
        return f"{message.body}\nReply {options}"

    @staticmethod
    def segments(text: str) -> int:
        return max(1, -(-len(text) // GSM7_SEGMENT))

    @classmethod
    def check_length(cls, text: str) -> None:
        if cls.segments(text) > MAX_SEGMENTS:
            raise ValueError(
                f"message is {cls.segments(text)} SMS segments and will fragment: {text!r}"
            )

    @staticmethod
    def parse_reply(text: str, question_code: str) -> str | None:
        """Map a free-text reply onto a button id, or None if unrecognised.

        Unrecognised is not an answer and never a guess. It follows the same rule as
        the voice channel: silence and confusion are escalated, not interpreted.
        """
        token = text.strip().lower().rstrip(".!")
        if token not in REPLY_TOKENS:
            return None
        return encode_button_id(question_code, REPLY_TOKENS[token])


@dataclass(slots=True)
class DryRunSms:
    """Captures what would be sent. The default, and the demo path (SC-6)."""

    sent: list[dict[str, str]] = field(default_factory=list)

    def send(self, to: str, message: TemplateMessage | ButtonMessage) -> str:
        text = SmsFormatter.render(message)
        SmsFormatter.check_length(text)
        self.sent.append({"to": to, "text": text})
        return f"dryrun-sms-{len(self.sent)}"

    def transcript(self) -> list[str]:
        return [entry["text"] for entry in self.sent]


class HttpSms:
    """Live sender, provider-agnostic.

    Guarded identically to CloudApiWhatsApp: absent credentials fail closed, and an
    unlisted recipient fails closed even with valid credentials.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        sender_id: str = "Climatise",
        allowed_recipients: frozenset[str] | None = None,
        client: Any = None,
    ) -> None:
        self.endpoint = endpoint or os.environ.get("SMS_API_ENDPOINT")
        self.api_key = api_key or os.environ.get("SMS_API_KEY")
        if not self.endpoint or not self.api_key:
            raise ValueError(
                "SMS credentials are absent. Set SMS_API_ENDPOINT and SMS_API_KEY, "
                "or use DryRunSms. Never commit these."
            )
        self.sender_id = sender_id
        self.allowed_recipients = (
            allowed_recipients
            if allowed_recipients is not None
            else self.allowlist_from_env()
        )
        self.client = client

    @staticmethod
    def allowlist_from_env() -> frozenset[str]:
        raw = os.environ.get(ALLOWED_RECIPIENTS_ENV, "")
        return frozenset(number.strip() for number in raw.split(",") if number.strip())

    def send(self, to: str, message: TemplateMessage | ButtonMessage) -> str:
        if to not in self.allowed_recipients:
            raise PermissionError(
                f"{to} is not on the allowlist. SC-6: this build sends only to numbers "
                f"listed in {ALLOWED_RECIPIENTS_ENV}, and only fictional personas are "
                f"seeded. Real recipients need a completed DPIA."
            )
        if self.client is None:
            raise RuntimeError("no HTTP client configured")
        text = SmsFormatter.render(message)
        SmsFormatter.check_length(text)
        response = self.client.post(
            self.endpoint,
            json={"phone_number": to, "message": text, "sender_id": self.sender_id},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        response.raise_for_status()
        return response.json().get("id", "")
