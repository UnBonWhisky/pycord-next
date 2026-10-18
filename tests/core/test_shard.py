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
import math
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import discord
from discord import types as t
from discord.errors import ClientException
from discord.shard import ShardInfo
from discord.state.sharded import AutoShardedConnectionState
from tests.core.rig import Rig

if TYPE_CHECKING:
    from tests.models.context import World


def transport(shard_id: int, latency: float = 0.1) -> Any:
    parent = MagicMock()
    parent.shard_id = shard_id
    parent.latency = latency
    parent.is_ratelimited.return_value = False
    parent.change_presence = AsyncMock()
    return parent


def sharded_client(**options: Any) -> discord.AutoShardedClient:
    return discord.AutoShardedClient(**options)


def test_shard_info_delegates_to_the_manager() -> None:
    manager = MagicMock()
    manager.disconnect_shard = AsyncMock()
    manager.connect_shard = AsyncMock()
    parent = transport(3, latency=0.25)
    info = ShardInfo(manager, parent, 8)
    loop = asyncio.new_event_loop()
    try:
        assert (info.id, info.shard_count, info.latency) == (3, 8, 0.25)
        assert info.is_ws_ratelimited() is False
        parent.is_closed.return_value = False
        loop.run_until_complete(info.disconnect())
        manager.disconnect_shard.assert_awaited_once_with(3)
        loop.run_until_complete(info.connect())
        manager.connect_shard.assert_not_called()
        parent.is_closed.return_value = True
        loop.run_until_complete(info.connect())
        manager.connect_shard.assert_awaited_once_with(3)
        manager.disconnect_shard.reset_mock()
        loop.run_until_complete(info.disconnect())
        manager.disconnect_shard.assert_not_called()
    finally:
        loop.close()


def test_sharded_client_options(world: World) -> None:
    client = sharded_client(shard_ids=[0, 1], shard_count=4, shard_id=9)
    assert client.shard_ids == [0, 1]
    assert client.shard_count == 4
    with pytest.raises(ClientException, match="must provide a shard_count"):
        sharded_client(shard_ids=[0])
    with pytest.raises(ClientException, match="must be a list or a tuple"):
        sharded_client(shard_ids={0}, shard_count=2)


def test_shard_registry_and_latency(world: World) -> None:
    client = sharded_client(shard_count=2)
    assert client.shards == {}
    assert client.get_shard(0) is None
    assert client.latencies == []
    assert math.isnan(client.latency)

    manager = MagicMock()
    manager.transports = {0: transport(0, 0.1), 1: transport(1, 0.3)}
    manager.latencies = [(0, 0.1), (1, 0.3)]
    client._shard_manager = manager
    assert sorted(client.shards) == [0, 1]
    assert client.get_shard(1).latency == 0.3  # type: ignore[union-attr]
    assert client.get_shard(7) is None
    assert client.latency == pytest.approx(0.2)
    assert sorted(client.latencies) == [(0, 0.1), (1, 0.3)]


def test_gateway_shard_selection() -> None:
    client = sharded_client()
    info = SimpleNamespace(shards=3)
    assert client._gateway_shards(info) == (3, [0, 1, 2])  # type: ignore[arg-type]
    assert client.shard_count == 3
    assert client._connection.shard_count == 3

    with pytest.raises(ClientException, match="shard_count is required"):
        sharded_client()._gateway_shards(None)

    chosen = sharded_client(shard_ids=[1], shard_count=4)
    assert chosen._gateway_shards(None) == (4, [1])


def test_change_presence_all_shards_or_one(world: World) -> None:
    rig = Rig(world)
    client = sharded_client()
    client._connection = rig.state  # type: ignore[assignment]
    first, second = transport(0), transport(1)
    manager = MagicMock()
    manager.transports = {0: first, 1: second}
    manager.get_transport.return_value = second
    client._shard_manager = manager
    me = rig.world.member
    me._user.id = rig.world.me.id
    rig.state.user = rig.world.me
    rig.run(rig.guild._add_member(me))

    rig.run(
        client.change_presence(
            activity=discord.Game("chess"), status=discord.Status.offline
        )
    )
    first.change_presence.assert_awaited_once()
    second.change_presence.assert_awaited_once()
    assert first.change_presence.await_args.kwargs["status"] == "invisible"
    refreshed = rig.run(rig.guild.get_me())
    assert refreshed.status is discord.Status.offline
    assert [a.name for a in refreshed.activities] == ["chess"]

    first.change_presence.reset_mock()
    second.change_presence.reset_mock()
    rig.run(client.change_presence(status=discord.Status.idle, shard_id=1))
    first.change_presence.assert_not_called()
    second.change_presence.assert_awaited_once()
    assert second.change_presence.await_args.kwargs["status"] == "idle"

    rig.run(client.change_presence())
    assert second.change_presence.await_args.kwargs["status"] == "online"
    refreshed = rig.run(rig.guild.get_me())
    assert refreshed.activities == ()


def sharded_state(world: World, **options: Any) -> AutoShardedConnectionState:
    return AutoShardedConnectionState(
        dispatch=lambda *_a, **_k: None,
        handlers={},
        hooks={},
        http=world.state.http,
        loop=world.state.loop,
        **options,
    )


