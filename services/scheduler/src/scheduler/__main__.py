"""The three-hourly loop, as a long-running process.

    uv run python -m scheduler run           # loop until killed
    uv run python -m scheduler once          # one pass, prints what would send
    uv run python -m scheduler once --send   # one pass, actually sends

`once` defaults to a dry run because the alternative is a command that texts five
people the first time someone tries it.
"""

import os
import time
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import quote

import httpx
import typer
from typing import Any
from actions.checklist import PreventionPlanBuilder
from actions.interactions import InteractionTable
from checkin.env import load_env
from checkin.messages import ButtonMessage, TemplateLibrary, TemplateMessage
from checkin.twilio import TwilioChannel
from checkin.webpush import WebPushChannel
from core.corpus import Corpus
from contracts import ExposureFeatures, Tier
from core.scoring import RiskScorer
from exposure.openmeteo import OpenMeteoClient
from persons.loader import PersonaLoader
from rich.console import Console
from checkin.preferences import PreferenceBook
from scheduler.calls import CallDispatcher
from scheduler.contacts import ContactBook
from scheduler.sweep import HeatSweep, SweepResult, next_sweep_at

# Before any channel is constructed. Credentials live in a gitignored .env at the
# repo root; without this they sit on disk and every send reports them as absent.
load_env()

app = typer.Typer(help="Climatise proactive sweep. Demonstrator — SC-6.")
console = Console()


