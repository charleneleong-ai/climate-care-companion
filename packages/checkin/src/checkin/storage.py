"""Where a check-in record and a push subscription actually live.

Both stores began as a JSON file, which is right for one process and wrong for
several. Each read the whole collection into memory, mutated it, and wrote the
whole thing back — so two writers at once keep only one of the two writes. On a
single container that races rarely. On serverless, where the platform runs as
many copies of a function as it likes, it is the ordinary case, and the write
that gets lost is a check-in nobody knows was answered.

So the seam is at the mutation rather than at the file. `append`, `put` and
`drop` are each one operation the backend performs atomically: Redis does that
natively, and the file backend takes a lock and re-reads first, which is as
atomic as one process needs.

Reads are still served from the copy the store loaded at construction. That is
deliberate and it is why this is a small change: a serverless invocation builds
a fresh store and therefore sees current data, and a long-running container is
the only writer to its own file. What neither can now do is silently drop the
other's write.
"""

import json
import os
import urllib.request
from http.client import HTTPException
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

UNREACHABLE = (OSError, HTTPException, ValueError, TypeError)
"""Everything a read over the network can fail with, treated as damage to
report rather than an exception to raise.

Deliberately wider than `URLError`: a timeout arrives as `TimeoutError` and a
certificate problem as `SSLError`, both plain `OSError`s that would otherwise
escape — and these stores are held as module-level singletons, so an escape
during import stops the whole service rather than one read."""

REDIS_URL_VARS = ("KV_REST_API_URL", "UPSTASH_REDIS_REST_URL")
REDIS_TOKEN_VARS = ("KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_TOKEN")
"""Vercel's Upstash integration injects the `KV_` pair; Upstash's own dashboard
gives you the `UPSTASH_` pair. Same service, two names, so accept both rather
than make the deployment depend on which route provisioned it."""


class Rows(Protocol):
    """An ordered, append-only collection. The check-in log."""

    unreadable: str | None

    def all(self) -> list[dict[str, Any]]: ...

    def append(self, row: dict[str, Any]) -> None: ...


class Fields(Protocol):
    """A collection addressed by a stable key. Push subscriptions, by endpoint."""

    unreadable: str | None

    def all(self) -> dict[str, dict[str, Any]]: ...

    def put(self, key: str, row: dict[str, Any]) -> None: ...

    def drop(self, key: str) -> None: ...


class JsonFile:
    """Never-raising read, atomic write. Shared by both file backends.

    `read` never raises because the API and the voice service each hold a store
    at module level: a truncated file used to mean the service failed to import,
    and every phone that had registered went dark with no signal to anyone
    except alerts that stopped arriving.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = Lock()
        self.unreadable: str | None = None

    def read(self) -> Any:
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text() or "null")
        except ValueError as exc:
            self.unreadable = f"{type(exc).__name__}: {exc}"
            return None
        self.unreadable = None
        return value

    def write(self, value: Any) -> None:
        """`write_text` truncates in place, so an interrupted write leaves
        invalid JSON where `read` has to cope with it. Render to a temporary and
        rename, which the filesystem makes atomic."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(value, indent=2))
        temporary.replace(self.path)


class FileRows:
    def __init__(self, path: Path) -> None:
        self.file = JsonFile(path)

    @property
    def unreadable(self) -> str | None:
        return self.file.unreadable

    def all(self) -> list[dict[str, Any]]:
        value = self.file.read()
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            # Parsed as JSON but is not what this store writes. Reported as
            # damage rather than silently treated as empty, because "nobody has
            # checked in" and "the log is unreadable" call for opposite responses.
            self.file.unreadable = f"expected a list of objects, found {type(value).__name__}"
            return []
        return value

    def append(self, row: dict[str, Any]) -> None:
        # Re-reads inside the lock rather than trusting a cached copy, so a
        # second process appending between our load and our write is not erased.
        with self.file.lock:
            self.file.write([*self.all(), row])


