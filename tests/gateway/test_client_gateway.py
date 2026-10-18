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
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord.gateway import (
    DiscordWebSocket,
    GatewayEvent,
    GatewayTransport,
)
from discord.state import ChunkRequest
from tests.gateway.conftest import FakeGateway, eventually, make_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def run() -> AsyncIterator[list[tuple[discord.Client, asyncio.Task[None]]]]:
    started: list[tuple[discord.Client, asyncio.Task[None]]] = []
    yield started
    for client, task in started:
        if not client.is_closed():
            await client.close()
        await client.http.close()
        task.cancel()
    await asyncio.gather(*(task for _, task in started), return_exceptions=True)


def start(
    client: discord.Client,
    started: list[tuple[discord.Client, asyncio.Task[None]]],
    **kwargs: Any,
) -> asyncio.Task[None]:
    task = asyncio.ensure_future(client.connect(**kwargs))
    started.append((client, task))
    return task


async def stop(client: discord.Client, task: asyncio.Task[None]) -> None:
    await client.close()
    await client.http.close()
    await asyncio.wait_for(task, 5)


def record(client: discord.Client) -> list[tuple[str, tuple[Any, ...]]]:
    seen: list[tuple[str, tuple[Any, ...]]] = []
    original = client.dispatch

    def dispatch(event: str, *args: Any, **kwargs: Any) -> None:
        seen.append((event, args))
        original(event, *args, **kwargs)

    client.dispatch = dispatch  # type: ignore[method-assign]
    client._connection.dispatch = dispatch
    return seen


def names(seen: list[tuple[str, tuple[Any, ...]]]) -> list[str]:
    return [name for name, _ in seen]


@pytest.mark.parametrize("value", [49, 251, 0])
def test_large_threshold_is_validated(value: int) -> None:
    with pytest.raises(ValueError, match="large_threshold"):
        discord.Client(large_threshold=value)


@pytest.mark.parametrize("value", [50, 250])
def test_large_threshold_bounds(value: int) -> None:
    assert discord.Client(large_threshold=value)._large_threshold == value


def test_gateway_compression_is_validated() -> None:
    with pytest.raises(ValueError, match="gateway_compression"):
        discord.Client(gateway_compression="gzip")


def test_gateway_options_have_defaults() -> None:
    client = discord.Client()
    assert client._gateway_compression == "zlib-stream"
    assert client._large_threshold == 250
    assert client.ws is None
    assert client.session_start_limit is None
    assert client.latency != client.latency
    assert client.is_ws_ratelimited() is False


async def test_connect_dispatches_the_connection_events(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server)
    seen = record(client)
    task = start(client, run)

    await eventually(lambda: "ready" in names(seen))

    assert "connect" in names(seen)
    assert ("socket_event_type", ("READY",)) in seen
    assert client.user is not None
    assert client.user.id == 42
    assert isinstance(client.ws, DiscordWebSocket)
    assert client.latency < 3
    assert client.is_ws_ratelimited() is False
    assert client.session_start_limit == discord.gateway.SessionStartLimit(
        total=1000, remaining=999, reset_after=1000, max_concurrency=1
    )
    await stop(client, task)


async def test_resume_dispatches_resumed(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server)
    seen = record(client)
    task = start(client, run)
    await eventually(lambda: "ready" in names(seen))

    await server.connections[0].send({"op": 7, "d": None})

    await eventually(lambda: "resumed" in names(seen))
    assert "disconnect" in names(seen)
    assert server.connections[1].path == "/resume"
    await stop(client, task)


async def test_unknown_events_are_ignored(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server)
    seen = record(client)
    task = start(client, run)
    await eventually(lambda: "ready" in names(seen))

    await server.connections[0].dispatch("SOMETHING_NEW", {})
    await server.connections[0].dispatch("RESUMED", {})

    await eventually(lambda: "resumed" in names(seen))
    assert ("socket_event_type", ("SOMETHING_NEW",)) in seen
    await stop(client, task)


async def test_debug_events(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server, enable_debug_events=True)
    seen = record(client)
    task = start(client, run)
    await eventually(lambda: "ready" in names(seen))

    await client.change_presence(status=discord.Status.idle)

    await eventually(lambda: "socket_raw_send" in names(seen))
    assert "socket_raw_receive" in names(seen)
    await stop(client, task)


async def test_change_presence_goes_through_the_transport(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server)
    seen = record(client)
    task = start(client, run)
    await eventually(lambda: "ready" in names(seen))

    await client.change_presence(
        activity=discord.Game("chess"), status=discord.Status.dnd
    )

    await eventually(lambda: server.connections[0].ops(3))
    data = server.connections[0].ops(3)[0]["d"]
    assert data["status"] == "dnd"
    assert data["activities"][0]["name"] == "chess"
    await stop(client, task)


