# The MIT License (MIT)
#
# Copyright (c) 2015-2021 Rapptz
# Copyright (c) 2021-present Pycord Development
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""A gateway transport reading the events of a gateway proxy from Redis Streams."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, TypedDict, cast

try:
    from redis.asyncio import Redis
    from redis.exceptions import (
        ConnectionError as RedisConnectionError,
        ResponseError,
        TimeoutError as RedisTimeoutError,
    )
except ModuleNotFoundError as exc:
    if exc.name is None or exc.name.split(".")[0] != "redis":
        raise
    raise ImportError(
        "The Redis gateway transport needs redis, install it with: pip install py-cord[redis]"
    ) from exc

from ...backoff import ExponentialBackoff
from ...errors import ClientException
from ...utils import _from_json, _to_json
from ..models import GatewayEvent
from ..transport import GatewayTransport, GatewayTransportFactory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from typing_extensions import Unpack

__all__ = (
    "RedisStreamsConfig",
    "RedisStreamsOptions",
    "RedisStreamsPublisher",
    "RedisStreamsTransport",
)

_log = logging.getLogger(__name__)

_COMMANDS_GROUP = "proxy"
_STATUS_REFRESH = 5.0
_CONNECTION_ERRORS: tuple[type[BaseException], ...] = (
    RedisConnectionError,
    RedisTimeoutError,
    OSError,
)

_FAILED = object()
_Entry = tuple[str, dict[str, str]]
_Execute = Callable[[int, Any], Awaitable[None]]


def _default_consumer() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


@dataclass(frozen=True, slots=True, kw_only=True)
class RedisStreamsConfig:
    """The configuration shared by :class:`RedisStreamsTransport` and :class:`RedisStreamsPublisher`.

    Attributes
    ----------
    url: :class:`str`
        The URL of the Redis server, ignored when ``client`` is given.
    client: Optional[:class:`redis.asyncio.Redis`]
        An existing client to use, it is shared and never closed by the transport.
    prefix: :class:`str`
        The prefix of every key, ``{prefix}:gateway:{shard_id}`` is the event stream of a shard.
    group: :class:`str`
        The consumer group of the workers. Workers of one group share the events,
        each one is delivered to a single worker.
    consumer: :class:`str`
        The name of this consumer in the group, ``{hostname}-{pid}`` by default.
    block_ms: :class:`int`
        How long a read waits for new entries, in milliseconds.
    batch_size: :class:`int`
        The maximum number of entries read at once.
    maxlen: :class:`int`
        The approximate number of entries kept in a stream, older entries are trimmed.
    claim_idle_ms: :class:`int`
        A delivered entry that was not acknowledged for this long, in milliseconds, is
        taken over by a consumer of the group.
    """

    url: str = "redis://localhost:6379/0"
    client: Redis | None = None
    prefix: str = "pycord"
    group: str = "pycord"
    consumer: str = field(default_factory=_default_consumer)
    block_ms: int = 1000
    batch_size: int = 100
    maxlen: int = 10000
    claim_idle_ms: int = 30000

    def __post_init__(self) -> None:
        if not self.prefix:
            raise ValueError("prefix cannot be empty")
        if not self.group:
            raise ValueError("group cannot be empty")
        if not self.consumer:
            raise ValueError("consumer cannot be empty")
        if self.block_ms < 1:
            raise ValueError("block_ms must be at least 1")
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if self.maxlen < 1:
            raise ValueError("maxlen must be at least 1")
        if self.claim_idle_ms < 0:
            raise ValueError("claim_idle_ms cannot be negative")

    def stream(self, shard_id: int | None) -> str:
        """The key of the event stream of a shard."""
        return f"{self.prefix}:gateway:{_shard(shard_id)}"

    def commands(self, shard_id: int | None) -> str:
        """The key of the command stream of a shard."""
        return f"{self.prefix}:gateway:commands:{_shard(shard_id)}"

    def session(self, shard_id: int | None) -> str:
        """The key of the session hash of a shard."""
        return f"{self.prefix}:gateway:session:{_shard(shard_id)}"


class RedisStreamsOptions(TypedDict, total=False):
    """The options of :class:`RedisStreamsConfig`."""

    url: str
    client: Redis | None
    prefix: str
    group: str
    consumer: str
    block_ms: int
    batch_size: int
    maxlen: int
    claim_idle_ms: int


def _shard(shard_id: int | None) -> int:
    return 0 if shard_id is None else shard_id


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _entries(raw: Any) -> list[_Entry]:
    return [
        (_text(entry_id), {_text(k): _text(v) for k, v in fields.items()})
        for entry_id, fields in cast("list[tuple[Any, Any]]", raw)
        if fields
    ]


