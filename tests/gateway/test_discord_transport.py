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
from discord.gateway import DiscordGatewayTransport, GatewayEvent
from tests.gateway.conftest import (
    Connection,
    FakeGateway,
    eventually,
    make_client,
    next_event,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def client(server: FakeGateway) -> AsyncIterator[discord.Client]:
    client = make_client(server)
    yield client
    await client.http.close()


def make_transport(
    client: discord.Client, *, reconnect: bool = True, **kwargs: Any
) -> DiscordGatewayTransport:
    transport = DiscordGatewayTransport(
        client, identify_limiter=client._identify_limiter, **kwargs
    )
    transport.reconnect = reconnect
    transport._backoff.delay = lambda: 0.0  # type: ignore[method-assign]
    return transport


async def test_hello_heartbeat_ack_and_identify(
    server: FakeGateway, client: discord.Client
) -> None:
    transport = make_transport(client)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    conn = server.connections[0]

    assert conn.query == {"encoding": "json", "v": "10", "compress": "zlib-stream"}
    assert conn.ops(1)[0]["d"] is None
    await eventually(lambda: transport.latency != float("inf"))
    assert transport.latency < 3

    identify = conn.identify
    assert identify["token"] == "token"
    assert identify["intents"] == 0
    assert identify["large_threshold"] == 250
    assert identify["properties"]["browser"] == "pycord"
    assert "shard" not in identify
    assert "compress" not in identify
    await transport.close()


async def test_identify_drops_compress_without_transport_compression(
    server: FakeGateway,
) -> None:
    client = make_client(server, gateway_compression=None, large_threshold=100)
    transport = make_transport(client, shard_id=1, shard_count=3)
    await transport.connect()
    await next_event(transport.events())
    conn = server.connections[0]

    assert "compress" not in conn.query
    assert "compress" not in conn.identify
    assert conn.identify["large_threshold"] == 100
    assert conn.identify["shard"] == [1, 3]
    await transport.close()
    await client.http.close()


@pytest.mark.parametrize("compression", ["zlib-stream", "zstd-stream"])
async def test_events_are_decompressed(server: FakeGateway, compression: str) -> None:
    if compression == "zstd-stream":
        pytest.importorskip("zstandard")
    client = make_client(server, gateway_compression=compression)
    transport = make_transport(client)
    await transport.connect()
    events = transport.events()
    ready = await next_event(events)
    assert ready.d["session_id"] == "session-1"

    for index in range(3):
        await server.connections[0].dispatch("MESSAGE_CREATE", {"index": index})
    assert [(await next_event(events)).d["index"] for _ in range(3)] == [0, 1, 2]
    assert server.connections[0].query["compress"] == compression
    await transport.close()
    await client.http.close()


async def test_before_identify_hook_receives_initial(client: discord.Client) -> None:
    calls: list[tuple[int | None, bool]] = []

    async def hook(shard_id: int | None, *, initial: bool = False) -> None:
        calls.append((shard_id, initial))

    client.before_identify_hook = hook  # type: ignore[method-assign]
    transport = make_transport(client, initial=True)
    await transport.connect()
    await transport.close()
    assert calls == [(None, True)]


async def test_reconnect_opcode_resumes_on_the_resume_gateway_url(
    server: FakeGateway, client: discord.Client
) -> None:
    transport = make_transport(client)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    await server.connections[0].dispatch("MESSAGE_CREATE", {"index": 1})
    await next_event(events)
    await server.connections[0].send({"op": 7, "d": None})

    resumed = await next_event(events)

    assert resumed.t == "RESUMED"
    first, second = server.connections
    assert second.path == "/resume"
    assert second.query == first.query
    resume = second.ops(6)[0]["d"]
    assert resume == {"seq": 2, "session_id": "session-1", "token": "token"}
    assert not second.ops(2)
    await transport.close()


@pytest.mark.parametrize("resumable", [True, False])
async def test_invalid_session(
    server: FakeGateway, client: discord.Client, resumable: bool
) -> None:
    transport = make_transport(client)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    await server.connections[0].send({"op": 9, "d": resumable})

    event = await next_event(events)

    second = server.connections[1]
    if resumable:
        assert event.t == "RESUMED"
        assert second.ops(6)
        assert second.path == "/resume"
    else:
        assert event.t == "READY"
        assert event.d["session_id"] == "session-2"
        assert second.ops(2)
        assert not second.ops(6)
        assert second.path == "/"
    await transport.close()


@pytest.mark.parametrize("code", [4007, 4009])
async def test_close_codes_that_need_a_new_session(
    server: FakeGateway, client: discord.Client, code: int
) -> None:
    transport = make_transport(client)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    await server.connections[0].close(code)

    event = await next_event(events)

    assert event.t == "READY"
    second = server.connections[1]
    assert second.ops(2)
    assert not second.ops(6)
    assert second.path == "/"
    await transport.close()


@pytest.mark.parametrize("code", [4000, 4008])
async def test_other_close_codes_resume(
    server: FakeGateway, client: discord.Client, code: int
) -> None:
    transport = make_transport(client)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    await server.connections[0].close(code)

    event = await next_event(events)

    assert event.t == "RESUMED"
    assert server.connections[1].path == "/resume"
    await transport.close()


async def test_close_code_4004_raises_login_failure(
    server: FakeGateway, client: discord.Client
) -> None:
    transport = make_transport(client)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    await server.connections[0].close(4004)

    with pytest.raises(discord.LoginFailure):
        await next_event(events)
    await transport.close()


async def test_close_code_4014_raises_privileged_intents_required(
    server: FakeGateway, client: discord.Client
) -> None:
    transport = make_transport(client, shard_id=3, shard_count=4)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    await server.connections[0].close(4014)

    with pytest.raises(discord.PrivilegedIntentsRequired) as info:
        await next_event(events)
    assert info.value.shard_id == 3
    await transport.close()


async def test_connection_lost_without_reconnect_raises(
    server: FakeGateway, client: discord.Client
) -> None:
    transport = make_transport(client, reconnect=False)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    await server.connections[0].close(4012)

    with pytest.raises(discord.ConnectionClosed) as info:
        await next_event(events)
    assert info.value.code == 4012
    await transport.close()


async def test_connection_lost_notifies_on_disconnect(
    server: FakeGateway, client: discord.Client
) -> None:
    transport = make_transport(client)
    disconnects: list[int] = []
    transport.on_disconnect = lambda: disconnects.append(1)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    await server.connections[0].send({"op": 7, "d": None})
    await next_event(events)
    assert disconnects == [1]
    await transport.close()
    async for _ in events:
        pass
    assert disconnects == [1, 1]


async def test_connection_reset_resumes(client: discord.Client) -> None:
    transport = make_transport(client)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    ws = transport.ws
    assert ws is not None

    async def poll() -> None:
        raise ConnectionResetError(104, "reset")

    ws.poll_event = poll  # type: ignore[method-assign]
    event = await next_event(events)

    assert event.t == "RESUMED"
    assert transport.ws is not ws
    await transport.close()


async def test_fresh_connect_after_close_starts_a_new_session(
    server: FakeGateway, client: discord.Client
) -> None:
    transport = make_transport(client)
    await transport.connect()
    await next_event(transport.events())
    await transport.close()
    assert transport.is_closed()

    await transport.connect()
    event = await next_event(transport.events())

    assert event.d["session_id"] == "session-2"
    assert not server.connections[1].ops(6)
    assert not transport.is_closed()
    await transport.close()


async def test_send_without_connection_raises(client: discord.Client) -> None:
    transport = make_transport(client)
    with pytest.raises(discord.ClientException):
        await transport.send(3, {})
    assert transport.is_closed()
    assert transport.is_ratelimited() is False
    assert transport.latency != transport.latency


async def test_rate_limited_dispatch_is_a_regular_event(
    server: FakeGateway, client: discord.Client
) -> None:
    transport = make_transport(client)
    await transport.connect()
    events = transport.events()
    await next_event(events)
    payload = {"opcode": 8, "retry_after": 1.5, "meta": {"guild_id": "1", "nonce": "n"}}
    await server.connections[0].dispatch("RATE_LIMITED", payload)

    event = await next_event(events)

    assert isinstance(event, GatewayEvent)
    assert event.t == "RATE_LIMITED"
    assert event.d == payload
    await transport.close()


async def test_first_connection_failure_is_retried(
    server: FakeGateway, client: discord.Client
) -> None:
    attempts = 0
    real = client.http.get_gateway

    async def flaky(**kwargs: Any) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise discord.GatewayNotFound
        return await real(**kwargs)

    client.http.get_gateway = flaky  # type: ignore[method-assign]
    transport = make_transport(client)
    await asyncio.wait_for(transport.connect(), 3)
    assert attempts == 2
    assert len(server.connections) == 1
    await transport.close()


def connections_identified(server: FakeGateway) -> list[Connection]:
    return [c for c in server.connections if c.ops(2)]


async def test_socket_is_closed_when_the_identify_fails(
    server: FakeGateway, client: discord.Client
) -> None:
    async def hook(_shard_id: int | None, *, initial: bool = False) -> None:
        raise RuntimeError(initial)

    client.before_identify_hook = hook  # type: ignore[method-assign]
    transport = make_transport(client)

    with pytest.raises(RuntimeError):
        await transport.connect()

    await eventually(lambda: server.connections[0].ws.closed)
