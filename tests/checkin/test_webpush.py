"""Web Push.

The channel's failure mode is silence, so the tests are about what reaches a
device and what is refused before it can.
"""

import json

import pytest
from checkin.messages import TemplateLibrary
from checkin.webpush import (
    GONE,
    PushPayload,
    PushSubscription,
    SubscriptionStore,
    WebPushChannel,
)
from checkin.vapid import generate
from contracts import Audience, Tier

KEY = "-----BEGIN PRIVATE KEY-----\nstub\n-----END PRIVATE KEY-----"


def subscription(endpoint: str, person_id: str = "doris", audience=Audience.CAREGIVER):
    return PushSubscription(
        endpoint=endpoint,
        p256dh="p256dh-stub",
        auth="auth-stub",
        person_id=person_id,
        audience=audience,
    )


@pytest.fixture
def store(tmp_path) -> SubscriptionStore:
    return SubscriptionStore(tmp_path / "push.json")


class Recorder:
    """Stands in for pywebpush. Returns whatever status it was told to."""

    def __init__(self, status: int = 201) -> None:
        self.status = status
        self.calls: list[dict] = []

    def __call__(self, **kwargs) -> int:
        self.calls.append(kwargs)
        return self.status


class Exploding:
    """Fails for one endpoint, succeeds for every other."""

    def __init__(self, bad: str, exc: Exception) -> None:
        self.bad = bad
        self.exc = exc
        self.reached: list[str] = []

    def __call__(self, **kwargs) -> int:
        endpoint = kwargs["subscription_info"]["endpoint"]
        self.reached.append(endpoint)
        if endpoint == self.bad:
            raise self.exc
        return 201


# ─────────────────────────────────────────────────────────────── the store


def test_subscriptions_survive_a_restart(store, tmp_path):
    """A subscription lost on restart makes the feature impossible to demo twice."""
    store.add(subscription("https://push.example/a"))
    assert SubscriptionStore(tmp_path / "push.json").for_person("doris", Audience.CAREGIVER)


def test_one_phone_can_be_registered_for_two_people(store):
    store.add(subscription("https://push.example/a", person_id="doris"))
    store.add(subscription("https://push.example/b", person_id="harold"))
    assert len(store.for_person("doris", Audience.CAREGIVER)) == 1
    assert len(store.for_person("harold", Audience.CAREGIVER)) == 1


def test_one_person_can_be_watched_from_two_devices(store):
    """A daughter's phone and a care home tablet."""
    store.add(subscription("https://push.example/a"))
    store.add(subscription("https://push.example/b"))
    assert len(store.for_person("doris", Audience.CAREGIVER)) == 2


def test_re_registering_the_same_device_does_not_duplicate_it(store):
    store.add(subscription("https://push.example/a"))
    store.add(subscription("https://push.example/a"))
    assert len(store.for_person("doris", Audience.CAREGIVER)) == 1


def test_the_two_audiences_are_addressed_separately(store):
    """Registering a phone as caregiver must not make it receive the person's
    message as well — that is how someone reads both voices and trusts neither."""
    store.add(subscription("https://push.example/a", audience=Audience.CAREGIVER))
    assert store.for_person("doris", Audience.CARED_FOR) == ()


# ──────────────────────────────────────────────────────────────── the channel


def test_absent_credentials_refuse_construction(monkeypatch, tmp_path):
    """A channel that silently does nothing is worse than one that will not exist.

    The env var is cleared explicitly rather than assumed missing: importing a
    service entrypoint calls `load_env`, which puts a real key into the session
    and would otherwise make this pass or fail on test ordering alone.
    """
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    with pytest.raises(ValueError, match="VAPID_PRIVATE_KEY"):
        WebPushChannel(store=SubscriptionStore(tmp_path / "push.json"), vapid_private_key="")


def test_it_pushes_to_every_registered_device(store):
    store.add(subscription("https://push.example/a"))
    store.add(subscription("https://push.example/b"))
    recorder = Recorder()
    channel = WebPushChannel(store=store, vapid_private_key=KEY, sender=recorder)

    outcomes = channel.send_to(
        "doris",
        Audience.CAREGIVER,
        PushPayload("Climatise", "It is going to be hot.", Tier.HIGH, "doris"),
    )
    assert [o.status for o in outcomes] == [201, 201]
    assert all(o.delivered for o in outcomes)
    assert len(recorder.calls) == 2


def test_nobody_installed_is_an_empty_result_not_an_error(store):
    channel = WebPushChannel(store=store, vapid_private_key=KEY, sender=Recorder())
    assert (
        channel.send_to("doris", Audience.CAREGIVER, PushPayload("a", "b", Tier.HIGH, "doris"))
        == ()
    )


@pytest.mark.parametrize("status", GONE)
def test_a_dead_subscription_is_pruned_not_retried_forever(store, status):
    store.add(subscription("https://push.example/a"))
    channel = WebPushChannel(store=store, vapid_private_key=KEY, sender=Recorder(status))

    channel.send_to("doris", Audience.CAREGIVER, PushPayload("a", "b", Tier.HIGH, "doris"))
    assert store.for_person("doris", Audience.CAREGIVER) == ()


def test_a_transient_failure_keeps_the_subscription(store):
    """500 is the push service having a bad day, not the device going away."""
    store.add(subscription("https://push.example/a"))
    channel = WebPushChannel(store=store, vapid_private_key=KEY, sender=Recorder(500))

    channel.send_to("doris", Audience.CAREGIVER, PushPayload("a", "b", Tier.HIGH, "doris"))
    assert len(store.for_person("doris", Audience.CAREGIVER)) == 1


