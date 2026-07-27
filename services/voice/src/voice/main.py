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
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Any

import httpx
from checkin.log import Channel, CheckinLog, CheckinRecord, Outcome, now_iso
from checkin.questions import QuestionBank, Questionnaire
from checkin.session import SessionStore
from checkin.twilio import DryRunTwilio, TwilioFormatter
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from exposure.openmeteo import OpenMeteoClient
from fastapi import BackgroundTasks, FastAPI, Header, Request, Response
from persons.loader import PersonaLoader
from voice.call import TwiMLBuilder, answer_from, questionnaire_for


@dataclass(slots=True)
class CallState:
    questionnaire: Questionnaire
    answers: dict[str, bool | None] = field(default_factory=dict)
    started_at: str = ""


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


# ── The check-in as a phone call ─────────────────────────────────────────────
#
# Inbound rather than outbound, and that is not only a demo convenience: a UK
# carrier silently drops an unknown US VoIP number calling a mobile, so an
# outbound call from this number rings at Twilio and never reaches the handset.
# Calling in is also closer to how a reassurance line actually gets used.

CALLS: dict[str, CallState] = {}
"""Answers so far, keyed by Twilio's CallSid. In memory because a call is minutes
long and a dropped call should start over rather than resume half-answered."""

BANK = QuestionBank.load()
CHECKINS = CheckinLog()
PERSONAS = PersonaLoader()
CORPUS = Corpus.load()
SCORER = RiskScorer(CORPUS)
VULNERABILITY = VulnerabilityScorer()
WEATHER = OpenMeteoClient(httpx.Client())

DEMO_PERSON = os.environ.get("CLIMATISE_VOICE_PERSON", "doris")
"""Who the line answers as. A real deployment would identify the caller by their
number; for a demonstrator, naming the persona in one place is honest and keeps
the call auditable."""


def public_base_url(request: Request) -> str:
    """The URL Twilio reached us on, so <Gather> actions point back at the tunnel
    rather than at localhost."""
    return os.environ.get("CLIMATISE_VOICE_URL") or str(request.base_url).rstrip("/")


SIMULATE_PEAK = float(os.environ.get("CLIMATISE_VOICE_SIMULATE_PEAK", "0")) or None
"""Demonstration only. The system is built not to fire on an ordinary warm day,
so on most days the honest questionnaire is empty and the call has nothing to
ask. Raising the temperature leaves every rule, threshold and question
untouched — the weather is the only thing pretended about."""


def questionnaire_now(person_id: str) -> Questionnaire:
    person = PERSONAS.load()[person_id]
    place = PERSONAS.places()[person_id]
    forecast = WEATHER.fetch(place.lat or 52.1364, place.lon or -0.4669, datetime.now(UTC))
    exposure = WEATHER.features_for(forecast, date.today(), place.dwelling_offset)
    if SIMULATE_PEAK:
        lift = SIMULATE_PEAK - exposure.peak_air
        exposure = replace(
            exposure,
            peak_air=SIMULATE_PEAK,
            peak_apparent=exposure.peak_apparent + lift,
            overnight_min=exposure.overnight_min + lift,
            indoor_day_est=exposure.indoor_day_est + lift,
            indoor_night_est=exposure.indoor_night_est + lift,
            hours_above_26=max(exposure.hours_above_26, 8),
            spell_day=max(exposure.spell_day, 3),
        )
    assessment = SCORER.assess(exposure, VULNERABILITY.profile(person))
    return questionnaire_for(BANK, person_id, assessment, date.today())


@app.post("/voice/checkin")
async def voice_checkin(request: Request, person: str | None = None) -> Response:
    """Who the call is for arrives on the query string, put there by the
    dispatcher, so an outbound call asks *that* person's questions.

    An inbound caller supplies nothing and is not identified, so they get the
    demonstrator persona and their answers are recorded against it — not against
    them. Identifying an inbound caller needs verification this does not yet do.
    """
    form = {k: str(v) for k, v in (await request.form()).items()}
    call_sid = form.get("CallSid", "unknown")
    builder = TwiMLBuilder(public_base_url(request))

    people = PERSONAS.load()
    person_id = person if person in people else DEMO_PERSON
    questionnaire = questionnaire_now(person_id)
    person = people[person_id]

    if not questionnaire.questions:
        # Tier Low asks nothing. Saying so plainly beats inventing a question to
        # justify the call — and beats a silent hang-up.
        return Response(
            builder.document(
                builder.say(
                    f"Hello {person.name}. This is Climatise. Conditions where you are "
                    f"are not a concern today, so there is nothing to ask. Goodbye."
                ),
                builder.hangup(),
            ),
            media_type="application/xml",
        )

    CALLS[call_sid] = CallState(questionnaire=questionnaire, answers={}, started_at=now_iso())
    return Response(
        builder.document(
            builder.opening(person.name, len(questionnaire.questions)),
            builder.question(questionnaire.questions[0], 0),
        ),
        media_type="application/xml",
    )