class FileFields:
    def __init__(self, path: Path) -> None:
        self.file = JsonFile(path)

    @property
    def unreadable(self) -> str | None:
        return self.file.unreadable

    def all(self) -> dict[str, dict[str, Any]]:
        value = self.file.read()
        if value is None:
            return {}
        if not isinstance(value, dict) or not all(isinstance(r, dict) for r in value.values()):
            self.file.unreadable = f"expected an object of objects, found {type(value).__name__}"
            return {}
        return value

    def put(self, key: str, row: dict[str, Any]) -> None:
        with self.file.lock:
            self.file.write({**self.all(), key: row})

    def drop(self, key: str) -> None:
        with self.file.lock:
            remaining = self.all()
            if remaining.pop(key, None) is not None:
                self.file.write(remaining)


class RedisCommand:
    """Upstash's REST API — one HTTPS request per command.

    REST rather than the Redis wire protocol because a serverless function has
    nowhere to keep a connection pool: it is created and destroyed per request,
    and a pool that never gets reused is pure cost. Plain HTTPS also survives
    the platform's egress rules without special configuration.
    """

    def __init__(self, base: str, token: str, transport: Any = None) -> None:
        self.base = base.rstrip("/")
        self.token = token
        # Injected by tests so no network call is made, matching TwilioChannel.
        self.transport = transport or self.over_https

    def __call__(self, *command: str) -> Any:
        return self.transport(list(command))

    def over_https(self, command: list[str]) -> Any:
        request = urllib.request.Request(
            self.base,
            data=json.dumps(command).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read()).get("result")


class RedisRows:
    """The check-in log as a Redis list.

    `RPUSH` is why this exists: appending is one atomic operation, so two
    functions recording a check-in at the same moment both survive. The file
    backend can only approximate that within one process.
    """

    def __init__(self, key: str, command: RedisCommand) -> None:
        self.key = key
        self.command = command
        self.unreadable: str | None = None

    def all(self) -> list[dict[str, Any]]:
        try:
            raw = self.command("LRANGE", self.key, "0", "-1") or []
            rows = [json.loads(item) for item in raw]
        except UNREACHABLE as exc:
            self.unreadable = f"{type(exc).__name__}: {exc}"
            return []
        self.unreadable = None
        return [row for row in rows if isinstance(row, dict)]

    def append(self, row: dict[str, Any]) -> None:
        self.command("RPUSH", self.key, json.dumps(row))


class RedisFields:
    """Push subscriptions as a Redis hash, one field per endpoint.

    A hash rather than a serialised blob so registering a phone touches only
    that phone's field — otherwise two people installing the app at the same
    moment would each write back a copy of the map that omits the other.
    """

    def __init__(self, key: str, command: RedisCommand) -> None:
        self.key = key
        self.command = command
        self.unreadable: str | None = None

    def all(self) -> dict[str, dict[str, Any]]:
        try:
            flat = self.command("HGETALL", self.key) or []
            # Upstash returns a hash as a flat field, value, field, value list.
            pairs = zip(flat[0::2], flat[1::2], strict=True)
            rows = {key: json.loads(value) for key, value in pairs}
        except UNREACHABLE as exc:
            self.unreadable = f"{type(exc).__name__}: {exc}"
            return {}
        self.unreadable = None
        return {key: row for key, row in rows.items() if isinstance(row, dict)}

    def put(self, key: str, row: dict[str, Any]) -> None:
        self.command("HSET", self.key, key, json.dumps(row))

    def drop(self, key: str) -> None:
        self.command("HDEL", self.key, key)


def first_set(names: tuple[str, ...]) -> str | None:
    for name in names:
        if value := os.environ.get(name):
            return value
    return None


def redis_command() -> RedisCommand | None:
    """None when no Redis is configured, which is the local default.

    Both halves are required: a URL without a token is a misconfiguration that
    would otherwise fail on the first write, long after deploy, and look like
    data loss rather than a missing variable.
    """
    base, token = first_set(REDIS_URL_VARS), first_set(REDIS_TOKEN_VARS)
    if not base:
        return None
    if not token:
        raise ValueError(
            f"{REDIS_URL_VARS[0]} is set but no token is. Set one of "
            f"{' or '.join(REDIS_TOKEN_VARS)} — a URL alone cannot authenticate."
        )
    return RedisCommand(base, token)


def rows_for(key: str, path: Path) -> Rows:
    command = redis_command()
    return RedisRows(key, command) if command else FileRows(path)


def fields_for(key: str, path: Path) -> Fields:
    command = redis_command()
    return RedisFields(key, command) if command else FileFields(path)