def _stream_replies(reply: Any) -> list[Any]:
    if not reply:
        return []
    streams = cast(
        "Any", reply.values() if isinstance(reply, dict) else (r[1] for r in reply)
    )
    batches: list[Any] = []
    for items in streams:
        if items and isinstance(items[0], list) and _is_batch(items[0]):
            batches.extend(items)
        else:
            batches.append(items)
    return batches


def _is_batch(item: list[Any]) -> bool:
    return not item or isinstance(item[0], (list, tuple))


def _open(config: RedisStreamsConfig) -> tuple[Any, bool]:
    if config.client is not None:
        return config.client, False
    return cast("Any", Redis).from_url(config.url), True


async def _close(client: Any, owned: bool) -> None:
    if owned:
        await client.aclose()


class _GroupReader:
    def __init__(
        self, client: Any, stream: str, group: str, config: RedisStreamsConfig
    ) -> None:
        self._client: Any = client
        self._stream: str = stream
        self._group: str = group
        self._consumer: str = config.consumer
        self._block_ms: int = config.block_ms
        self._batch_size: int = config.batch_size
        self._claim_idle_ms: int = config.claim_idle_ms
        self._next_recovery: float = 0.0

    async def ensure_group(self, start_id: str) -> None:
        try:
            await self._client.xgroup_create(
                self._stream, self._group, id=start_id, mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def recover(self) -> list[_Entry]:
        entries: list[_Entry] = []
        cursor = "0-0"
        while True:
            reply = await self._client.xautoclaim(
                self._stream,
                self._group,
                self._consumer,
                min_idle_time=self._claim_idle_ms,
                start_id=cursor,
                count=self._batch_size,
            )
            entries.extend(_entries(reply[1]))
            cursor = _text(reply[0])
            if cursor in ("0-0", "0"):
                return entries

    async def next(self) -> list[_Entry]:
        now = asyncio.get_running_loop().time()
        if now >= self._next_recovery:
            self._next_recovery = now + max(self._claim_idle_ms, self._block_ms) / 1000
            recovered = await self.recover()
            if recovered:
                return recovered
        reply = await self._client.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=self._batch_size,
            block=self._block_ms,
        )
        await asyncio.sleep(0)
        entries: list[_Entry] = []
        for items in _stream_replies(reply):
            entries.extend(_entries(items))
        return entries

    async def ack(self, entry_id: str) -> None:
        try:
            await self._client.xack(self._stream, self._group, entry_id)
        except _CONNECTION_ERRORS:
            _log.warning(
                "Could not acknowledge %s of %s, it will be delivered again.",
                entry_id,
                self._stream,
            )

    async def handle_error(
        self,
        exc: BaseException,
        *,
        reconnect: bool,
        backoff: ExponentialBackoff[bool],
        start_id: str,
    ) -> None:
        if isinstance(exc, ResponseError) and "NOGROUP" in str(exc):
            await self.ensure_group(start_id)
            return
        if not reconnect or not isinstance(exc, _CONNECTION_ERRORS):
            raise exc
        retry = backoff.delay()
        _log.error(
            "Lost the connection to Redis, trying again in %.2fs", retry, exc_info=exc
        )
        await asyncio.sleep(retry)
        self._next_recovery = 0.0