class DryRunChannel:
    """Prints instead of sending. The default, deliberately."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, TemplateMessage | ButtonMessage]] = []

    def send(self, to: str, message: TemplateMessage | ButtonMessage) -> str:
        self.sent.append((to, message))
        return f"dry-run-{len(self.sent)}"


class SimulatedHeat:
    """A real forecast with the temperature raised, for demonstrating the push path.

    Necessary because the system is built not to fire on an ordinary warm day, so
    on most days there is nothing to show. Everything downstream is untouched —
    the same rules, the same corpus, the same thresholds — which is the point: the
    weather is the only thing being pretended about.
    """

    def __init__(self, inner: OpenMeteoClient, peak: float) -> None:
        self.inner = inner
        self.peak = peak

    def fetch(self, latitude: float, longitude: float, when: datetime):
        return self.inner.fetch(latitude, longitude, when)

    def features_for(self, forecast, day, dwelling_offset: float) -> ExposureFeatures:
        real = self.inner.features_for(forecast, day, dwelling_offset)
        lift = self.peak - real.peak_air
        return replace(
            real,
            peak_air=self.peak,
            peak_apparent=real.peak_apparent + lift,
            overnight_min=real.overnight_min + lift,
            indoor_day_est=real.indoor_day_est + lift,
            indoor_night_est=real.indoor_night_est + lift,
            hours_above_26=max(real.hours_above_26, 8),
            spell_day=max(real.spell_day, 3),
        )


def build_sweep(send: bool, simulate_peak: float | None = None) -> HeatSweep:
    corpus = Corpus.load()
    weather = OpenMeteoClient(httpx.Client())
    return HeatSweep(
        personas=PersonaLoader(),
        weather=SimulatedHeat(weather, simulate_peak) if simulate_peak else weather,
        scorer=RiskScorer(corpus),
        planner=PreventionPlanBuilder(corpus, InteractionTable.load()),
        contacts=ContactBook.load(),
        # TwilioChannel takes its HTTP client by injection and refuses to send
        # without one, so it has to be handed in here rather than defaulted.
        channel=TwilioChannel(client=httpx.Client()) if send else DryRunChannel(),
    )


def report(result: SweepResult, sent_for_real: bool) -> None:
    verb = "sent" if sent_for_real else "would send"
    console.print(
        f"[dim]{result.at:%Y-%m-%d %H:%M}[/dim]  assessed {result.assessed}, "
        f"{verb} {len(result.dispatched)}"
    )
    for dispatch in result.dispatched:
        rise = (
            "first assessment"
            if dispatch.notification.is_first_ever
            else f"{dispatch.notification.from_tier.name.title()} → "
            f"{dispatch.notification.to_tier.name.title()}"
        )
        console.print(
            f"  [bold]{dispatch.contact.name}[/bold] ({dispatch.notification.audience}) · {rise}"
        )
        console.print(f"    [dim]{dispatch.message.body}[/dim]")
        for name, value in zip(
            dispatch.message.variable_names, dispatch.message.variables, strict=True
        ):
            console.print(f"      [dim]{{{name}}}[/dim] {value}")
    for person_id, audience in result.unreachable:
        console.print(f"  [yellow]{person_id} rose but has no {audience}[/yellow]")


@app.command()
def once(
    send: bool = typer.Option(False, help="Actually send. Off by default."),
    simulate_peak: float | None = typer.Option(
        None, help="Pretend the day peaks at this many °C. For demonstrations."
    ),
) -> None:
    if simulate_peak:
        console.print(f"[yellow]Simulating a {simulate_peak}°C day — not real weather.[/yellow]")
    report(build_sweep(send, simulate_peak).run(), sent_for_real=send)


@app.command()
def invite(
    to: str = typer.Argument(..., help="E.164 number, e.g. +447700900123."),
    area: str = typer.Option("Bedford", help="Area the warning covers."),
    level: str = typer.Option("amber", help="UKHSA alert level: yellow, amber, red."),
    start: str = typer.Option("midday tomorrow", help="When the warning begins."),
    base_url: str = typer.Option(
        "http://localhost:3000",
        help="Where the app is reachable FROM THE PHONE. localhost will not open "
        "on a handset — use a LAN address or a tunnel.",
    ),
    send: bool = typer.Option(False, help="Actually send. Off by default."),
) -> None:
    """The acquisition message: a warning, and a link into the app.

    Separate from the sweep because it is a different act. The sweep tells people
    already registered that their own risk has moved; this tells a stranger that
    their area is under warning and that a personal answer exists. Nothing is
    known about the recipient, and the wording is careful not to imply otherwise.
    """
    link = f"{base_url.rstrip('/')}/join?area={quote(area)}&level={quote(level)}&from=UKHSA"
    message = TemplateLibrary.load().get("heat_alert_invite").bind(area, start, link)
    rendered = WebPushChannel.rendered(message)

    console.print(f"[dim]to[/dim] {to}")
    console.print(f"[dim]via[/dim] {'Twilio WhatsApp' if send else 'dry run'}\n")
    console.print(rendered)
    console.print(f"\n[dim]link opens[/dim] {link}")

    if "localhost" in base_url and send:
        console.print(
            "\n[yellow]Warning: a localhost link will not open on a phone. "
            "Pass --base-url with a LAN address or tunnel.[/yellow]"
        )

    if not send:
        console.print("\n[dim]Dry run. Add --send to deliver it.[/dim]")
        return

    channel = TwilioChannel(client=httpx.Client())
    sid = channel.send(to, message)
    console.print(f"\n[green]Sent.[/green] Twilio message SID {sid}")


@app.command()
def run(
    send: bool = typer.Option(False, help="Actually send. Off by default."),
    every_hours: int = typer.Option(3, help="§5.3 cadence."),
    simulate_peak: float | None = typer.Option(
        None, help="Pretend every day peaks at this many °C. For demonstrations."
    ),
) -> None:
    sweep = build_sweep(send, simulate_peak)
    while True:
        report(sweep.run(), sent_for_real=send)
        wake = next_sweep_at(datetime.now(UTC), every_hours)
        console.print(f"[dim]next sweep {wake:%H:%M}[/dim]", highlight=False)
        time.sleep(max(0.0, (wake - datetime.now(UTC)).total_seconds()))


class DryRunCalls:
    """Reports what it would dial. Mirrors Twilio's response shape closely enough
    that the dispatcher takes the same path either way."""

    def __init__(self) -> None:
        self.dialled: list[dict[str, str]] = []

    def post(self, url: str, auth: tuple[str, str], data: dict[str, str]) -> Any:
        self.dialled.append(data)

        class Response:
            status_code = 201

            @staticmethod
            def json() -> dict[str, str]:
                return {"sid": f"CAdry{len(self.dialled):03d}"}

        return Response()


@app.command()
def daily(
    send: bool = typer.Option(False, help="Actually dial. Off by default."),
    simulate_peak: float | None = typer.Option(
        None, help="Pretend the day peaks at this many °C. For demonstrations."
    ),
    voice_url: str = typer.Option("", help="Public base URL of the voice service."),
) -> None:
    """Today's check-in calls, for everyone who asked for one.

    Separate from `once`, which dispatches on a tier *rise*. This is the standing
    arrangement: someone who asked to be rung every day during a heat episode.
    Tier still gates it — the same call on a mild Tuesday is a nuisance that gets
    the number blocked.
    """
    sweep = build_sweep(send=False, simulate_peak=simulate_peak)
    result = sweep.run()
    tiers = {pid: sweep.policy.seen(pid).last_tier or Tier.LOW for pid in sweep.personas.load()}

    client = httpx.Client() if send else DryRunCalls()
    dispatcher = CallDispatcher(
        contacts=ContactBook.load(),
        preferences=PreferenceBook.load(),
        voice_base_url=voice_url or os.environ.get("CLIMATISE_VOICE_URL", ""),
        caller_id=os.environ.get("TWILIO_VOICE_CALLER_ID", "+16089030949"),
        client=client,
        account_sid=os.environ.get("TWILIO_ACCOUNT_SID", ""),
        auth_token=os.environ.get("TWILIO_AUTH_TOKEN", ""),
    )
    outcome = dispatcher.daily_round(result.at, tiers)

    verb = "dialled" if send else "would dial"
    console.print(f"[dim]{result.at:%Y-%m-%d %H:%M}[/dim]  {verb} {len(outcome.placed)}")
    for call in outcome.placed:
        console.print(
            f"  [bold]{call.person_id}[/bold] ({call.audience}) → {call.to}  {call.call_sid}"
        )
    for person_id, reason in outcome.skipped:
        console.print(f"  [yellow]{person_id} skipped — {reason}[/yellow]")


if __name__ == "__main__":
    app()