URGENT: Any = None
"""The sweep used to dispatch a red flag, built once on first use.

Lazy because building it loads the corpus, the interaction table, every persona
and a weather client — cost a webhook should not pay at import, and should never
pay at all on a deployment where nobody ever reports a red flag.
"""


def escalate(person_id: str) -> None:
    """Tell somebody, now, that this person has just reported a red flag.

    Never raises. It runs after the response has gone, so an exception here
    cannot reach Twilio and would otherwise be a silent traceback in a log
    nobody reads — the failure has to be visible as itself.
    """
    global URGENT
    try:
        if URGENT is None:
            from scheduler.build import build_sweep

            URGENT = build_sweep(send=SEND_FOR_REAL)
        dispatch = URGENT.escalate_now(person_id)
    except Exception as exc:
        print(f"[voice] urgent escalation for {person_id} failed: {type(exc).__name__}: {exc}")
        return
    if dispatch is None:
        # Nobody to tell. A real state worth naming — it is the case the
        # council view exists to find — not a failure.
        print(f"[voice] {person_id} reported a red flag and has no one to contact")
    else:
        print(f"[voice] {person_id} reported a red flag — told {dispatch.contact.name}")


SEND_FOR_REAL = os.environ.get("CLIMATISE_VOICE_DISPATCH") == "1"
"""Off by default. On, a red flag heard on a call sends a real message to a real
handset, and the first person to ring the demo number triggers it."""


@app.post("/voice/answer")
async def voice_answer(request: Request, background: BackgroundTasks, q: int = 0) -> Response:
    form = {k: str(v) for k, v in (await request.form()).items()}
    call_sid = form.get("CallSid", "unknown")
    builder = TwiMLBuilder(public_base_url(request))

    state = CALLS.get(call_sid)
    if state is None:
        # The call outlived the process, or someone POSTed at us directly.
        return Response(
            builder.document(
                builder.say("Sorry, I have lost track of this call."), builder.hangup()
            ),
            media_type="application/xml",
        )

    questions = state.questionnaire.questions
    if 0 <= q < len(questions):
        state.answers[questions[q].code] = answer_from(form.get("SpeechResult"), form.get("Digits"))

    nxt = q + 1
    if nxt < len(questions):
        return Response(
            builder.document(builder.question(questions[nxt], nxt)),
            media_type="application/xml",
        )

    report = state.questionnaire.to_self_report(state.answers)
    CHECKINS.record(
        CheckinRecord(
            person_id=state.questionnaire.person_id,
            channel=Channel.VOICE,
            outcome=Outcome.COMPLETED,
            started_at=state.started_at,
            completed_at=now_iso(),
            answers=dict(state.answers),
            red_flags=tuple(f.value for f in report.red_flags),
            reference=call_sid,
        )
    )
    CALLS.pop(call_sid, None)

    # Recorded first, then acted on — the escalation reads the log entry above,
    # so writing it is what makes the dispatch possible rather than merely
    # tidy. In the background because Twilio times the webhook out in seconds
    # and dispatch fetches a forecast; a caller must never wait in silence for
    # a message being sent to somebody else.
    if report.red_flags:
        background.add_task(escalate, state.questionnaire.person_id)

    return Response(
        builder.document(builder.closing(bool(report.red_flags)), builder.hangup()),
        media_type="application/xml",
    )


@app.post("/voice/status")
async def voice_status(request: Request) -> Response:
    """Twilio's end-of-call callback.

    Records the calls nobody answered. Without this the log would contain only
    conversations that happened, and a person who never picks up — the exact
    case the escalation ladder exists for — would leave no trace at all.
    """
    form = {k: str(v) for k, v in (await request.form()).items()}
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")

    state = CALLS.pop(call_sid, None)
    if status in {"completed"} and state is None:
        # Already recorded by the final answer handler.
        return Response(status_code=204)

    outcome = Outcome.ABANDONED if state else Outcome.NO_ANSWER
    CHECKINS.record(
        CheckinRecord(
            person_id=state.questionnaire.person_id if state else DEMO_PERSON,
            channel=Channel.VOICE,
            outcome=outcome,
            started_at=state.started_at if state else now_iso(),
            completed_at=now_iso(),
            answers=dict(state.answers) if state else {},
            reference=call_sid,
        )
    )
    return Response(status_code=204)


@app.get("/checkins/{person_id}")
def checkins_for(person_id: str) -> dict[str, Any]:
    """What the app reads to show "last check-in" on the companion screen."""
    records = CHECKINS.for_person(person_id)
    return {
        "person_id": person_id,
        "count": len(records),
        "checkins": [
            {
                "channel": r.channel.value,
                "outcome": r.outcome.value,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "answered": r.answered_count,
                "asked": len(r.answers),
                "red_flags": list(r.red_flags),
                "answers": r.answers,
            }
            for r in records[-10:]
        ],
    }
