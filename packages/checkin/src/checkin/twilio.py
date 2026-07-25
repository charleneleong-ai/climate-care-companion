"""Twilio channel — one API for both SMS and WhatsApp.

Practical advantages over talking to Meta directly:

- The WhatsApp sandbox sends real messages today, with no Meta business
  verification, which otherwise takes days.
- Quick-reply buttons work without template approval inside a 24-hour session,
  so the questionnaire is sendable as soon as the person has messaged in.
- SMS and WhatsApp differ only by an address prefix, so the fallback for someone
  without a smartphone is a parameter rather than a second integration.

Outbound is form-encoded to the 2010-04-01 Messages resource with HTTP Basic auth.
Inbound arrives as a form POST carrying `ButtonPayload` — invisible to the user —
which is where the question code rides, so a late reply still cannot be misfiled.
"""

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Any

from checkin.messages import ButtonMessage, TemplateMessage, encode_button_id
from checkin.sms import SmsFormatter

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

ALLOWED_RECIPIENTS_ENV = "CLIMATISE_TWILIO_ALLOWED_RECIPIENTS"


class TwilioTransport(StrEnum):
    SMS = auto()
    WHATSAPP = auto()

    def address(self, number: str) -> str:
        """WhatsApp addresses are prefixed; SMS addresses are bare E.164."""
        bare = number.removeprefix("whatsapp:")
        return f"whatsapp:{bare}" if self is TwilioTransport.WHATSAPP else bare


class TwilioFormatter:
    """Builds outbound form parameters and parses inbound webhooks. No network."""

    @staticmethod
    def outbound(
        to: str,
        sender: str,
        message: TemplateMessage | ButtonMessage,
        transport: TwilioTransport,
        content_sid: str | None = None,
    ) -> dict[str, str]:
        """Rich quick-reply when a Content template SID is configured, plain
        numbered text otherwise.

        The plain path is not a degraded mode — it is what SMS uses anyway, and it
        works on WhatsApp with no Content template set up at all. Buttons are an
        upgrade, not a prerequisite, which keeps the demo unblocked.
        """
        params = {
            "To": transport.address(to),
            "From": transport.address(sender),
        }
        if content_sid and isinstance(message, ButtonMessage):
            params["ContentSid"] = content_sid
            params["ContentVariables"] = TwilioFormatter.content_variables(message)
        else:
            params["Body"] = SmsFormatter.render(message)
        return params

    @staticmethod
    def content_variables(message: ButtonMessage) -> str:
        """Fill one reusable quick-reply Content template.

        Variable 1 is the question, 2 to 4 are the button payloads. One template
        serves every question, rather than one template per question — with
        twenty-three questions the latter is unmaintainable and each would need its
        own approval.
        """
        variables: dict[str, str] = {"1": message.body}
        for index, button in enumerate(message.buttons, start=2):
            variables[str(index)] = button.id
        return json.dumps(variables)

    @staticmethod
    def parse_inbound(form: dict[str, str], question_code: str | None = None) -> tuple[str, str | None]:
        """Return (sender, button_id).

        Prefers ButtonPayload, which carries the question code. Falls back to
        parsing Body as free text, because someone who types "1" instead of tapping
        the button has still answered — but that path needs the outstanding question
        supplied, since typed text carries no question code of its own.
        """
        sender = form.get("From", "").removeprefix("whatsapp:")
        if not sender:
            raise ValueError("Twilio webhook has no From field")

        payload = form.get("ButtonPayload")
        if payload:
            return sender, payload

        body = form.get("Body", "")
        if body and question_code:
            return sender, SmsFormatter.parse_reply(body, question_code)
        return sender, None

    @staticmethod
    def validate_signature(url: str, params: dict[str, str], signature: str, auth_token: str) -> bool:
        """Twilio's X-Twilio-Signature check.

        Not optional. An unauthenticated webhook lets anyone POST "yes, my bedroom
        is dangerously hot" for a real person and move their tier — injecting false
        health data into a system whose whole purpose is deciding who to send help
        to. Compared with hmac.compare_digest to avoid a timing oracle.
        """
        payload = url + "".join(f"{key}{params[key]}" for key in sorted(params))
        digest = hmac.new(
            auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1
        ).digest()
        expected = base64.b64encode(digest).decode("utf-8")
        return hmac.compare_digest(expected, signature)


@dataclass(slots=True)
class DryRunTwilio:
    """Captures the form parameters that would be POSTed. The default (SC-6)."""

    transport: TwilioTransport = TwilioTransport.WHATSAPP
    sender: str = "+14155238886"
    """Twilio's shared WhatsApp sandbox number."""
    content_sid: str | None = None
    sent: list[dict[str, str]] = field(default_factory=list)

    def send(self, to: str, message: TemplateMessage | ButtonMessage) -> str:
        params = TwilioFormatter.outbound(
            to, self.sender, message, self.transport, self.content_sid
        )
        self.sent.append(params)
        return f"dryrun-twilio-{len(self.sent)}"

    def transcript(self) -> list[str]:
        return [
            entry.get("Body") or f"[content {entry['ContentSid']}] {entry['ContentVariables']}"
            for entry in self.sent
        ]


class TwilioChannel:
    """Live sender. Guarded identically to the other channels: absent credentials
    refuse construction, and an unlisted recipient refuses send."""

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        sender: str | None = None,
        transport: TwilioTransport = TwilioTransport.WHATSAPP,
        content_sid: str | None = None,
        allowed_recipients: frozenset[str] | None = None,
        client: Any = None,
    ) -> None:
        self.account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN")
        self.sender = sender or os.environ.get("TWILIO_SENDER")
        if not self.account_sid or not self.auth_token or not self.sender:
            raise ValueError(
                "Twilio credentials are absent. Set TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN and TWILIO_SENDER, or use DryRunTwilio. "
                "Never commit these."
            )
        self.transport = transport
        self.content_sid = content_sid or os.environ.get("TWILIO_CONTENT_SID")
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

    @property
    def url(self) -> str:
        return f"{TWILIO_API_BASE}/Accounts/{self.account_sid}/Messages.json"

    def send(self, to: str, message: TemplateMessage | ButtonMessage) -> str:
        bare = to.removeprefix("whatsapp:")
        if bare not in self.allowed_recipients:
            raise PermissionError(
                f"{bare} is not on the allowlist. SC-6: this build sends only to "
                f"numbers listed in {ALLOWED_RECIPIENTS_ENV}, and only fictional "
                f"personas are seeded. Real recipients need a completed DPIA."
            )
        if self.client is None:
            raise RuntimeError("no HTTP client configured")
        response = self.client.post(
            self.url,
            data=TwilioFormatter.outbound(
                to, self.sender, message, self.transport, self.content_sid
            ),
            auth=(self.account_sid, self.auth_token),
        )
        response.raise_for_status()
        return response.json()["sid"]
