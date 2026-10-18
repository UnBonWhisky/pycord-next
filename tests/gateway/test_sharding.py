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

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import pytest

from discord.gateway import (
    GatewayEvent,
    GatewayTransport,
    IdentifyLimiter,
    ShardManager,
)
from tests.gateway.conftest import eventually

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class FakeTransport(GatewayTransport):
    def __init__(
        self,
        shard_id: int | None,
        shard_count: int | None,
        log: list[tuple[str, int | None, float]],
        delays: dict[int | None, float],
    ) -> None:
        super().__init__(shard_id, shard_count)
        self.log = log
        self.delay = delays.get(shard_id, 0.05)
        self.queue: asyncio.Queue[GatewayEvent | BaseException | None] = asyncio.Queue()
        self.closed = True
        self.sent: list[tuple[int, Any]] = []
        self.fail_connect: BaseException | None = None
        self.ratelimited = False

    async def connect(self) -> None:
        self.log.append(("start", self.shard_id, time.monotonic()))
        await asyncio.sleep(self.delay)
        if self.fail_connect is not None:
            raise self.fail_connect
        self.closed = False
        self.queue = asyncio.Queue()
        self.log.append(("end", self.shard_id, time.monotonic()))

    async def events(self) -> AsyncIterator[GatewayEvent]:
        while True:
            item = await self.queue.get()
            if item is None:
                return
            if isinstance(item, BaseException):
                raise item
            yield item

    async def send(self, op: int, d: Any) -> None:
        self.sent.append((op, d))

    async def close(self, _code: int = 1000) -> None:
        self.closed = True
        self.queue.put_nowait(None)

    @property
    def latency(self) -> float:
        return 0.1 + (self.shard_id or 0)

    def is_ratelimited(self) -> bool:
        return self.ratelimited

    def is_closed(self) -> bool:
        return self.closed

    def emit(self, name: str, **data: Any) -> None:
        self.queue.put_nowait(
            GatewayEvent(op=0, t=name, s=None, d=data, shard_id=self.shard_id)
        )


class Harness:
    def __init__(
        self,
        shard_ids: list[int | None],
        *,
        max_concurrency: int = 1,
        shard_count: int | None = None,
        delays: dict[int | None, float] | None = None,
        sharded: bool = True,
    ) -> None:
        self.log: list[tuple[str, int | None, float]] = []
        self.dispatched: list[tuple[Any, ...]] = []
        self.launched = False
        self.created: dict[int | None, FakeTransport] = {}

        def factory(shard_id: int | None, count: int | None) -> GatewayTransport:
            transport = FakeTransport(shard_id, count, self.log, delays or {})
            self.created[shard_id] = transport
            return transport

        def mark() -> None:
            self.launched = True

        self.manager = ShardManager(
            factory,
            shard_ids=shard_ids,
            shard_count=shard_count if shard_count is not None else len(shard_ids),
            identify_limiter=IdentifyLimiter(max_concurrency=max_concurrency),
            dispatch=lambda *args: self.dispatched.append(args),
            sharded=sharded,
            on_launched=mark,
        )

    def when(self, kind: str, shard_id: int) -> float:
        return next(t for k, s, t in self.log if k == kind and s == shard_id)


async def collect(manager: ShardManager, count: int) -> list[GatewayEvent]:
    events = manager.events()
    return [await asyncio.wait_for(anext(events), 3) for _ in range(count)]


def test_buckets_group_the_shards_by_rate_limit_key() -> None:
    harness = Harness([0, 1, 2, 3], max_concurrency=2)
    assert harness.manager.buckets == [[0, 2], [1, 3]]
    assert Harness([0, 1, 2], max_concurrency=1).manager.buckets == [[0, 1, 2]]
    assert Harness([0, 1], max_concurrency=16).manager.buckets == [[0], [1]]
    assert Harness([None]).manager.buckets == [[None]]


async def test_four_shards_with_a_max_concurrency_of_two() -> None:
    harness = Harness([0, 1, 2, 3], max_concurrency=2)
    await harness.manager.start()
    await asyncio.wait_for(harness.manager.launched.wait(), 3)

    assert harness.launched
    assert sorted(harness.manager.transports) == [0, 1, 2, 3]
    assert abs(harness.when("start", 0) - harness.when("start", 1)) < 0.03
    assert harness.when("start", 2) >= harness.when("end", 0)
    assert harness.when("start", 3) >= harness.when("end", 1)
    assert harness.when("start", 2) < harness.when("end", 1) + 0.03
    await harness.manager.close()


async def test_a_max_concurrency_of_one_launches_the_shards_in_order() -> None:
    harness = Harness([0, 1, 2], max_concurrency=1)
    await harness.manager.start()
    await asyncio.wait_for(harness.manager.launched.wait(), 3)

    order = [(kind, shard) for kind, shard, _ in harness.log]
    assert order == [
        ("start", 0),
        ("end", 0),
        ("start", 1),
        ("end", 1),
        ("start", 2),
        ("end", 2),
    ]
    await harness.manager.close()


async def test_transports_receive_the_manager_settings() -> None:
    harness = Harness([0, 1], max_concurrency=2)
    await harness.manager.start(reconnect=False)
    await asyncio.wait_for(harness.manager.launched.wait(), 3)

    for shard_id, transport in harness.created.items():
        assert transport.reconnect is False
        assert transport.shard_count == 2
        transport.on_disconnect()
        assert ("shard_disconnect", shard_id) in harness.dispatched
    assert harness.dispatched.count(("disconnect",)) == 2
    await harness.manager.close()


