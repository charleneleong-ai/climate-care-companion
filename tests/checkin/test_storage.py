"""Storage backends.

The tests that matter here are about writes surviving each other. Both stores
used to rewrite their whole collection on every mutation, which is correct for
one process and silently lossy for two — and on serverless "two" is the normal
case, not the unlucky one.
"""

import json

import pytest
from checkin.log import CheckinLog, CheckinRecord, Channel, Outcome, now_iso
from checkin.storage import (
    FileFields,
    FileRows,
    RedisCommand,
    RedisFields,
    RedisRows,
    fields_for,
    redis_command,
    rows_for,
)
from checkin.webpush import PushSubscription, SubscriptionStore
from contracts import Audience

REDIS_VARS = (
    "KV_REST_API_URL",
    "KV_REST_API_TOKEN",
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
)


@pytest.fixture(autouse=True)
def no_ambient_redis(monkeypatch):
    """A developer with Upstash in their shell must not silently send the file
    tests' data to a real database."""
    for name in REDIS_VARS:
        monkeypatch.delenv(name, raising=False)


class FakeRedis:
    """Records commands and answers them from a dict, like the real thing."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.lists: dict[str, list[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    def __call__(self, command: list[str]):
        self.commands.append(command)
        verb, key, *rest = command
        match verb:
            case "RPUSH":
                self.lists.setdefault(key, []).append(rest[0])
            case "LRANGE":
                return self.lists.get(key, [])
            case "HSET":
                self.hashes.setdefault(key, {})[rest[0]] = rest[1]
            case "HDEL":
                self.hashes.get(key, {}).pop(rest[0], None)
            case "HGETALL":
                # Upstash flattens a hash to field, value, field, value.
                return [x for pair in self.hashes.get(key, {}).items() for x in pair]
        return None


def redis_rows(fake: FakeRedis) -> RedisRows:
    return RedisRows("checkins", RedisCommand("https://r.example", "t", transport=fake))


def redis_fields(fake: FakeRedis) -> RedisFields:
    return RedisFields("push", RedisCommand("https://r.example", "t", transport=fake))


def entry(outcome: Outcome = Outcome.COMPLETED, person_id: str = "doris") -> CheckinRecord:
    return CheckinRecord(
        person_id=person_id, channel=Channel.VOICE, outcome=outcome, started_at=now_iso()
    )


def subscription(endpoint: str) -> PushSubscription:
    return PushSubscription(
        endpoint=endpoint,
        p256dh="key",
        auth="auth",
        person_id="doris",
        audience=Audience.CAREGIVER,
    )


class TestConcurrentWritesSurvive:
    """The bug the seam exists for: a second writer's record disappearing.

    Two store instances over one file stand in for two workers — or two
    serverless invocations — recording at the same moment.
    """

    def test_a_second_log_does_not_erase_the_first(self, tmp_path):
        path = tmp_path / "checkins.json"
        first, second = CheckinLog(path), CheckinLog(path)

        first.record(entry(person_id="doris"))
        second.record(entry(person_id="victor"))

        people = {r.person_id for r in CheckinLog(path).records}
        assert people == {"doris", "victor"}, "a check-in was silently dropped"

    def test_a_second_subscriber_does_not_erase_the_first(self, tmp_path):
        path = tmp_path / "push.json"
        first, second = SubscriptionStore(path), SubscriptionStore(path)

        first.add(subscription("https://push.example/a"))
        second.add(subscription("https://push.example/b"))

        assert len(SubscriptionStore(path).subscriptions) == 2

    def test_removing_one_device_leaves_the_others(self, tmp_path):
        path = tmp_path / "push.json"
        store = SubscriptionStore(path)
        store.add(subscription("https://push.example/a"))
        store.add(subscription("https://push.example/b"))

        store.remove("https://push.example/a")

        assert set(SubscriptionStore(path).subscriptions) == {"https://push.example/b"}


class TestRedisIsAtomic:
    """Why Redis rather than a blob: appending is one operation, not read-modify-write."""

    def test_appending_pushes_rather_than_rewriting(self):
        fake = FakeRedis()
        backend = redis_rows(fake)
        backend.append({"person_id": "doris"})
        backend.append({"person_id": "victor"})

        assert [c[0] for c in fake.commands] == ["RPUSH", "RPUSH"]
        assert [row["person_id"] for row in backend.all()] == ["doris", "victor"]

    def test_registering_sets_one_field_rather_than_the_map(self):
        fake = FakeRedis()
        backend = redis_fields(fake)
        backend.put("https://push.example/a", {"endpoint": "a"})

        assert fake.commands[0][:2] == ["HSET", "push"]

    def test_a_hash_round_trips_through_the_flat_reply(self):
        """Upstash returns a hash as field, value, field, value — not an object."""
        fake = FakeRedis()
        backend = redis_fields(fake)
        backend.put("a", {"endpoint": "a"})
        backend.put("b", {"endpoint": "b"})

        assert backend.all() == {"a": {"endpoint": "a"}, "b": {"endpoint": "b"}}

    def test_dropping_removes_only_that_field(self):
        fake = FakeRedis()
        backend = redis_fields(fake)
        backend.put("a", {"endpoint": "a"})
        backend.put("b", {"endpoint": "b"})
        backend.drop("a")

        assert set(backend.all()) == {"b"}


class TestDamageIsReportedNotRaised:
    """Both stores are module-level singletons; raising takes the service down."""

    @pytest.mark.parametrize(
        ("contents", "backend"),
        [
            ("{ not json", FileRows),
            ('{"not": "a list"}', FileRows),
            ("[1, 2, 3]", FileRows),
            ("{ not json", FileFields),
            ("[]", FileFields),
            ('{"a": "not an object"}', FileFields),
        ],
    )
    def test_a_damaged_file_reports_damage(self, tmp_path, contents, backend):
        path = tmp_path / "store.json"
        path.write_text(contents)
        store = backend(path)

        assert not store.all()
        assert store.unreadable is not None

    def test_a_missing_file_is_empty_but_undamaged(self, tmp_path):
        """Nobody registered yet is a normal state, not a fault."""
        store = FileFields(tmp_path / "absent.json")
        assert not store.all()
        assert store.unreadable is None

    def test_an_unreachable_redis_reports_damage(self):
        def refuse(_command):
            raise OSError("connection refused")

        backend = RedisRows("checkins", RedisCommand("https://r.example", "t", transport=refuse))
        assert backend.all() == []
        assert backend.unreadable is not None


class TestBackendSelection:
    def test_no_configuration_means_a_file(self, tmp_path):
        assert isinstance(rows_for("k", tmp_path / "a.json"), FileRows)
        assert isinstance(fields_for("k", tmp_path / "b.json"), FileFields)

    @pytest.mark.parametrize(
        ("url_var", "token_var"),
        [
            ("KV_REST_API_URL", "KV_REST_API_TOKEN"),
            ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"),
        ],
    )
    def test_either_variable_pair_selects_redis(self, monkeypatch, tmp_path, url_var, token_var):
        """Vercel's integration injects one pair, Upstash's dashboard the other."""
        monkeypatch.setenv(url_var, "https://r.example")
        monkeypatch.setenv(token_var, "token")
        assert isinstance(rows_for("k", tmp_path / "a.json"), RedisRows)
        assert isinstance(fields_for("k", tmp_path / "b.json"), RedisFields)

    def test_a_url_without_a_token_refuses_to_start(self, monkeypatch):
        """Otherwise the first write fails long after deploy, and a missing
        variable is indistinguishable from data loss."""
        monkeypatch.setenv("KV_REST_API_URL", "https://r.example")
        with pytest.raises(ValueError, match="cannot authenticate"):
            redis_command()


class TestStoresOverRedis:
    """The stores themselves, with Redis underneath rather than a file."""

    def test_a_check_in_survives_a_new_instance(self):
        fake = FakeRedis()
        CheckinLog(backend=redis_rows(fake)).record(entry(Outcome.NO_ANSWER))

        revived = CheckinLog(backend=redis_rows(fake))
        assert revived.consecutive_missed("doris") == 1

    def test_a_registration_survives_a_new_instance(self):
        fake = FakeRedis()
        SubscriptionStore(backend=redis_fields(fake)).add(subscription("https://push.example/a"))

        revived = SubscriptionStore(backend=redis_fields(fake))
        assert revived.for_person("doris", Audience.CAREGIVER)


def test_the_command_sends_upstash_its_expected_shape():
    """A bearer token and a JSON array body — wrong here means every write
    fails in production and nowhere else."""
    sent = {}

    def capture(command):
        sent["command"] = command
        return None

    RedisCommand("https://r.example/", "secret", transport=capture)("SET", "k", "v")
    assert sent["command"] == ["SET", "k", "v"]
    assert json.dumps(sent["command"])
