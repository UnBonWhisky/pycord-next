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

"""Tests of the Redis Streams gateway transport, publisher and proxy."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
from typing import TYPE_CHECKING, Any, cast

import fakeredis
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError, ResponseError

import discord
from discord import __main__ as cli
from discord.gateway import GatewayEvent, GatewayTransport
from discord.gateway.brokers import (
    RedisStreamsConfig,
    RedisStreamsPublisher,
    RedisStreamsTransport,
    redis as brokers_redis,
)
from discord.gateway.proxy import GatewayProxy
from discord.http import HTTPClient
from tests.gateway.conftest import REDIS_READY, USER, eventually, next_event

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    from discord.gateway import GatewayTransportFactory


def make_config(server: fakeredis.FakeServer, **options: Any) -> RedisStreamsConfig:
    options.setdefault("block_ms", 20)
    options.setdefault("claim_idle_ms", 50)
    return RedisStreamsConfig(client=fakeredis.FakeAsyncRedis(server=server), **options)


def make_resp3_config(
    server: fakeredis.FakeServer, **options: Any
) -> RedisStreamsConfig:
    options.setdefault("block_ms", 20)
    options.setdefault("claim_idle_ms", 50)
    return RedisStreamsConfig(
        client=fakeredis.FakeAsyncRedis(server=server, protocol=3), **options
    )


def redis_of(config: RedisStreamsConfig) -> Any:
    assert config.client is not None
    return config.client


async def close_events(events: AsyncIterator[GatewayEvent]) -> None:
    await cast("AsyncGenerator[GatewayEvent, None]", events).aclose()


def pull(events: AsyncIterator[GatewayEvent]) -> asyncio.Task[GatewayEvent]:
    async def one() -> GatewayEvent:
        return await anext(events)

    return asyncio.create_task(one())


def message(index: int, shard_id: int = 0) -> GatewayEvent:
    return GatewayEvent(0, "TEST", index + 1, {"index": index}, shard_id)


async def pending(config: RedisStreamsConfig, shard_id: int = 0) -> int:
    summary = await redis_of(config).xpending(config.stream(shard_id), config.group)
    return int(summary["pending"])


async def collect(transport: GatewayTransport, into: list[int]) -> None:
    async for event in transport.events():
        if event.t == "TEST":
            into.extend((event.d["index"],))


@pytest.fixture
def server() -> fakeredis.FakeServer:  # type: ignore[override]
    return fakeredis.FakeServer()


@pytest.fixture
async def publisher(
    server: fakeredis.FakeServer,
) -> AsyncIterator[RedisStreamsPublisher]:
    publisher = RedisStreamsPublisher(make_config(server))
    await publisher.start()
    yield publisher
    await publisher.close()


async def test_config_defaults_and_keys() -> None:
    config = RedisStreamsConfig()

    assert config.url == "redis://localhost:6379/0"
    assert config.prefix == "pycord"
    assert config.group == "pycord"
    assert config.maxlen == 10000
    assert config.consumer
    assert config.stream(3) == "pycord:gateway:3"
    assert config.stream(None) == "pycord:gateway:0"
    assert config.commands(3) == "pycord:gateway:commands:3"
    assert config.session(3) == "pycord:gateway:session:3"


@pytest.mark.parametrize(
    "options",
    [
        {"prefix": ""},
        {"group": ""},
        {"consumer": ""},
        {"block_ms": 0},
        {"batch_size": 0},
        {"maxlen": 0},
        {"claim_idle_ms": -1},
    ],
)
def test_config_rejects_invalid_values(options: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"cannot be empty|at least|negative"):
        RedisStreamsConfig(**options)


def test_config_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        RedisStreamsConfig("redis://localhost")  # type: ignore[misc]


def test_factory_merges_a_config_and_options() -> None:
    base = RedisStreamsConfig(prefix="a", group="g")
    factory = RedisStreamsTransport.factory(base, group="other", maxlen=5)

    transport = factory(2, 4)

    assert isinstance(transport, RedisStreamsTransport)
    assert transport.config.prefix == "a"
    assert transport.config.group == "other"
    assert transport.config.maxlen == 5
    assert (transport.shard_id, transport.shard_count) == (2, 4)


def test_factory_without_shard_count_explains_the_problem() -> None:
    factory = RedisStreamsTransport.factory(url="redis://localhost")

    with pytest.raises(discord.ClientException, match="shard_count"):
        factory(None, None)


async def test_client_without_shard_count_fails_to_start(
    server: fakeredis.FakeServer,
) -> None:
    client = discord.Client(
        gateway=RedisStreamsTransport.factory(make_config(server)),
        intents=discord.Intents.none(),
    )

    manager = await client._start_gateway(reconnect=False)

    with pytest.raises(discord.ClientException, match="shard_count"):
        await anext(manager.events())
    await client.close()


async def test_missing_redis_package_points_to_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in [n for n in sys.modules if n.startswith("redis.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "redis", None)
    monkeypatch.delitem(sys.modules, "discord.gateway.brokers.redis")

    with pytest.raises(ImportError, match=r"pip install py-cord\[redis\]"):
        importlib.import_module("discord.gateway.brokers.redis")


async def test_events_flow_from_the_publisher_to_the_consumer(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    transport = RedisStreamsTransport(make_config(server), 0, 1)
    await transport.connect()
    events = transport.events()

    await publisher.publish(
        GatewayEvent(0, "MESSAGE_CREATE", 7, {"id": "1", "nested": [1, {"a": None}]}, 0)
    )

    event = await next_event(events)
    assert event == GatewayEvent(
        0, "MESSAGE_CREATE", 7, {"id": "1", "nested": [1, {"a": None}]}, 0
    )
    await transport.close()


async def test_event_without_sequence_keeps_none(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    transport = RedisStreamsTransport(make_config(server), 0, 1)
    await transport.connect()
    events = transport.events()

    await publisher.publish(GatewayEvent(0, "X", None, {}, 0))

    assert (await next_event(events)).s is None
    await transport.close()


async def test_each_shard_has_its_own_ordered_stream(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    transports = [RedisStreamsTransport(make_config(server), i, 2) for i in range(2)]
    received: list[list[int]] = [[], []]
    for transport in transports:
        await transport.connect()
    tasks = [
        asyncio.create_task(collect(transport, received[i]))
        for i, transport in enumerate(transports)
    ]

    for index in range(20):
        await publisher.publish(message(index, shard_id=index % 2))

    await eventually(lambda: sum(map(len, received)) == 20)
    assert received[0] == list(range(0, 20, 2))
    assert received[1] == list(range(1, 20, 2))
    for transport in transports:
        await transport.close()
    await asyncio.gather(*tasks)


async def test_consumer_announces_the_ready_of_the_session(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    await publisher.publish(GatewayEvent(0, "READY", 1, REDIS_READY, 0))
    await publisher.publish(message(0))
    transport = RedisStreamsTransport(make_config(server), 0, 1)
    await transport.connect()
    events = transport.events()

    ready = await next_event(events)

    assert ready.t == "READY"
    assert ready.d["session_id"] == "redis-session"
    assert ready.shard_id == 0
    await publisher.publish(message(1))
    assert (await next_event(events)).d["index"] == 1
    await transport.close()


async def test_ready_of_a_known_session_is_not_delivered_twice(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    config = make_config(server)
    first = RedisStreamsTransport(config, 0, 1)
    await first.connect()
    await publisher.publish(GatewayEvent(0, "READY", 1, REDIS_READY, 0))
    events = first.events()
    await next_event(events)
    await close_events(events)
    await first.close()
    await asyncio.sleep(0.1)

    second = RedisStreamsTransport(make_config(server), 0, 1)
    await second.connect()
    await publisher.publish(message(0))
    events = second.events()

    assert (await next_event(events)).t == "READY"
    assert (await next_event(events)).t == "TEST"
    await second.close()


async def test_new_session_ready_reaches_a_running_consumer(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    await publisher.publish(GatewayEvent(0, "READY", 1, REDIS_READY, 0))
    transport = RedisStreamsTransport(make_config(server), 0, 1)
    await transport.connect()
    events = transport.events()
    await next_event(events)

    await publisher.publish(
        GatewayEvent(0, "READY", 1, {**REDIS_READY, "session_id": "second"}, 0)
    )

    ready = await next_event(events)
    assert ready.t == "READY"
    assert ready.d["session_id"] == "second"
    await transport.close()


async def test_events_are_acknowledged_after_they_are_handed_over(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    config = make_config(server)
    transport = RedisStreamsTransport(config, 0, 1)
    await transport.connect()
    events = transport.events()
    for index in range(3):
        await publisher.publish(message(index))

    await next_event(events)
    assert await pending(config) == 3
    await next_event(events)
    assert await pending(config) == 2
    await next_event(events)
    assert await pending(config) == 1
    task = pull(events)
    await asyncio.sleep(0.05)
    assert await pending(config) == 0
    task.cancel()
    await transport.close()


async def test_unacknowledged_events_are_recovered_after_a_crash(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    crashed = RedisStreamsTransport(make_config(server, consumer="crashed"), 0, 1)
    await crashed.connect()
    events = crashed.events()
    for index in range(3):
        await publisher.publish(message(index))
    assert (await next_event(events)).d["index"] == 0
    await close_events(events)
    await crashed.close()
    await asyncio.sleep(0.1)

    config = make_config(server, consumer="replacement")
    replacement = RedisStreamsTransport(config, 0, 1)
    await replacement.connect()
    events = replacement.events()

    indexes = [(await next_event(events)).d["index"] for _ in range(3)]

    assert indexes == [0, 1, 2]
    await replacement.close()


async def test_resp3_clients_read_and_acknowledge_events(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    config = make_resp3_config(server)
    transport = RedisStreamsTransport(config, 0, 1)
    await transport.connect()
    events = transport.events()
    for index in range(3):
        await publisher.publish(message(index))

    indexes = [(await next_event(events)).d["index"] for _ in range(3)]
    task = pull(events)
    await asyncio.sleep(0.05)

    assert indexes == [0, 1, 2]
    assert await pending(config) == 0
    task.cancel()
    await transport.close()


async def test_resp3_clients_recover_unacknowledged_events(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    crashed = RedisStreamsTransport(make_resp3_config(server, consumer="crashed"), 0, 1)
    await crashed.connect()
    events = crashed.events()
    for index in range(3):
        await publisher.publish(message(index))
    assert (await next_event(events)).d["index"] == 0
    await close_events(events)
    await crashed.close()
    await asyncio.sleep(0.1)

    replacement = RedisStreamsTransport(
        make_resp3_config(server, consumer="replacement"), 0, 1
    )
    await replacement.connect()
    events = replacement.events()

    indexes = [(await next_event(events)).d["index"] for _ in range(3)]

    assert indexes == [0, 1, 2]
    await replacement.close()


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (None, []),
        ({}, []),
        ([], []),
        ([[b"s", [(b"1-0", {b"a": b"1"})]]], [("1-0", {"a": "1"})]),
        ({b"s": [(b"1-0", {b"a": b"1"})]}, [("1-0", {"a": "1"})]),
        ({b"s": [[(b"1-0", {b"a": b"1"})]]}, [("1-0", {"a": "1"})]),
        ({"s": [[]]}, []),
    ],
)
def test_stream_replies_of_both_protocols(
    reply: Any, expected: list[tuple[str, dict[str, str]]]
) -> None:
    entries = [
        entry
        for items in brokers_redis._stream_replies(reply)
        for entry in brokers_redis._entries(items)
    ]

    assert entries == expected


async def test_recovery_waits_for_the_idle_time(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    crashed = RedisStreamsTransport(make_config(server, consumer="crashed"), 0, 1)
    await crashed.connect()
    events = crashed.events()
    await publisher.publish(message(0))
    await next_event(events)
    await close_events(events)
    await crashed.close()

    replacement = RedisStreamsTransport(
        make_config(server, consumer="other", claim_idle_ms=60000), 0, 1
    )
    await replacement.connect()
    assert replacement._reader is not None

    assert await replacement._reader.recover() == []
    await replacement.close()


async def test_two_consumers_of_a_group_share_the_events(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    first = RedisStreamsTransport(make_config(server, consumer="a"), 0, 1)
    second = RedisStreamsTransport(make_config(server, consumer="b"), 0, 1)
    await first.connect()
    await second.connect()
    received_first: list[int] = []
    received_second: list[int] = []
    tasks = [
        asyncio.create_task(collect(first, received_first)),
        asyncio.create_task(collect(second, received_second)),
    ]

    for index in range(20):
        await publisher.publish(message(index))
    await eventually(lambda: len(received_first) + len(received_second) == 20)

    assert sorted(received_first + received_second) == list(range(20))

    await first.close()
    for index in range(20, 40):
        await publisher.publish(message(index))
    await eventually(lambda: len(received_first) + len(received_second) >= 40)

    assert sorted(received_first + received_second) == list(range(40))
    assert len(set(received_second)) == len(received_second)
    assert set(range(20, 40)) <= set(received_second)
    await second.close()
    await asyncio.gather(*tasks)


async def test_commands_reach_the_command_stream(
    server: fakeredis.FakeServer,
) -> None:
    config = make_config(server)
    transport = RedisStreamsTransport(config, 1, 2)
    await transport.connect()

    await transport.change_presence(status="dnd")
    await transport.voice_state(1, 2)

    entries = await redis_of(config).xrange(config.commands(1))
    assert [int(fields[b"op"]) for _, fields in entries] == [3, 4]
    assert await redis_of(config).xlen(config.commands(0)) == 0
    await transport.close()


async def test_send_requires_a_connection(server: fakeredis.FakeServer) -> None:
    transport = RedisStreamsTransport(make_config(server), 0, 1)

    assert transport.is_closed()
    with pytest.raises(discord.ClientException):
        await transport.send(3, {})


async def test_publisher_runs_commands_and_acknowledges_them(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    transport = RedisStreamsTransport(make_config(server), 0, 1)
    await transport.connect()
    executed: list[tuple[int, Any]] = []

    async def execute(op: int, d: Any) -> None:
        if d.get("fail"):
            raise RuntimeError
        executed.append((op, d))

    await transport.send(3, {"fail": True})
    await transport.send(3, {"x": 1})
    task = asyncio.create_task(publisher.consume_commands(0, execute))

    await eventually(lambda: executed)
    await asyncio.sleep(0.05)
    assert executed == [(3, {"x": 1})]
    client = redis_of(publisher.config)
    summary = await client.xpending(publisher.config.commands(0), "proxy")
    assert summary["pending"] == 0
    publisher.stop()
    await asyncio.wait_for(task, 3)
    await transport.close()


async def test_commands_sent_while_the_proxy_was_down_are_executed(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    transport = RedisStreamsTransport(make_config(server), 0, 1)
    await transport.connect()
    await transport.send(4, {"guild_id": 1})
    executed: list[tuple[int, Any]] = []

    async def execute(op: int, d: Any) -> None:
        executed.append((op, d))

    task = asyncio.create_task(publisher.consume_commands(0, execute))

    await eventually(lambda: executed)
    assert executed == [(4, {"guild_id": 1})]
    publisher.stop()
    await asyncio.wait_for(task, 3)
    await transport.close()


async def test_streams_are_trimmed_to_the_maxlen(server: fakeredis.FakeServer) -> None:
    config = make_config(server, maxlen=10)
    publisher = RedisStreamsPublisher(config)
    await publisher.start()
    for index in range(500):
        await publisher.publish(message(index))

    length = await redis_of(config).xlen(config.stream(0))

    assert length < 500
    assert length >= 10
    last = await redis_of(config).xrevrange(config.stream(0), count=1)
    assert last[0][1][b"t"] == b"TEST"
    await publisher.close()


async def test_transport_trims_the_command_stream(
    server: fakeredis.FakeServer,
) -> None:
    config = make_config(server, maxlen=10)
    transport = RedisStreamsTransport(config, 0, 1)
    await transport.connect()
    for _ in range(500):
        await transport.send(3, {})

    assert await redis_of(config).xlen(config.commands(0)) < 500
    await transport.close()


async def test_latency_and_rate_limit_come_from_the_session_hash(
    server: fakeredis.FakeServer,
    publisher: RedisStreamsPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(brokers_redis, "_STATUS_REFRESH", 0.0)
    transport = RedisStreamsTransport(make_config(server), 0, 1)
    assert str(transport.latency) == "nan"
    await publisher.publish_status(0, latency=float("inf"), ratelimited=False)
    await transport.connect()
    events = transport.events()
    assert transport.latency == float("inf")
    assert not transport.is_ratelimited()

    await publisher.publish_status(0, latency=0.042, ratelimited=True)
    await publisher.publish(message(0))
    await next_event(events)

    assert transport.latency == pytest.approx(0.042)
    assert transport.is_ratelimited()
    await transport.close()
    assert str(transport.latency) == "nan"


async def test_malformed_entries_are_dropped_and_acknowledged(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    config = make_config(server)
    transport = RedisStreamsTransport(config, 0, 1)
    await transport.connect()
    events = transport.events()
    await redis_of(config).xadd(config.stream(0), {"t": "TEST"})
    await redis_of(config).xadd(config.stream(0), {"t": "TEST", "s": "1", "d": "{"})
    await publisher.publish(message(5))

    assert (await next_event(events)).d["index"] == 5
    task = pull(events)
    await asyncio.sleep(0.05)
    assert await pending(config) == 0
    task.cancel()
    await transport.close()


async def test_a_lost_connection_is_raised_without_reconnect(
    server: fakeredis.FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(server)
    transport = RedisStreamsTransport(config, 0, 1)
    transport.reconnect = False
    disconnected: list[bool] = []
    transport.on_disconnect = lambda: disconnected.append(True)
    await transport.connect()

    async def fail(*_: Any, **__: Any) -> None:
        raise RedisConnectionError

    monkeypatch.setattr(redis_of(config), "xreadgroup", fail)

    with pytest.raises(RedisConnectionError):
        await anext(transport.events())
    assert disconnected == [True]
    await transport.close()


async def test_a_lost_connection_is_retried_with_reconnect(
    server: fakeredis.FakeServer,
    publisher: RedisStreamsPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(server)
    transport = RedisStreamsTransport(config, 0, 1)
    disconnected: list[bool] = []
    transport.on_disconnect = lambda: disconnected.append(True)
    await transport.connect()
    original = redis_of(config).xreadgroup
    calls = 0

    async def flaky(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RedisConnectionError
        return await original(*args, **kwargs)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(redis_of(config), "xreadgroup", flaky)
    monkeypatch.setattr(brokers_redis.asyncio, "sleep", no_sleep)
    events = transport.events()
    await publisher.publish(message(3))

    assert (await next_event(events)).d["index"] == 3
    assert disconnected == [True]
    await transport.close()


async def test_a_missing_group_is_created_again(
    server: fakeredis.FakeServer,
    publisher: RedisStreamsPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(server)
    transport = RedisStreamsTransport(config, 0, 1)
    await transport.connect()
    original = redis_of(config).xreadgroup
    calls = 0

    async def lost(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            await redis_of(config).delete(config.stream(0))
            raise ResponseError("NOGROUP No such key or consumer group")
        return await original(*args, **kwargs)

    monkeypatch.setattr(redis_of(config), "xreadgroup", lost)
    events = transport.events()
    task = pull(events)
    await asyncio.sleep(0.1)
    await publisher.publish(message(9))

    assert (await asyncio.wait_for(task, 3)).d["index"] == 9
    await transport.close()


async def test_url_clients_are_owned_by_the_transport(
    server: fakeredis.FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = fakeredis.FakeAsyncRedis(server=server)
    closed: list[bool] = []
    original = fake.aclose

    async def aclose(*args: Any, **kwargs: Any) -> None:
        closed.append(True)
        await original(*args, **kwargs)

    monkeypatch.setattr(fake, "aclose", aclose)

    def from_url(_cls: type[Any], _url: str) -> Any:
        return fake

    monkeypatch.setattr(brokers_redis.Redis, "from_url", classmethod(from_url))
    transport = RedisStreamsTransport(RedisStreamsConfig(block_ms=20), 0, 1)

    await transport.connect()
    await transport.close()

    assert closed == [True]


async def test_shared_clients_are_left_open(server: fakeredis.FakeServer) -> None:
    config = make_config(server)
    transport = RedisStreamsTransport(config, 0, 1)
    await transport.connect()
    await transport.close()

    assert await redis_of(config).ping()


async def test_close_without_events_and_reconnect(
    server: fakeredis.FakeServer, publisher: RedisStreamsPublisher
) -> None:
    transport = RedisStreamsTransport(make_config(server), 0, 1)
    await transport.connect()
    await transport.close()
    assert transport.is_closed()

    await transport.connect()
    events = transport.events()
    await publisher.publish(message(1))

    assert not transport.is_closed()
    assert (await next_event(events)).d["index"] == 1
    await transport.close()


class FakeUpstream(GatewayTransport):
    def __init__(self, shard_id: int | None, shard_count: int | None) -> None:
        super().__init__(shard_id, shard_count)
        self.queue: asyncio.Queue[GatewayEvent | None] = asyncio.Queue()
        self.sent: list[tuple[int, Any]] = []
        self.closed = True

    async def connect(self) -> None:
        self.closed = False
        self.queue.put_nowait(
            GatewayEvent(
                0,
                "READY",
                1,
                {**REDIS_READY, "session_id": f"upstream-{self.shard_id}"},
                self.shard_id,
            )
        )

    async def events(self) -> AsyncIterator[GatewayEvent]:
        while True:
            item = await self.queue.get()
            if item is None:
                return
            yield item

    async def send(self, op: int, d: Any) -> None:
        self.sent.append((int(op), d))

    async def close(self, code: int = 1000) -> None:
        del code
        self.closed = True
        self.queue.put_nowait(None)

    @property
    def latency(self) -> float:
        return 0.042

    def is_ratelimited(self) -> bool:
        return False

    def is_closed(self) -> bool:
        return self.closed


async def test_proxy_forwards_events_and_executes_commands(
    server: fakeredis.FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def static_login(self: HTTPClient, token: str) -> dict[str, Any]:
        self.token = token
        return USER

    monkeypatch.setattr(HTTPClient, "static_login", static_login)
    monkeypatch.setattr(brokers_redis, "_STATUS_REFRESH", 0.0)
    upstreams: dict[int, FakeUpstream] = {}

    def upstream(shard_id: int | None, shard_count: int | None) -> GatewayTransport:
        assert shard_id is not None
        upstreams[shard_id] = FakeUpstream(shard_id, shard_count)
        return upstreams[shard_id]

    proxy = GatewayProxy(
        "token",
        config=make_config(server),
        shard_ids=[0, 1],
        shard_count=2,
        gateway=upstream,
        status_interval=0.02,
    )
    run = asyncio.create_task(proxy.run())
    await asyncio.wait_for(proxy.launched.wait(), 3)
    factory: GatewayTransportFactory = RedisStreamsTransport.factory(
        make_config(server)
    )
    worker = factory(1, 2)
    await eventually(
        lambda: cast("Any", server).dbs[0].get(b"pycord:gateway:session:1") is not None
    )
    await worker.connect()
    events = worker.events()

    ready = await next_event(events)
    assert ready.t == "READY"
    assert ready.d["session_id"] == "upstream-1"
    upstreams[1].queue.put_nowait(GatewayEvent(0, "MESSAGE_CREATE", 2, {"id": "1"}, 1))
    upstreams[0].queue.put_nowait(GatewayEvent(0, "MESSAGE_CREATE", 2, {"id": "0"}, 0))
    message_event = await next_event(events)
    assert message_event.t == "MESSAGE_CREATE"
    assert message_event.d == {"id": "1"}
    assert message_event.shard_id == 1

    await worker.change_presence(status="dnd")
    await eventually(lambda: upstreams[1].sent)
    assert upstreams[1].sent[0][0] == 3
    assert upstreams[1].sent[0][1]["status"] == "dnd"
    assert upstreams[0].sent == []

    await eventually(lambda: worker.latency == pytest.approx(0.042))
    upstreams[1].queue.put_nowait(GatewayEvent(0, "MESSAGE_CREATE", 3, {"id": "2"}, 1))
    await next_event(events)
    assert worker.latency == pytest.approx(0.042)

    proxy.stop()
    await asyncio.wait_for(run, 5)
    assert all(u.closed for u in upstreams.values())
    await worker.close()


async def test_proxy_stops_when_a_shard_fails(
    server: fakeredis.FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def static_login(self: HTTPClient, token: str) -> dict[str, Any]:
        self.token = token
        return USER

    monkeypatch.setattr(HTTPClient, "static_login", static_login)

    class Failing(FakeUpstream):
        async def connect(self) -> None:
            raise discord.LoginFailure("bad token")

    proxy = GatewayProxy(
        "token",
        config=make_config(server),
        shard_ids=[0],
        shard_count=1,
        gateway=Failing,
    )

    with pytest.raises(discord.LoginFailure):
        await asyncio.wait_for(proxy.run(), 5)


def run_cli(
    monkeypatch: pytest.MonkeyPatch, *argv: str, from_env: str | None = None
) -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    if from_env is None:
        monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DISCORD_TOKEN", from_env)
    monkeypatch.setattr(sys, "argv", ["discord", "gateway-proxy", *argv])
    parser, args = cli.parse_args()
    return parser, args


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0-7,9", [0, 1, 2, 3, 4, 5, 6, 7, 9]),
        ("3", [3]),
        ("0, 2-3", [0, 2, 3]),
        ("1,1,0-1", [1, 0]),
    ],
)
def test_shard_ids_are_parsed(value: str, expected: list[int]) -> None:
    assert cli.parse_shard_ids(value) == expected


@pytest.mark.parametrize("value", ["", "a", "1-", "-1", "3-1", "1-2-3", "1,,2"])
def test_invalid_shard_ids_are_rejected(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_shard_ids(value)


def test_cli_parses_the_options(monkeypatch: pytest.MonkeyPatch) -> None:
    _, args = run_cli(
        monkeypatch,
        "--token",
        "abc",
        "--redis-url",
        "redis://example/2",
        "--prefix",
        "bot",
        "--shard-ids",
        "0-3,7",
        "--shard-count",
        "8",
        "--intents",
        "513",
        "--compression",
        "none",
        "--maxlen",
        "50",
        "--log-level",
        "debug",
    )

    assert args.token == "abc"
    assert args.redis_url == "redis://example/2"
    assert args.prefix == "bot"
    assert args.shard_ids == [0, 1, 2, 3, 7]
    assert args.shard_count == 8
    assert args.intents == 513
    assert args.compression == "none"
    assert args.maxlen == 50
    assert args.log_level == "DEBUG"


def test_cli_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    _, args = run_cli(monkeypatch, from_env="from-env")

    assert args.token == "from-env"
    assert args.redis_url == "redis://localhost:6379/0"
    assert args.prefix == "pycord"
    assert args.shard_ids is None
    assert args.shard_count is None
    assert args.intents == discord.Intents.default().value
    assert args.compression == "zlib-stream"
    assert args.maxlen == 10000


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--token", "t", "--shard-ids", "0-1"],
        ["--token", "t", "--shard-ids", "0-3", "--shard-count", "2"],
        ["--token", "t", "--shard-count", "0"],
        ["--token", "t", "--maxlen", "0"],
    ],
)
def test_cli_rejects_invalid_combinations(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    parser, args = run_cli(monkeypatch, *argv)

    with pytest.raises(SystemExit) as info:
        cli.gateway_proxy(parser, args)
    assert info.value.code == 2


def test_cli_runs_the_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict[str, Any]] = []
    ran: list[bool] = []

    class Spy:
        def __init__(self, token: str, **options: Any) -> None:
            created.append({"token": token, **options})

        async def run(self) -> None:
            ran.append(True)

    proxy_module = importlib.import_module("discord.gateway.proxy")
    monkeypatch.setattr(proxy_module, "GatewayProxy", Spy)
    parser, args = run_cli(
        monkeypatch,
        "--token",
        "abc",
        "--shard-ids",
        "0-1",
        "--shard-count",
        "4",
        "--compression",
        "none",
        "--maxlen",
        "7",
        "--intents",
        "1",
    )

    cli.gateway_proxy(parser, args)

    assert ran == [True]
    options = created[0]
    assert options["token"] == "abc"
    assert options["shard_ids"] == [0, 1]
    assert options["shard_count"] == 4
    assert options["compression"] is None
    assert options["config"].maxlen == 7
    assert options["intents"].value == 1


def test_cli_without_redis_reports_the_extra(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    parser, args = run_cli(monkeypatch, "--token", "abc")

    def fail(_name: str) -> Any:
        raise ImportError("install it with: pip install py-cord[redis]")

    monkeypatch.setattr(cli.importlib, "import_module", fail)

    with pytest.raises(SystemExit) as info:
        cli.gateway_proxy(parser, args)
    assert info.value.code == 1
    assert "py-cord[redis]" in capsys.readouterr().err


def test_other_subcommands_do_not_need_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "redis", None)
    monkeypatch.setattr(sys, "argv", ["discord", "newcog", "name"])
    _, args = cli.parse_args()

    assert args.subcommand == "newcog"
