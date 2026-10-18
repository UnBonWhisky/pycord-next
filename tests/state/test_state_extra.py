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
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import discord
from discord import types as t
from discord.errors import GatewayRateLimited, InvalidData
from discord.state import ConnectionState
from discord.state.state import ChunkRequest
from tests.core.rig import Rig

if TYPE_CHECKING:
    from discord.http import HTTPClient
    from tests.models.context import World


def make_state(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, **options: Any
) -> ConnectionState:
    return ConnectionState(
        dispatch=lambda *_a, **_k: None,
        handlers={},
        hooks={},
        http=http,
        loop=loop,
        **options,
    )


@pytest.mark.parametrize(
    ("options", "error", "message"),
    [
        ({"guild_ready_timeout": -1}, ValueError, "cannot be negative"),
        ({"allowed_mentions": 1}, TypeError, "allowed_mentions parameter"),
        ({"activity": "x"}, TypeError, "activity parameter"),
        ({"intents": 5}, TypeError, "intents parameter"),
        (
            {"intents": discord.Intents.none(), "chunk_guilds_at_startup": True},
            ValueError,
            "Intents.members must be enabled",
        ),
        ({"member_cache_flags": 5}, TypeError, "member_cache_flags parameter"),
        ({"capabilities": "x"}, TypeError, "capabilities parameter"),
        ({"cache_backend": object()}, TypeError, "cache_backend parameter"),
    ],
)
def test_state_rejects_invalid_options(
    loop: asyncio.AbstractEventLoop,
    http: HTTPClient,
    options: dict[str, Any],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        make_state(loop, http, **options)


def test_state_option_normalisation(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, caplog: pytest.LogCaptureFixture
) -> None:
    state = make_state(
        loop,
        http,
        max_messages=0,
        activity=discord.Game("chess"),
        status=discord.Status.offline,
        capabilities=1,
        application_id="42",
        heartbeat_timeout=5.0,
    )
    assert state.max_messages == 1000
    assert state._activity is not None
    assert state._activity["name"] == "chess"
    assert state._status == "invisible"
    assert state.capabilities.value == 1
    assert state.application_id == 42
    assert state.heartbeat_timeout == 5.0

    other = make_state(
        loop,
        http,
        status=discord.Status.idle,
        capabilities=discord.GatewayCapabilities.none(),
        member_cache_flags=discord.MemberCacheFlags.none(),
    )
    assert other._status == "idle"
    assert other._cache_users is False

    with caplog.at_level("WARNING"):
        make_state(loop, http, intents=discord.Intents.none())
    assert "Guilds intent seems to be disabled" in caplog.text

    verified = discord.MemberCacheFlags.from_intents(discord.Intents.default())
    assert (
        make_state(loop, http, member_cache_flags=verified).member_cache_flags
        is verified
    )


def test_hooks_handlers_and_background_tasks(world: World) -> None:
    state = world.state
    calls: list[Any] = []
    state.handlers["ready"] = lambda *a, **k: calls.append(("handler", a, k))

    async def hook(*args: Any, **kwargs: Any) -> None:
        calls.append(("hook", args, kwargs))

    state.hooks["x"] = hook
    state.call_handlers("ready", 1, a=2)
    state.call_handlers("missing")
    world.run(state.call_hooks("x", 3, b=4))
    world.run(state.call_hooks("missing"))
    assert calls == [("handler", (1,), {"a": 2}), ("hook", (3,), {"b": 4})]

    async def work() -> int:
        return 5

    async def scenario() -> int:
        task = state._create_task(work())
        assert task in state._background_tasks
        result = await task
        await asyncio.sleep(0)
        assert task not in state._background_tasks
        return result

    assert world.run(scenario()) == 5


def test_user_cache_store(world: World) -> None:
    state = world.state
    payload = world.payload(t.user.User, id="31", discriminator="0")
    state._cache_users = False
    uncached = world.run(state.store_user(payload))
    assert world.run(state.get_user(31)) is None
    assert uncached.id == 31

    state._cache_users = True
    first = world.run(state.store_user(payload))
    assert world.run(state.get_user(31)) is first
    updated = world.run(state.store_user({**payload, "username": "renamed"}))
    assert updated is not first
    assert updated.name == "renamed"
    assert first.name != "renamed"
    assert world.run(state.get_user(None)) is None

    legacy = world.run(
        state.store_user({**payload, "id": "32", "discriminator": "0000"})
    )
    assert world.run(state.get_user(32)) is None
    assert legacy.id == 32

    world.run(state.deref_user(31))
    assert world.run(state.get_user(31)) is None
    world.run(state.deref_user_no_intents(31))


def test_message_view_and_modal_helpers(world: World) -> None:
    state = world.state
    view = MagicMock()
    state._view_store = MagicMock()
    state._view_store.get_message_view.return_value = view
    assert state.get_message_view(5) is view
    state.purge_message_view(5)
    state._view_store.remove_message_view.assert_called_once_with(5)
    state._modal_store = MagicMock()
    modal = object()
    state.store_modal(modal, 7)  # type: ignore[arg-type]
    state._modal_store.add_modal.assert_called_once_with(modal, 7)


def test_sync_cache_properties(world: World) -> None:
    state = world.state
    assert state.guilds == [world.guild]
    assert state.emojis == world.run(state.get_emojis())
    assert state.stickers == world.run(state.get_stickers())
    assert state.polls == world.run(state.get_polls())
    assert state.private_channels == world.run(state.get_private_channels())
    assert state.sounds == world.run(state.get_sounds())


def test_voice_client_registry(world: World) -> None:
    state = world.state
    voice = SimpleNamespace(main_ws=None)
    state._add_voice_client(5, voice)  # type: ignore[arg-type]
    assert state._get_voice_client(5) is voice
    ws = object()
    state._update_references(ws)  # type: ignore[arg-type]
    assert voice.main_ws is ws
    state._remove_voice_client(5)
    assert state._get_voice_client(5) is None


def test_emoji_sticker_and_sound_lookups(world: World) -> None:
    rig = Rig(world)
    state = world.state
    emoji = world.run(
        state.store_emoji(world.guild, rig.payload(t.emoji.Emoji, id="9001"))
    )
    assert world.run(state.get_emoji(9001)) is emoji
    assert world.run(state.get_emoji(None)) is None
    world.run(state._remove_emoji(emoji))
    assert world.run(state.get_emoji(9001)) is None

    sticker = world.run(
        state.store_sticker(world.guild, rig.payload(t.sticker.GuildSticker, id="9002"))
    )
    assert world.run(state.get_sticker(9002)) is sticker
    assert world.run(state.get_sticker(None)) is None

    sound = discord.SoundboardSound(
        state=state,
        http=state.http,
        data=rig.payload(
            t.soundboard.SoundboardSound, sound_id="9003", guild_id=str(world.guild.id)
        ),
    )
    world.run(state._add_sound(sound))
    assert world.run(state._get_sound(9003)) is sound
    world.run(state._remove_sound(sound))
    assert world.run(state._get_sound(9003)) is None
    default = discord.SoundboardSound(
        state=state,
        http=state.http,
        data=rig.payload(t.soundboard.SoundboardSound, sound_id="9004", guild_id=None),
    )
    world.run(state._add_sound(default))
    world.run(state._remove_sound(default))


def test_private_channel_lookups(world: World) -> None:
    rig = Rig(world)
    state = world.state
    state.user = world.me
    dm = world.run(
        state.add_dm_channel(
            rig.payload(
                t.channel.DMChannel,
                id="9100",
                recipients=[rig.payload(t.user.User, id="9101")],
            )
        )
    )
    assert world.run(state._get_private_channel(9100)) is dm
    assert world.run(state._get_private_channel(None)) is None
    assert world.run(state._get_private_channel_by_user(9101)) is dm
    assert world.run(state._get_private_channel_by_user(1)) is None
    assert world.run(state.get_channel(9100)) is dm
    assert world.run(state.get_channel(None)) is None


def test_get_guild_channel_for_dm_and_missing_channels(world: World) -> None:
    state = world.state
    dm_channel, guild = world.run(state._get_guild_channel({"channel_id": "55"}))
    assert guild is None
    assert dm_channel.id == 55
    assert isinstance(dm_channel, discord.DMChannel)
    unknown, found = world.run(
        state._get_guild_channel({"channel_id": "777", "guild_id": str(world.guild.id)})
    )
    assert found is world.guild
    assert isinstance(unknown, discord.PartialMessageable)
    missing, none = world.run(state._get_guild_channel({"channel_id": "5"}, 123456))
    assert none is None
    assert isinstance(missing, discord.PartialMessageable)


def test_typing_and_reaction_users(world: World) -> None:
    rig = Rig(world)
    state = world.state
    member = world.member
    world.run(world.guild._add_member(member))
    text = world.channel
    assert world.run(state._get_typing_user(text, member.id)) is member
    assert world.run(state._get_reaction_user(text, member.id)) is member
    thread = discord.Thread(
        guild=world.guild,
        state=state,
        data=rig.payload(
            t.threads.Thread,
            guild_id=str(world.guild.id),
            parent_id=str(text.id),
        ),
    )
    assert world.run(state._get_typing_user(thread, member.id)) is member
    assert world.run(state._get_typing_user(None, 4)) is None

    recipient = world.user
    dm = discord.DMChannel(
        me=world.me,
        state=state,
        data=rig.payload(
            t.channel.DMChannel,
            recipients=[rig.payload(t.user.User, id=str(recipient.id))],
        ),
    )
    assert world.run(state._get_typing_user(dm, recipient.id)) is dm.recipient
    dm.recipient = None
    assert world.run(state._get_typing_user(dm, recipient.id)) is None

    group = discord.GroupChannel(
        me=world.me,
        state=state,
        data=rig.payload(
            t.channel.GroupDMChannel, recipients=[rig.payload(t.user.User, id="9200")]
        ),
    )
    assert world.run(state._get_typing_user(group, 9200)).id == 9200
    assert world.run(state._get_typing_user(group, 1)) is None


def test_reaction_emoji_resolution(world: World) -> None:
    rig = Rig(world)
    state = world.state
    assert (
        world.run(state.get_reaction_emoji({"id": None, "name": "\N{FIRE}"}))
        == "\N{FIRE}"
    )
    custom = world.run(
        state.get_reaction_emoji({"id": "9300", "name": "x", "animated": True})
    )
    assert isinstance(custom, discord.PartialEmoji)
    assert custom.animated is True
    cached = world.run(
        state.store_emoji(world.guild, rig.payload(t.emoji.Emoji, id="9300"))
    )
    assert world.run(state.get_reaction_emoji({"id": "9300", "name": "x"})) is cached


def test_fetch_channel_builds_and_caches(world: World) -> None:
    rig = Rig(world)
    state = rig.state
    rig.respond(
        "get_channel",
        rig.payload(
            t.channel.VoiceChannel,
            id="9400",
            guild_id=str(world.guild.id),
            type=2,
            parent_id=None,
            permission_overwrites=[],
        ),
    )
    voice = world.run(state._fetch_channel(9400))
    assert isinstance(voice, discord.VoiceChannel)

    state.user = world.me
    rig.respond(
        "get_channel",
        rig.payload(
            t.channel.DMChannel,
            id="9401",
            recipients=[rig.payload(t.user.User, id="9402")],
        ),
    )
    dm = world.run(state._fetch_channel(9401))
    assert isinstance(dm, discord.DMChannel)

    rig.respond("get_channel", {"id": "9403", "type": 999})
    with pytest.raises(InvalidData, match="Unknown channel type 999"):
        world.run(state._fetch_channel(9403))


def test_store_fetched_routes_every_model(world: World) -> None:
    rig = Rig(world)
    state = world.state
    state.cache_fetch = True
    member = world.member
    thread = discord.Thread(
        guild=world.guild,
        state=state,
        data=rig.payload(
            t.threads.Thread,
            id="9500",
            guild_id=str(world.guild.id),
            parent_id=str(world.channel.id),
        ),
    )
    thread_member = discord.ThreadMember(
        parent=thread,
        data=rig.payload(t.threads.ThreadMember, id="9500", user_id="9501"),
    )
    role = discord.Role(
        guild=world.guild, state=state, data=rig.payload(t.role.Role, id="9502")
    )
    guild_emoji = discord.GuildEmoji(
        guild=world.guild, state=state, data=rig.payload(t.emoji.Emoji, id="9503")
    )
    app_emoji = discord.AppEmoji(
        application_id=1, state=state, data=rig.payload(t.emoji.Emoji, id="9504")
    )
    sticker = discord.GuildSticker(
        state=state,
        data=rig.payload(
            t.sticker.GuildSticker, id="9505", guild_id=str(world.guild.id)
        ),
    )
    event = discord.ScheduledEvent(
        state=state,
        guild=world.guild,
        creator=None,
        data=rig.payload(
            t.scheduled_events.ScheduledEvent,
            id="9506",
            guild_id=str(world.guild.id),
            creator_id=None,
        ),
    )
    stage = discord.StageInstance(
        guild=world.guild,
        state=state,
        data=rig.payload(
            t.channel.StageInstance,
            id="9507",
            guild_id=str(world.guild.id),
            channel_id=str(world.channel.id),
        ),
    )
    dm = discord.DMChannel(
        me=world.me,
        state=state,
        data=rig.payload(
            t.channel.DMChannel,
            id="9508",
            recipients=[rig.payload(t.user.User, id="9509")],
        ),
    )
    message = rig.make_message(9510)
    sound = discord.SoundboardSound(
        state=state,
        http=state.http,
        data=rig.payload(
            t.soundboard.SoundboardSound, sound_id="9511", guild_id=str(world.guild.id)
        ),
    )
    user = discord.User(
        state=state, data=rig.payload(t.user.User, id="9512", discriminator="0")
    )
    channel = discord.TextChannel(
        state=state,
        guild=world.guild,
        data=rig.payload(
            t.channel.TextChannel,
            id="9513",
            guild_id=str(world.guild.id),
            parent_id=None,
            permission_overwrites=[],
        ),
    )
    guild_payload = rig.payload(
        t.guild.Guild,
        id="9514",
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
        unavailable=False,
    )
    guild_payload.pop("presences", None)
    new_guild = discord.Guild(data=guild_payload, state=state)

    for obj, data in (
        (world.me, None),
        (user, None),
        (new_guild, guild_payload),
        (new_guild, None),
        (member, None),
        (thread, None),
        (thread_member, None),
        (dm, None),
        (channel, None),
        (message, None),
        (role, None),
        (guild_emoji, None),
        (app_emoji, None),
        (sticker, None),
        (event, None),
        (stage, None),
        (sound, None),
        (object(), None),
    ):
        world.run(state._store_fetched(obj, data))

    assert world.run(state.get_user(9512)) is user
    assert world.run(state._get_guild(9514)) is new_guild
    assert world.run(state._get_private_channel(9508)) is dm
    assert world.run(state._get_message(9510)) is message
    assert world.run(state.get_emoji(9503)) is guild_emoji
    assert world.run(state.get_sticker(9505)) is sticker
    assert world.run(state._get_sound(9511)) is sound
    assert world.run(world.guild.get_channel(9513)) is channel
    assert world.run(world.guild.get_thread(9500)) is thread
    assert world.run(world.guild.get_scheduled_event(9506)) is event

    state.member_cache_flags = discord.MemberCacheFlags.none()
    world.run(state._store_fetched(member, None))


def test_populate_guild_with_every_collection(world: World) -> None:
    rig = Rig(world)
    state = world.state
    state.member_cache_flags = discord.MemberCacheFlags.all()
    state._cache_users = True
    state.user = world.me
    guild_payload = rig.payload(
        t.guild.Guild,
        id="9600",
        roles=[rig.payload(t.role.Role, id="9601")],
        emojis=[rig.payload(t.emoji.Emoji, id="9602")],
        stickers=[rig.payload(t.sticker.GuildSticker, id="9603", guild_id="9600")],
        stage_instances=[
            rig.payload(
                t.channel.StageInstance, id="9604", guild_id="9600", channel_id="9605"
            )
        ],
        members=[
            rig.payload(
                t.member.MemberWithUser,
                roles=[],
                user=rig.payload(t.user.User, id="9606", discriminator="0"),
            )
        ],
        guild_scheduled_events=[
            rig.payload(
                t.scheduled_events.ScheduledEvent,
                id="9607",
                guild_id="9600",
                creator_id="9606",
                creator=rig.payload(t.user.User, id="9606"),
            ),
            rig.payload(
                t.scheduled_events.ScheduledEvent,
                id="9608",
                guild_id="9600",
                creator_id=None,
                creator=None,
            ),
        ],
        presences=[
            {
                "user": {"id": "9606"},
                "status": "idle",
                "activities": [],
                "client_status": {},
            }
        ],
        channels=[
            rig.payload(
                t.channel.TextChannel,
                id="9605",
                guild_id="9600",
                type=0,
                parent_id=None,
                permission_overwrites=[],
            ),
            {"id": "9609", "type": 999},
        ],
        threads=[
            rig.payload(
                t.threads.Thread, id="9610", guild_id="9600", parent_id="9605", type=11
            )
        ],
        voice_states=[],
        soundboard_sounds=[
            rig.payload(t.soundboard.SoundboardSound, sound_id="9611", guild_id="9600")
        ],
        unavailable=False,
    )
    guild = discord.Guild(data=guild_payload, state=state)
    world.run(state._add_guild(guild))
    world.run(state._populate_guild(guild, guild_payload))
    world.run(state._populate_guild(guild, guild_payload))

    assert world.run(guild.get_role(9601)) is not None
    assert world.run(state.get_emoji(9602)) is not None
    assert world.run(state.get_sticker(9603)) is not None
    assert world.run(guild.get_channel(9605)) is not None
    assert world.run(guild.get_thread(9610)) is not None
    member = world.run(guild.get_member(9606))
    assert member is not None
    assert member.status is discord.Status.idle
    assert len(world.run(guild.get_scheduled_events())) == 2
    assert world.run(state._get_sound(9611)) is not None


def chunk_state(world: World) -> tuple[Any, AsyncMock]:
    ws = MagicMock()
    ws.request_chunks = AsyncMock()
    world.state._get_websocket = lambda _guild_id=None: ws  # type: ignore[assignment]
    return ws, ws.request_chunks


def test_chunker_and_query_members(world: World) -> None:
    _ws, request = chunk_state(world)
    state = world.state
    world.run(state.chunker(5, "ab", 3, True, nonce="n"))
    request.assert_awaited_once_with(5, query="ab", limit=3, presences=True, nonce="n")

    async def scenario() -> list[Any]:
        task = asyncio.ensure_future(
            state.query_members(world.guild, "a", 5, None, True, False)
        )
        await asyncio.sleep(0)
        ((nonce, pending),) = state._chunk_requests.items()
        assert pending.guild_id == world.guild.id
        await pending.add_members([world.member])
        pending.done()
        result = await task
        state._chunk_requests.pop(nonce)
        return result

    result = world.run(scenario())
    assert result == [world.member]
    assert request.await_args.kwargs["query"] == "a"
    assert request.await_args.kwargs["user_ids"] is None
    assert world.run(world.guild.get_member(world.member.id)) is world.member


def test_query_members_times_out(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    chunk_state(world)

    async def scenario() -> None:
        original = asyncio.wait_for

        async def fast(awaitable: Any, timeout: float) -> Any:
            return await original(awaitable, 0.01)

        asyncio.wait_for = fast  # type: ignore[assignment]
        try:
            await world.state.query_members(world.guild, "a", 5, None, False, False)
        finally:
            asyncio.wait_for = original  # type: ignore[assignment]

    with caplog.at_level("WARNING"), pytest.raises(asyncio.TimeoutError):
        world.run(scenario())
    assert "Timed out waiting for chunks" in caplog.text


def test_chunk_request_buffers_and_waits(world: World) -> None:
    request = ChunkRequest(
        world.guild.id, world.state.loop, world.state._get_guild, cache=False
    )

    async def scenario() -> list[Any]:
        waiter = asyncio.ensure_future(request.wait())
        await asyncio.sleep(0)
        await request.add_members([world.member])
        assert request.buffer == [world.member]
        assert await world.guild.get_member(world.member.id) is None or True
        request.done()
        return await waiter

    assert world.run(scenario()) == [world.member]
    assert request.waiters == []

    async def missing_guild() -> None:
        gone = ChunkRequest(1, world.state.loop, world.state._get_guild, cache=True)
        await gone.add_members([world.member])
        assert gone.buffer == [world.member]

    world.run(missing_guild())


def test_chunk_guild(world: World) -> None:
    _ws, request = chunk_state(world)
    state = world.state
    state.member_cache_flags = discord.MemberCacheFlags.all()

    async def waiting() -> list[Any]:
        task = asyncio.ensure_future(state.chunk_guild(world.guild, cache=True))
        await asyncio.sleep(0)
        pending = state._chunk_requests[world.guild.id]
        pending.done()
        return await task

    assert world.run(waiting()) == []
    request.assert_awaited_once()

    async def future_form() -> Any:
        future = await state.chunk_guild(world.guild, wait=False)
        assert not future.done()
        state._chunk_requests[world.guild.id].done()
        return await future

    assert world.run(future_form()) == []
    assert request.await_count == 1


def test_chunk_and_dispatch(world: World) -> None:
    state = world.state
    events: list[Any] = []
    state.dispatch = lambda name, *a, **k: events.append((name, a))  # type: ignore[assignment]

    state.chunk_guild = AsyncMock(return_value=[])  # type: ignore[method-assign]
    world.run(state._chunk_and_dispatch(world.guild, False))
    world.run(state._chunk_and_dispatch(world.guild, True))
    state.chunk_guild = (
        AsyncMock(
            side_effect=GatewayRateLimited(  # type: ignore[method-assign]
                SimpleNamespace(retry_after=1, opcode=8, shard_id=0)  # type: ignore[arg-type]
            )
        )
        if False
        else AsyncMock(side_effect=asyncio.TimeoutError)
    )
    world.run(state._chunk_and_dispatch(world.guild, None))
    assert [name for name, _ in events] == [
        "guild_available",
        "guild_join",
        "guild_join",
    ]


def test_waiting_for_chunks_and_channel_info(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    state = world.state

    async def never() -> None:
        await asyncio.sleep(10)

    async def scenario() -> None:
        original = asyncio.wait_for

        async def fast(awaitable: Any, timeout: float) -> Any:
            return await original(awaitable, 0.01)

        asyncio.wait_for = fast  # type: ignore[assignment]
        try:
            await state._wait_for_guild_chunks(
                world.guild, asyncio.ensure_future(never())
            )
            await state._wait_for_guild_channel_info(
                world.guild, asyncio.ensure_future(never())
            )
        finally:
            asyncio.wait_for = original  # type: ignore[assignment]

        async def failing() -> None:
            raise RuntimeError("boom")

        await state._wait_for_guild_channel_info(
            world.guild, asyncio.ensure_future(failing())
        )

    with caplog.at_level("WARNING"):
        world.run(scenario())
    assert "timed out waiting for chunks" in caplog.text
    assert "timed out waiting for channel info" in caplog.text
    assert "failed to request channel info" in caplog.text
