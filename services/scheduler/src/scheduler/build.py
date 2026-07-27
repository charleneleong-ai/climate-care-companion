"""Assembling a sweep from its parts.

Separate from `__main__` so that something other than the CLI can run a sweep.
The cron endpoint needs exactly this and nothing else from the scheduler, and
importing `__main__` to get it would drag in typer, rich, and a Typer app that
builds itself at import time — none of which belong in a web request.
"""

import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import httpx
from actions.checklist import PreventionPlanBuilder
from actions.interactions import InteractionTable
from actions.notify import NotificationPolicy, PersonState
from checkin.messages import ButtonMessage, TemplateMessage
from checkin.storage import Fields, fields_for
from checkin.twilio import TwilioChannel
from contracts import ExposureFeatures
from core.corpus import Corpus
from core.scoring import RiskScorer
from exposure.openmeteo import OpenMeteoClient
from persons.loader import PersonaLoader
from scheduler.contacts import ContactBook
from scheduler.sweep import HeatSweep, SweepResult

POLICY_KEY = "climatise:notify"
POLICY_PATH = Path(os.environ.get("CLIMATISE_NOTIFY_STATE", "/tmp/climatise-notify.json"))


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


def build_sweep(
    send: bool,
    simulate_peak: float | None = None,
    policy: NotificationPolicy | None = None,
) -> HeatSweep:
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
        policy=policy,
    )


def load_policy(backend: Fields) -> NotificationPolicy:
    """What everyone was last told, recovered from the last run.

    Without this the policy is empty at every start, and an empty policy has
    never told anyone anything — so FR-21's "upward transition" reads as a first
    rise for the whole register and FR-22's six-hour window has nothing to
    measure from. A long-running process hides that by never restarting. A cron
    invocation is a new process every time, so every sweep would re-alert
    everybody: precisely the cry-wolf failure the rules exist to prevent, and
    the one a caregiver responds to by muting the system.
    """
    return NotificationPolicy(
        state={person_id: PersonState.from_json(row) for person_id, row in backend.all().items()}
    )


def save_policy(policy: NotificationPolicy, backend: Fields) -> None:
    for person_id, state in policy.state.items():
        backend.put(person_id, state.to_json())


def run_sweep(send: bool, simulate_peak: float | None = None) -> SweepResult:
    """One pass, with the memory that makes the next pass correct.

    The save has to happen even though `run` isolates per-person failures: the
    people it did assess were still told, and forgetting that is what produces a
    duplicate alert an hour later.
    """
    backend = fields_for(POLICY_KEY, POLICY_PATH)
    policy = load_policy(backend)
    result = build_sweep(send, simulate_peak, policy=policy).run()
    save_policy(policy, backend)
    return result