def test_sharded_state_chunk_waiting(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    state = sharded_state(world)

    async def scenario() -> None:
        quick = asyncio.get_running_loop().create_future()
        quick.set_result([])
        failing = asyncio.get_running_loop().create_future()
        failing.set_exception(RuntimeError("retrieved"))
        await state._wait_for_shard_chunks(0, (quick, failing), 1.0, 2)
        cancelled = asyncio.get_running_loop().create_future()
        cancelled.cancel()
        await state._wait_for_shard_chunks(0, (quick,), 1.0, 1)

        slow = asyncio.get_running_loop().create_future()
        await state._wait_for_shard_chunks(3, (slow,), 0.01, 7)
        await state._wait_for_bucket(
            SimpleNamespace(shard_id=3),
            [slow],
            0,  # type: ignore[arg-type]
        )

    with caplog.at_level("WARNING"):
        world.run(scenario())
    assert (
        "Shard ID 3 failed to wait for chunks (timeout=0.01) for 7 guilds"
        in caplog.text
    )
    assert "failed to wait for chunks from a sub-bucket with length 1" in caplog.text


def test_sharded_state_chunker_uses_the_guild_shard(world: World) -> None:
    state = sharded_state(world)
    ws = MagicMock()
    ws.request_chunks = AsyncMock()
    state._get_websocket = lambda guild_id=None, *, shard_id=None: ws  # type: ignore[assignment]
    world.run(state.chunker(5, "a", 2, True, shard_id=1, nonce="n"))
    ws.request_chunks.assert_awaited_once_with(
        5, query="a", limit=2, presences=True, nonce="n"
    )


def test_sharded_ready_and_resumed_events(world: World) -> None:
    state = sharded_state(world)
    events: list[tuple[str, Any]] = []
    state.dispatch = lambda name, *args: events.append((name, args))  # type: ignore[assignment]
    user = world.payload(t.user.User, id="31")
    data = {
        "user": user,
        "guilds": [],
        "application": {"id": "77", "flags": 8},
        "__shard_id__": 2,
    }

    async def scenario() -> None:
        await state.parse_ready(data)
        task = state._ready_task
        assert task is not None
        task.cancel()
        await asyncio.sleep(0)
        await state.parse_ready({"user": user, "guilds": [], "__shard_id__": 3})
        state._ready_task.cancel()  # type: ignore[union-attr]
        await state.parse_resumed({"__shard_id__": 2})

    world.run(scenario())

    assert state.user.id == 31
    assert state.application_id == 77
    assert state.application_flags.value == 8
    assert world.run(state.get_user(31)) is not None
    assert events == [
        ("connect", ()),
        ("shard_connect", (2,)),
        ("connect", ()),
        ("shard_connect", (3,)),
        ("resumed", ()),
        ("shard_resumed", (2,)),
    ]


def test_sharded_delay_ready_dispatches_per_shard(world: World) -> None:
    state = sharded_state(world, guild_ready_timeout=0.01, cache_default_sounds=False)
    state.shard_ids = [0]
    events: list[tuple[str, Any]] = []
    state.dispatch = lambda name, *args: events.append((name, args))  # type: ignore[assignment]
    state.call_handlers = lambda name, *args: events.append((f"handler:{name}", args))  # type: ignore[method-assign]
    state._chunk_guilds = False
    state._ready_state = asyncio.Queue()
    guild = world.guild
    guild.unavailable = False
    state._ready_state.put_nowait(guild)
    state.shards_launched.set()

    world.run(state._delay_ready())

    names = [name for name, _ in events]
    assert names == ["guild_available", "shard_ready", "handler:ready", "ready"]
    assert not hasattr(state, "_ready_state")
    assert state._ready_task is None


def test_sharded_delay_ready_with_chunking_and_emojis(world: World) -> None:
    rig = Rig(world)
    state = sharded_state(
        rig.world,
        guild_ready_timeout=0.01,
        cache_default_sounds=False,
        cache_app_emojis=True,
        application_id=1,
        cache_channel_info=True,
    )
    state.http = rig.http
    rig.respond(
        "get_all_application_emojis", {"items": [rig.payload(t.emoji.Emoji, id="8100")]}
    )
    state.shard_ids = [0]
    events: list[str] = []
    state.dispatch = lambda name, *args: events.append(name)  # type: ignore[assignment]
    state.call_handlers = lambda *args: None  # type: ignore[method-assign]
    state._chunk_guilds = True
    state._guild_needs_chunking = AsyncMock(side_effect=[True, False])  # type: ignore[method-assign]
    state.chunk_guild = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state.request_guild_channel_info = AsyncMock(return_value=[])  # type: ignore[method-assign]
    state._ready_state = asyncio.Queue()
    guild = world.guild
    guild.unavailable = True
    other = discord.Guild(
        data={
            **rig.payload(
                t.guild.Guild,
                id="8200",
                unavailable=False,
                channels=[],
                threads=[],
                members=[],
                voice_states=[],
                roles=[],
                emojis=[],
                stickers=[],
                stage_instances=[],
                guild_scheduled_events=[],
                soundboard_sounds=[],
            )
        },
        state=state,
    )
    state._ready_state.put_nowait(guild)
    state._ready_state.put_nowait(other)
    state.shards_launched.set()

    rig.run(state._delay_ready())

    assert events.count("shard_ready") >= 1
    assert "guild_join" in events
    assert "guild_available" in events
    assert events[-1] == "ready"
    state.chunk_guild.assert_awaited_once()
    assert rig.run(state._app_emojis.get(8100)) is not None