async def test_change_presence_before_connecting_raises(server: FakeGateway) -> None:
    client = make_client(server)
    with pytest.raises(discord.ClientException):
        await client.change_presence(status=discord.Status.idle)
    await client.http.close()


async def test_bad_token_close_raises_login_failure(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    async def refuse(conn: Any, _payload: Any) -> None:
        await conn.close(4004)

    server.on_identify = refuse
    client = make_client(server)
    task = start(client, run)

    with pytest.raises(discord.LoginFailure):
        await asyncio.wait_for(task, 5)
    assert client.is_closed()
    await client.http.close()


async def test_disabled_intents_close_raises_privileged_intents_required(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    async def refuse(conn: Any, _payload: Any) -> None:
        await conn.close(4014)

    server.on_identify = refuse
    client = make_client(server)
    task = start(client, run)

    with pytest.raises(discord.PrivilegedIntentsRequired):
        await asyncio.wait_for(task, 5)
    await client.http.close()


async def test_connect_without_reconnect_stops_on_a_dropped_connection(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server)
    seen = record(client)
    task = start(client, run, reconnect=False)
    await eventually(lambda: "ready" in names(seen))

    await server.connections[0].close(4012)

    with pytest.raises(discord.ConnectionClosed):
        await asyncio.wait_for(task, 5)
    assert client.is_closed()
    await client.http.close()


async def test_close_ends_connect(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server)
    seen = record(client)
    task = start(client, run)
    await eventually(lambda: "ready" in names(seen))

    await client.close()
    await asyncio.wait_for(task, 5)

    assert client.is_closed()
    assert not client.is_ready()
    assert "disconnect" in names(seen)
    await client.http.close()


async def test_rate_limited_event_and_chunk_requests(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server)
    seen = record(client)
    task = start(client, run)
    await eventually(lambda: "ready" in names(seen))
    state = client._connection
    request = ChunkRequest(1, client.loop, state._get_guild)
    other = ChunkRequest(1, client.loop, state._get_guild)
    state._chunk_requests[request.nonce] = request
    state._chunk_requests[other.nonce] = other
    future = request.get_future()
    untouched = other.get_future()

    await server.connections[0].dispatch(
        "RATE_LIMITED",
        {
            "opcode": 8,
            "retry_after": 2.5,
            "meta": {"guild_id": "1", "nonce": request.nonce},
        },
    )

    with pytest.raises(discord.GatewayRateLimited) as info:
        await asyncio.wait_for(future, 3)
    assert info.value.retry_after == 2.5
    assert info.value.opcode == 8
    assert info.value.meta["guild_id"] == "1"
    assert not untouched.done()
    assert request.nonce not in state._chunk_requests
    assert other.nonce in state._chunk_requests
    payload = next(args[0] for name, args in seen if name == "gateway_rate_limited")
    assert isinstance(payload, discord.raw_models.GatewayRateLimit)
    assert payload.opcode == 8
    assert payload.retry_after == 2.5
    assert payload.guild_id == 1
    assert payload.nonce == request.nonce
    await stop(client, task)


async def test_rate_limited_event_without_a_nonce(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server)
    seen = record(client)
    task = start(client, run)
    await eventually(lambda: "ready" in names(seen))

    await server.connections[0].dispatch(
        "RATE_LIMITED", {"opcode": 8, "retry_after": 1.0}
    )

    await eventually(lambda: "gateway_rate_limited" in names(seen))
    await stop(client, task)


async def test_autosharded_client_launches_buckets_in_parallel(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(
        server, discord.AutoShardedClient, shard_count=4, max_concurrency=2
    )
    client._identify_limiter.per = 0.3
    seen = record(client)
    task = start(client, run)

    await eventually(lambda: "ready" in names(seen), timeout=5)

    times = dict(server.identify_times)
    assert sorted(times) == [0, 1, 2, 3]
    assert abs(times[0] - times[1]) < 0.15
    assert times[2] - times[0] >= 0.29
    assert times[3] - times[1] >= 0.29
    assert client.shard_count == 4
    assert sorted(client.shards) == [0, 1, 2, 3]
    assert sorted(shard_id for shard_id, _ in client.latencies) == [0, 1, 2, 3]
    assert client.latency < 3
    assert client.get_shard(2).id == 2  # type: ignore[union-attr]
    assert client.get_shard(9) is None
    assert client.get_shard(1).shard_count == 4  # type: ignore[union-attr]
    assert client.is_ws_ratelimited() is False
    assert names(seen).count("shard_connect") == 4
    for conn in server.connections:
        assert conn.identify["shard"][1] == 4
    await stop(client, task)


async def test_shard_info_controls_a_shard(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server, discord.AutoShardedClient, shard_count=2)
    seen = record(client)
    task = start(client, run)
    await eventually(lambda: "ready" in names(seen), timeout=5)
    shard = client.get_shard(1)
    assert shard is not None
    assert not shard.is_closed()

    await shard.disconnect()
    assert shard.is_closed()
    assert ("shard_disconnect", (1,)) in seen

    await shard.connect()
    assert not shard.is_closed()
    await eventually(lambda: names(seen).count("shard_connect") == 3)

    await shard.reconnect()
    await eventually(lambda: names(seen).count("shard_connect") == 4)
    await stop(client, task)


async def test_autosharded_presence_and_chunk_routing(
    server: FakeGateway, run: list[tuple[discord.Client, asyncio.Task[None]]]
) -> None:
    client = make_client(server, discord.AutoShardedClient, shard_count=2)
    seen = record(client)
    task = start(client, run)
    await eventually(lambda: "ready" in names(seen), timeout=5)

    await client.change_presence(status=discord.Status.idle, shard_id=1)
    await client._connection.chunker(3 << 22, nonce="n")
    await client._connection.chunker(2 << 22, nonce="m", shard_id=1)

    by_shard = {c.identify["shard"][0]: c for c in server.connections if c.ops(2)}
    await eventually(lambda: len(by_shard[1].ops(3, 8)) == 3)
    assert by_shard[0].ops(3, 8) == []
    await stop(client, task)


class ScriptedTransport(GatewayTransport):
    def __init__(self, shard_id: int | None, shard_count: int | None) -> None:
        super().__init__(shard_id, shard_count)
        self.connected = False
        self.closed = False
        self.stopped = asyncio.Event()
        self.sent: list[tuple[int, Any]] = []

    async def connect(self) -> None:
        self.connected = True

    async def events(self) -> AsyncIterator[GatewayEvent]:
        yield GatewayEvent(op=0, t="RESUMED", s=1, d={}, shard_id=self.shard_id)
        await self.stopped.wait()

    async def send(self, op: int, d: Any) -> None:
        self.sent.append((op, d))

    async def close(self, _code: int = 1000) -> None:
        self.closed = True
        self.stopped.set()

    @property
    def latency(self) -> float:
        return 0.25

    def is_ratelimited(self) -> bool:
        return True

    def is_closed(self) -> bool:
        return self.closed


async def test_custom_gateway_transport(
    run: list[tuple[discord.Client, asyncio.Task[None]]],
) -> None:
    created: list[ScriptedTransport] = []

    def factory(shard_id: int | None, shard_count: int | None) -> GatewayTransport:
        created.append(ScriptedTransport(shard_id, shard_count))
        return created[-1]

    client = discord.Client(gateway=factory, shard_id=1, shard_count=3)
    seen = record(client)
    task = start(client, run)

    await eventually(lambda: "resumed" in names(seen))

    assert (created[0].shard_id, created[0].shard_count) == (1, 3)
    assert client.ws is None
    assert client.latency == 0.25
    assert client.is_ws_ratelimited() is True
    assert client.session_start_limit is None
    await client.change_presence(status=discord.Status.idle)
    assert created[0].sent[0][0] == 3
    await client.close()
    await asyncio.wait_for(task, 5)
    await client.http.close()


async def test_autosharded_custom_gateway_needs_shard_count_without_http(
    run: list[tuple[discord.Client, asyncio.Task[None]]],
) -> None:
    created: list[ScriptedTransport] = []

    def factory(shard_id: int | None, shard_count: int | None) -> GatewayTransport:
        created.append(ScriptedTransport(shard_id, shard_count))
        return created[-1]

    client = discord.AutoShardedClient(gateway=factory)
    calls: list[bool] = []

    async def get_bot_gateway_info(**_kwargs: Any) -> Any:
        calls.append(True)
        raise AssertionError("Get Gateway Bot must not be called")

    client.http.get_bot_gateway_info = get_bot_gateway_info  # type: ignore[method-assign]
    task = start(client, run)

    with pytest.raises(discord.ClientException, match="shard_count is required"):
        await asyncio.wait_for(task, 5)
    assert calls == []
    assert created == []


async def test_custom_transport_failure_closes_the_client(
    run: list[tuple[discord.Client, asyncio.Task[None]]],
) -> None:
    class Failing(ScriptedTransport):
        async def events(self) -> AsyncIterator[GatewayEvent]:
            raise RuntimeError("broker down")
            yield

    client = discord.Client(gateway=Failing)
    task = start(client, run)

    with pytest.raises(RuntimeError, match="broker down"):
        await asyncio.wait_for(task, 5)
    assert client.is_closed()
    await client.http.close()


async def test_before_identify_hook_default_does_not_sleep(
    server: FakeGateway,
) -> None:
    client = make_client(server)
    loop = asyncio.get_running_loop()
    start_time = loop.time()
    await client.before_identify_hook(0, initial=False)
    assert loop.time() - start_time < 0.1
    await client.http.close()
