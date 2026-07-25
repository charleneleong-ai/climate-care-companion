"""Inbound webhook for check-in conversations.

Twilio POSTs a form here whenever the person replies. The handler validates the
signature, advances their session, and sends whatever comes next.

Two properties this endpoint has to hold, because it is the one place an outsider
can reach:

- **Unsigned requests are rejected.** Without that check anyone can POST "yes, my
  bedroom is dangerously hot" for a real person and move their risk tier — false
  health data injected into a system that decides who gets a welfare visit.
- **An unknown sender is ignored, not errored.** Wrong numbers and stray messages
  reach any public number. Returning a 404 with detail would confirm which numbers
  the service is talking to, which is a disclosure about vulnerable people.
"""

import os
from datetime import UTC, datetime
from typing import Any

from checkin.session import SessionStore
from checkin.twilio import DryRunTwilio, TwilioFormatter
from fastapi import FastAPI, Header, Request, Response

app = FastAPI(
    title="Climatise check-in webhook",
    version="0.1.0",
    description="Demonstrator. Not medical advice.",
)

SESSIONS = SessionStore()

CHANNEL = DryRunTwilio()
"""SC-6: the scaffold replies into a capture buffer, not to a real handset. Track A
swaps in TwilioChannel once a DPIA and an allowlist exist."""

WEBHOOK_URL = os.environ.get("CLIMATISE_WEBHOOK_URL", "")
"""Must match the URL registered with Twilio exactly — the signature is computed
over it, so a mismatch rejects every request."""


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "sessions": len(SESSIONS.by_number)}


@app.post("/webhooks/twilio")
async def twilio_webhook(
    request: Request,
    x_twilio_signature: str = Header(default=""),
) -> Response:
    form = {key: str(value) for key, value in (await request.form()).items()}

    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if auth_token:
        if not TwilioFormatter.validate_signature(
            WEBHOOK_URL, form, x_twilio_signature, auth_token
        ):
            return Response(status_code=403)
    elif os.environ.get("CLIMATISE_ALLOW_UNSIGNED_WEBHOOKS") != "1":
        # Fail closed. A missing token is a misconfiguration, not permission to
        # accept anything that arrives.
        return Response(status_code=503)

    now = datetime.now(UTC)
    try:
        sender, _ = TwilioFormatter.parse_inbound(form)
    except ValueError:
        return Response(status_code=400)

    session = SESSIONS.get(sender)
    if session is None:
        # Silent 204: never confirm whether a number is known to the service.
        return Response(status_code=204)

    outstanding = session.outstanding_question
    _, button_id = TwilioFormatter.parse_inbound(
        form, question_code=outstanding.code if outstanding else None
    )

    if button_id:
        session.record_reply(button_id, now)
    else:
        # Unparseable, but they did respond — the window reopens and the
        # outstanding question is re-sent rather than being treated as answered.
        session.record_opener_acknowledged(now)

    reply = session.next_message(now)
    if reply is not None:
        CHANNEL.send(sender, reply)
        session.record_sent(now)

    return Response(status_code=204)
