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
    DiscordGatewayTransport,
    GatewayEvent,
    GatewayTransport,
    Opcode,
)
from tests.gateway.conftest import (
    FakeGateway,
    make_client,
    next_event,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from tests.gateway.conftest import TransportHarness


async def test_connect_then_ready_is_the_first_event(
    transport_factory: Callable[[], Awaitable[TransportHarness]],
) -> None:
    harness = await transport_factory()
    events = harness.transport.events()

    event = await next_event(events)

    assert isinstance(event, GatewayEvent)
    assert event.op == 0
    assert event.t == "READY"


async def test_events_keep_the_order_of_the_dispatches(
    transport_factory: Callable[[], Awaitable[TransportHarness]],
) -> None:
    harness = await transport_factory()
    events = harness.transport.events()
    await next_event(events)

    for index in range(5):
        await harness.remote_dispatch("MESSAGE_CREATE", {"index": index})

    received = [await next_event(events) for _ in range(5)]
    assert [e.t for e in received] == ["MESSAGE_CREATE"] * 5
    assert [e.d["index"] for e in received] == list(range(5))
    sequences = [e.s for e in received if e.s is not None]
    assert sequences == sorted(sequences)


async def test_dispatch_events_carry_the_shard_id(
    transport_factory: Callable[[], Awaitable[TransportHarness]],
) -> None:
    harness = await transport_factory()
    events = harness.transport.events()
    ready = await next_event(events)
    assert ready.shard_id == harness.transport.shard_id


async def test_commands_are_sent_to_the_gateway(
    transport_factory: Callable[[], Awaitable[TransportHarness]],
) -> None:
    harness = await transport_factory()
    transport = harness.transport

    await transport.change_presence(status="online")
    await transport.request_chunks(1, "ab", limit=5, nonce="n", presences=True)
    await transport.voice_state(1, 2, self_mute=True)
    await transport.request_soundboard_sounds([1, 2])
    await transport.request_channel_info(1, ["status", "voice_start_time"])
    await transport.send(Opcode.PRESENCE, {"x": 1})

    async def sent() -> list[tuple[int, Any]]:
        return await harness.remote_commands()

    commands = await sent()
    for _ in range(300):
        if len(commands) >= 6:
            break
        await asyncio.sleep(0.01)
        commands = await sent()
    assert [op for op, _ in commands] == [3, 8, 4, 31, 43, 3]
    assert commands[0][1] == {
        "activities": [],
        "afk": False,
        "since": 0.0,
        "status": "online",
    }
    assert commands[1][1] == {
        "guild_id": 1,
        "presences": True,
        "limit": 5,
        "nonce": "n",
        "query": "ab",
    }
    assert commands[2][1] == {
        "guild_id": 1,
        "channel_id": 2,
        "self_mute": True,
        "self_deaf": False,
    }
    assert commands[3][1] == {"guild_ids": [1, 2]}
    assert commands[4][1] == {
        "guild_id": 1,
        "fields": ["status", "voice_start_time"],
    }
    assert commands[5][1] == {"x": 1}


async def test_idle_presence_sets_since(
    transport_factory: Callable[[], Awaitable[TransportHarness]],
) -> None:
    harness = await transport_factory()
    await harness.transport.change_presence(
        activity=discord.Game("chess"), status="idle"
    )
    commands = []
    while not commands:
        commands = await harness.remote_commands()
        await asyncio.sleep(0.01)
    data = commands[0][1]
    assert data["status"] == "idle"
    assert data["since"] > 0
    assert data["activities"][0]["name"] == "chess"


async def test_change_presence_rejects_a_bad_activity(
    transport_factory: Callable[[], Awaitable[TransportHarness]],
) -> None:
    harness = await transport_factory()
    with pytest.raises(discord.InvalidArgument):
        await harness.transport.change_presence(activity="nope")  # type: ignore[arg-type]


async def test_close_ends_the_events_and_closes_the_transport(
    transport_factory: Callable[[], Awaitable[TransportHarness]],
) -> None:
    harness = await transport_factory()
    transport = harness.transport
    events = transport.events()
    await next_event(events)
    assert not transport.is_closed()

    await transport.close()

    async def drain() -> None:
        async for _ in events:
            pass

    await asyncio.wait_for(drain(), 3)
    assert transport.is_closed()


async def test_latency_and_rate_limit_state(
    transport_factory: Callable[[], Awaitable[TransportHarness]],
) -> None:
    harness = await transport_factory()
    assert isinstance(harness.transport, GatewayTransport)
    assert isinstance(harness.transport.latency, float)
    assert harness.transport.is_ratelimited() is False


async def test_transport_knows_its_shard(server: FakeGateway) -> None:
    client = make_client(server)
    transport = DiscordGatewayTransport(client, 0, 2)
    await transport.connect()
    assert transport.shard_id == 0
    assert transport.shard_count == 2
    await transport.close()
    await client.http.close()