class RedisStreamsTransport(GatewayTransport):
    """A transport reading the events of a shard from a Redis stream fed by a gateway proxy.

    Events are read with ``XREADGROUP`` and acknowledged once the client took them,
    entries a crashed consumer did not acknowledge are taken over by the others.
    Commands are appended to the command stream of the shard, the proxy executes them.
    Use :meth:`factory` to plug it in a client::

        bot = discord.AutoShardedBot(
            gateway=RedisStreamsTransport.factory(
                url="redis://localhost", group="bots"
            ),
            shard_count=8,
        )

    Workers share the events of a shard, so they should share their cache too.

    Parameters
    ----------
    config
        The Redis configuration.
    shard_id
        The shard to read, ``None`` for the shard ``0``.
    shard_count
        The total number of shards, defined by the gateway proxy.

    Raises
    ------
    ClientException
        ``shard_count`` is missing.
    """

    def __init__(
        self,
        config: RedisStreamsConfig,
        shard_id: int | None = None,
        shard_count: int | None = None,
    ) -> None:
        if shard_count is None:
            raise ClientException(
                "RedisStreamsTransport needs the shard_count of the gateway proxy, "
                "pass shard_count to the client."
            )
        super().__init__(shard_id, shard_count)
        self.config: RedisStreamsConfig = config
        self._client: Any = None
        self._owned: bool = False
        self._reader: _GroupReader | None = None
        self._closed: bool = True
        self._idle: asyncio.Event = asyncio.Event()
        self._idle.set()
        self._latency: float = float("inf")
        self._ratelimited: bool = False
        self._next_status: float = 0.0
        self._ready: GatewayEvent | None = None
        self._session_id: str | None = None

    @classmethod
    def factory(
        cls,
        config: RedisStreamsConfig | None = None,
        /,
        **options: Unpack[RedisStreamsOptions],
    ) -> GatewayTransportFactory:
        """Create the ``gateway`` factory of a client.

        Parameters
        ----------
        config
            The configuration, defaults are used for what ``options`` does not set.
        **options
            The fields of :class:`RedisStreamsConfig` to set or override.
        """
        resolved = (
            RedisStreamsConfig(**options)
            if config is None
            else replace(config, **options)
        )

        def create(shard_id: int | None, shard_count: int | None) -> GatewayTransport:
            return cls(resolved, shard_id, shard_count)

        return create

    @property
    def latency(self) -> float:
        """The heartbeat latency of the proxy, ``inf`` before the first one and ``nan`` when not connected."""
        return float("nan") if self._closed else self._latency

    def is_ratelimited(self) -> bool:
        """Whether the proxy cannot send a command right now."""
        return not self._closed and self._ratelimited

    def is_closed(self) -> bool:
        """Whether the transport is closed."""
        return self._closed

    async def connect(self) -> None:
        """Create the consumer group, then read the session of the proxy to announce its ``READY``."""
        if not self._closed:
            return
        self._client, self._owned = _open(self.config)
        self._reader = reader = _GroupReader(
            self._client,
            self.config.stream(self.shard_id),
            self.config.group,
            self.config,
        )
        try:
            await reader.ensure_group("$")
            self._ready = await self._read_session()
        except BaseException:
            await _close(self._client, self._owned)
            self._client = None
            raise
        self._session_id = (
            None if self._ready is None else self._ready.d.get("session_id")
        )
        self._closed = False
        self._next_status = asyncio.get_running_loop().time() + _STATUS_REFRESH

    async def events(self) -> AsyncIterator[GatewayEvent]:
        """Iterate over the events of the proxy, starting with its ``READY`` when it already has a session."""
        reader = self._reader
        if reader is None or self.is_closed():
            return
        backoff: ExponentialBackoff[bool] = ExponentialBackoff()
        ready, self._ready = self._ready, None
        if ready is not None:
            yield ready
        while not self.is_closed():
            try:
                entries = await self._read(reader)
            except Exception as exc:
                if self.is_closed():
                    break
                if isinstance(exc, _CONNECTION_ERRORS):
                    self.on_disconnect()
                await reader.handle_error(
                    exc, reconnect=self.reconnect, backoff=backoff, start_id="$"
                )
                continue
            for entry_id, fields in entries:
                if self.is_closed():
                    break
                event = self._decode(fields)
                if event is not None:
                    yield event
                await reader.ack(entry_id)

    async def _read(self, reader: _GroupReader) -> list[_Entry]:
        self._idle.clear()
        try:
            await self._refresh_status()
            return await reader.next()
        finally:
            self._idle.set()

    async def send(self, op: int, d: Any) -> None:
        """Append a command to the command stream of the shard."""
        client = self._client
        if self._closed or client is None:
            raise ClientException("The gateway transport is not connected.")
        await client.xadd(
            self.config.commands(self.shard_id),
            {"op": str(int(op)), "d": _to_json(d)},
            maxlen=self.config.maxlen,
            approximate=True,
        )

    async def close(self, code: int = 1000) -> None:
        """Stop reading, the iteration of :meth:`events` ends."""
        del code
        self._closed = True
        try:
            await asyncio.wait_for(self._idle.wait(), self.config.block_ms / 1000 + 5)
        except asyncio.TimeoutError:
            _log.warning("The reader of shard %s did not stop in time.", self.shard_id)
        client, self._client = self._client, None
        self._reader = None
        if client is not None:
            await _close(client, self._owned)

    def _decode(self, fields: dict[str, str]) -> GatewayEvent | None:
        try:
            t = fields["t"]
            s = fields.get("s")
            d = _from_json(fields["d"])
        except (KeyError, ValueError):
            _log.warning("Dropping a malformed entry of shard %s.", self.shard_id)
            return None
        if t == "READY" and isinstance(d, dict):
            session_id = cast("dict[str, Any]", d).get("session_id")
            if session_id is not None and session_id == self._session_id:
                return None
        return GatewayEvent(
            op=0, t=t, s=int(s) if s else None, d=d, shard_id=self.shard_id
        )

    async def _read_session(self) -> GatewayEvent | None:
        raw = await self._client.hgetall(self.config.session(self.shard_id))
        session = {_text(k): _text(v) for k, v in raw.items()}
        self._apply_status(session)
        ready = session.get("ready")
        if ready is None:
            return None
        s = session.get("s")
        return GatewayEvent(
            op=0,
            t="READY",
            s=int(s) if s else None,
            d=_from_json(ready),
            shard_id=self.shard_id,
        )

    def _apply_status(self, session: dict[str, str]) -> None:
        latency = session.get("latency")
        if latency is not None:
            self._latency = float(latency)
        self._ratelimited = session.get("ratelimited") == "1"

    async def _refresh_status(self) -> None:
        now = asyncio.get_running_loop().time()
        if now < self._next_status:
            return
        self._next_status = now + _STATUS_REFRESH
        values = await self._client.hmget(
            self.config.session(self.shard_id), "latency", "ratelimited"
        )
        latency, ratelimited = (None if v is None else _text(v) for v in values)
        status: dict[str, str] = {}
        if latency is not None:
            status["latency"] = latency
        if ratelimited is not None:
            status["ratelimited"] = ratelimited
        self._apply_status(status)