# ──────────────────────────────────────────────────────────────── the payload


def test_the_tier_travels_as_its_own_field():
    """The service worker reads it to decide whether to override quieting. Inferring
    it from the wording would put that decision in a regex."""
    encoded = json.loads(PushPayload("t", "b", Tier.SEVERE, "doris").encode())
    assert encoded["tier"] == "Severe"


def test_an_unbound_template_is_refused_rather_than_pushed():
    """Otherwise the notification reads "Hello {{1}}"."""
    template = TemplateLibrary.load().get("heat_alert_person")
    with pytest.raises(ValueError, match="unbound"):
        WebPushChannel.rendered(template)


def test_a_bound_template_renders_its_variables():
    template = TemplateLibrary.load().get("heat_alert_person").bind("Doris", "drink water.")
    rendered = WebPushChannel.rendered(template)
    assert "Doris" in rendered
    assert "{{" not in rendered


# ───────────────────────────────────────────────────────────────────── vapid


def test_the_generated_public_key_is_an_uncompressed_p256_point():
    """65 bytes: a 0x04 tag and two 32-byte coordinates. A short key is accepted by
    the browser and then fails to verify at push time, which is a very quiet bug."""
    import base64

    _, public = generate()
    raw = base64.urlsafe_b64decode(public + "=" * (-len(public) % 4))
    assert len(raw) == 65
    assert raw[0] == 0x04


# ───────────────────────────────────── one bad device must not silence the rest


def test_a_broken_device_does_not_stop_the_others(store):
    """The live bug: an unusable key raised straight out of the loop, so a dead
    phone on someone's record silenced every other device on it — and took the
    whole three-hourly sweep down with it."""
    store.add(subscription("https://push.example/broken"))
    store.add(subscription("https://push.example/fine"))
    sender = Exploding("https://push.example/broken", ValueError("Could not deserialize key data"))
    channel = WebPushChannel(store=store, vapid_private_key=KEY, sender=sender)

    outcomes = channel.send_to(
        "doris", Audience.CAREGIVER, PushPayload("a", "b", Tier.HIGH, "doris")
    )
    assert len(outcomes) == 2
    assert sum(o.delivered for o in outcomes) == 1
    assert len(sender.reached) == 2


def test_an_unusable_key_is_pruned_because_it_cannot_start_working(store):
    store.add(subscription("https://push.example/broken"))
    channel = WebPushChannel(
        store=store,
        vapid_private_key=KEY,
        sender=Exploding("https://push.example/broken", ValueError("bad key")),
    )

    channel.send_to("doris", Audience.CAREGIVER, PushPayload("a", "b", Tier.HIGH, "doris"))
    assert store.for_person("doris", Audience.CAREGIVER) == ()


def test_a_network_blip_keeps_the_device(store):
    """Distinct from a bad key: the phone is fine, the connection was not."""
    store.add(subscription("https://push.example/fine"))
    channel = WebPushChannel(
        store=store,
        vapid_private_key=KEY,
        sender=Exploding("https://push.example/fine", ConnectionError("dns exploded")),
    )

    outcomes = channel.send_to(
        "doris", Audience.CAREGIVER, PushPayload("a", "b", Tier.HIGH, "doris")
    )
    assert outcomes[0].status is None and not outcomes[0].delivered
    assert "dns exploded" in outcomes[0].error
    assert len(store.for_person("doris", Audience.CAREGIVER)) == 1


def test_the_failure_reason_is_carried_not_swallowed(store):
    store.add(subscription("https://push.example/fine"))
    channel = WebPushChannel(
        store=store,
        vapid_private_key=KEY,
        sender=Exploding("https://push.example/fine", ConnectionError("dns exploded")),
    )

    outcomes = channel.send_to(
        "doris", Audience.CAREGIVER, PushPayload("a", "b", Tier.HIGH, "doris")
    )
    assert "dns exploded" in outcomes[0].error


# ──────────────────────────────── a damaged store must not take the service down


@pytest.mark.parametrize(
    "contents",
    [
        "{ this is not json",
        '[{"endpoint": "https://push.example/a"}]',  # every other key missing
        '{"not": "a list"}',
    ],
    ids=["truncated", "missing-keys", "wrong-shape"],
)
def test_an_unparseable_store_loads_empty_rather_than_raising(tmp_path, contents):
    """The API holds one of these as a module-level singleton, so raising here
    meant the service failed to import and every registered phone went dark
    permanently — visible only as alerts that stopped arriving."""
    path = tmp_path / "push.json"
    path.write_text(contents)

    store = SubscriptionStore(path)
    assert store.subscriptions == {}
    assert store.unreadable is not None


def test_a_healthy_store_reports_no_damage(tmp_path):
    store = SubscriptionStore(tmp_path / "push.json")
    store.add(subscription("https://push.example/a"))
    assert SubscriptionStore(tmp_path / "push.json").unreadable is None


def test_writes_are_atomic_so_a_reader_never_sees_a_half_file(tmp_path):
    """A truncate-in-place write is how the corrupt file above gets created."""
    path = tmp_path / "push.json"
    store = SubscriptionStore(path)
    store.add(subscription("https://push.example/a"))

    assert not list(tmp_path.glob("*.tmp")), "temporary file left behind"
    assert SubscriptionStore(path).for_person("doris", Audience.CAREGIVER)