async def test_events_of_launched_shards_flow_while_others_launch() -> None:
    harness = Harness([0, 1], max_concurrency=1, delays={1: 0.5})
    await harness.manager.start()
    await eventually(lambda: 0 in harness.created and not harness.created[0].closed)

    harness.created[0].emit("READY")
    (event,) = await collect(harness.manager, 1)

    assert event.t == "READY"
    assert event.shard_id == 0
    assert not harness.launched
    await harness.manager.close()


async def test_events_of_each_shard_stay_in_order() -> None:
    harness = Harness([0, 1, 2, 3], max_concurrency=2)
    await harness.manager.start()
    await asyncio.wait_for(harness.manager.launched.wait(), 3)

    for index in range(5):
        for transport in harness.created.values():
            transport.emit("MESSAGE_CREATE", index=index)

    received = await collect(harness.manager, 20)
    for shard_id in range(4):
        assert [e.d["index"] for e in received if e.shard_id == shard_id] == list(
            range(5)
        )
    await harness.manager.close()


async def test_a_transport_error_is_raised_from_the_events() -> None:
    harness = Harness([0, 1], max_concurrency=2)
    await harness.manager.start()
    await asyncio.wait_for(harness.manager.launched.wait(), 3)
    harness.created[1].queue.put_nowait(RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        await collect(harness.manager, 1)
    await harness.manager.close()


async def test_a_launch_error_is_raised_from_the_events() -> None:
    harness = Harness([0, 1], max_concurrency=2)
    harness.manager._factory = lambda s, c: _failing(harness, s, c)
    await harness.manager.start()

    with pytest.raises(ConnectionError):
        await collect(harness.manager, 1)
    assert not harness.launched
    await harness.manager.close()


def _failing(
    harness: Harness, shard_id: int | None, count: int | None
) -> FakeTransport:
    transport = FakeTransport(shard_id, count, harness.log, {})
    if shard_id == 1:
        transport.fail_connect = ConnectionError("down")
    return transport


async def test_a_cleanly_ended_transport_closes_the_manager() -> None:
    harness = Harness([0, 1], max_concurrency=2)
    await harness.manager.start()
    await asyncio.wait_for(harness.manager.launched.wait(), 3)
    harness.created[0].queue.put_nowait(None)

    async def drain() -> None:
        async for _ in harness.manager.events():
            pass

    await asyncio.wait_for(drain(), 3)
    assert all(t.closed for t in harness.created.values())


async def test_close_ends_the_events_and_is_idempotent() -> None:
    harness = Harness([0, 1], max_concurrency=2)
    await harness.manager.start()
    await asyncio.wait_for(harness.manager.launched.wait(), 3)
    events = harness.manager.events()
    pending = asyncio.ensure_future(anext(events))
    await asyncio.sleep(0)

    await harness.manager.close()
    await harness.manager.close()

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(pending, 3)
    assert all(t.closed for t in harness.created.values())


async def test_close_while_launching_cancels_the_launch() -> None:
    harness = Harness([0, 1], max_concurrency=1, delays={1: 5})
    await harness.manager.start()
    await eventually(lambda: ("start", 1) in [(k, s) for k, s, _ in harness.log])

    await asyncio.wait_for(harness.manager.close(), 3)

    assert not harness.launched


async def test_routing_by_guild() -> None:
    harness = Harness([0, 1, 2, 3], max_concurrency=2)
    await harness.manager.start()
    await asyncio.wait_for(harness.manager.launched.wait(), 3)
    manager = harness.manager

    guild_id = 5 << 22
    assert manager.get_transport(guild_id) is harness.created[1]
    assert manager.get_transport(shard_id=3) is harness.created[3]
    assert manager.get_transport((4 << 22) + 123) is harness.created[0]
    assert manager.latencies == [(0, 0.1), (1, 1.1), (2, 2.1), (3, 3.1)]
    assert not manager.is_ratelimited()
    harness.created[2].ratelimited = True
    assert manager.is_ratelimited()
    await manager.close()


async def test_unsharded_manager_always_uses_its_transport() -> None:
    harness = Harness([None], shard_count=1, sharded=False)
    await harness.manager.start()
    await asyncio.wait_for(harness.manager.launched.wait(), 3)

    assert harness.manager.get_transport(123 << 22) is harness.created[None]
    harness.created[None].on_disconnect()
    assert harness.dispatched == [("disconnect",)]
    await harness.manager.close()


async def test_disconnect_connect_and_reconnect_a_shard() -> None:
    harness = Harness([0, 1], max_concurrency=2)
    await harness.manager.start()
    await asyncio.wait_for(harness.manager.launched.wait(), 3)
    manager = harness.manager
    transport = harness.created[1]

    await manager.disconnect_shard(1)
    assert transport.closed
    assert ("shard_disconnect", 1) in harness.dispatched

    await manager.connect_shard(1)
    assert not transport.closed
    transport.emit("RESUMED")
    (event,) = await collect(manager, 1)
    assert event.shard_id == 1

    starts = len([1 for k, s, _ in harness.log if k == "start" and s == 1])
    await manager.reconnect_shard(1)
    assert len([1 for k, s, _ in harness.log if k == "start" and s == 1]) == starts + 1
    assert not transport.closed
    await manager.close()