class RedisStreamsPublisher:
    """Publishes the events of a gateway to Redis Streams and reads the commands of the workers.

    Used by the gateway proxy. Every event is appended to ``{prefix}:gateway:{shard_id}``,
    ``READY`` also updates the session hash ``{prefix}:gateway:session:{shard_id}`` that
    workers read when they start. Commands come from ``{prefix}:gateway:commands:{shard_id}``.

    Parameters
    ----------
    config
        The Redis configuration.
    """

    def __init__(self, config: RedisStreamsConfig) -> None:
        self.config: RedisStreamsConfig = config
        self._client: Any = None
        self._owned: bool = False
        self._stopping: bool = False
        self._backoff: ExponentialBackoff[bool] = ExponentialBackoff()

    async def start(self) -> None:
        """Open the connection to Redis."""
        if self._client is None:
            self._client, self._owned = _open(self.config)
        self._stopping = False

    async def close(self) -> None:
        """Stop the command loops and close the connection."""
        self._stopping = True
        client, self._client = self._client, None
        if client is not None:
            await _close(client, self._owned)

    def stop(self) -> None:
        """Ask the command loops to return."""
        self._stopping = True

    def _is_stopping(self) -> bool:
        return self._stopping

    async def publish(self, event: GatewayEvent) -> str:
        """Append an event to the stream of its shard and return the ID of the entry.

        The write is retried until it succeeds as long as the publisher is open.
        """
        client = self._require()
        d = event.d
        if event.t == "READY":
            session: dict[str, str] = {"ready": _to_json(d), "s": str(event.s or "")}
            if isinstance(d, dict):
                session["session_id"] = str(cast("dict[str, Any]", d).get("session_id"))
            await self._retry(
                lambda: client.hset(
                    self.config.session(event.shard_id), mapping=session
                )
            )
        fields = {
            "t": event.t or "",
            "s": "" if event.s is None else str(event.s),
            "d": _to_json(d),
        }
        entry_id = await self._retry(
            lambda: client.xadd(
                self.config.stream(event.shard_id),
                fields,
                maxlen=self.config.maxlen,
                approximate=True,
            )
        )
        return _text(entry_id)

    async def publish_status(
        self, shard_id: int | None, *, latency: float, ratelimited: bool
    ) -> None:
        """Store the latency and rate limit state of a shard in its session hash."""
        client = self._require()
        await client.hset(
            self.config.session(shard_id),
            mapping={
                "latency": repr(latency),
                "ratelimited": "1" if ratelimited else "0",
            },
        )

    async def consume_commands(self, shard_id: int | None, execute: _Execute) -> None:
        """Execute the commands of the workers for a shard until the publisher is closed.

        A command is acknowledged once ``execute(op, d)`` returned or raised, a failing
        command is logged and dropped.
        """
        client = self._require()
        reader = _GroupReader(
            client, self.config.commands(shard_id), _COMMANDS_GROUP, self.config
        )
        backoff: ExponentialBackoff[bool] = ExponentialBackoff()
        await reader.ensure_group("0")
        while not self._is_stopping():
            try:
                entries = await reader.next()
            except Exception as exc:
                if self._is_stopping():
                    break
                await reader.handle_error(
                    exc, reconnect=True, backoff=backoff, start_id="0"
                )
                continue
            for entry_id, fields in entries:
                try:
                    await execute(int(fields["op"]), _from_json(fields["d"]))
                except Exception:
                    _log.exception("Could not execute a command of shard %s.", shard_id)
                await reader.ack(entry_id)

    def _require(self) -> Any:
        if self._client is None:
            raise ClientException("The publisher is not started.")
        return self._client

    async def _retry(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        while True:
            outcome = await self._attempt(operation)
            if outcome is not _FAILED:
                return outcome

    async def _attempt(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        try:
            return await operation()
        except _CONNECTION_ERRORS as exc:
            if self._stopping or self._client is None:
                raise
            retry = self._backoff.delay()
            _log.error(
                "Lost the connection to Redis, trying again in %.2fs",
                retry,
                exc_info=exc,
            )
            await asyncio.sleep(retry)
            return _FAILED
