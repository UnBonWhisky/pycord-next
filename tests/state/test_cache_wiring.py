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
from aiocache.backends.redis import RedisCache
from fakeredis import FakeAsyncRedis, FakeServer

from discord import types as t
from discord.channel import DMChannel
from discord.flags import MemberCacheFlags
from discord.state import AutoShardedConnectionState, ChunkRequest
from tests.state.conftest import build_state
from tests.state.test_parsers import (
    CHANNEL_ID,
    GUILD_ID,
    MESSAGE_ID,
    OTHER_USER_ID,
    THREAD_ID,
    USER_ID,
    Recorder,
    channel_payload,
    guild_payload,
    member_payload,
    payload,
    ready,
    thread_payload,
    user_payload,
)

if TYPE_CHECKING:
    from discord.http import HTTPClient
    from discord.state import ConnectionState

VOICE_ID = 2_100_000_000_000_000_020
ROLE_ID = GUILD_ID
EMOJI_ID = 2_100_000_000_000_000_010
STICKER_ID = 2_100_000_000_000_000_011
EVENT_ID = 2_100_000_000_000_000_012
STAGE_ID = 2_100_000_000_000_000_013
SOUND_ID = 2_100_000_000_000_000_014
OTHER_GUILD_ID = 2_100_000_000_000_000_030
OTHER_CHANNEL_ID = 2_100_000_000_000_000_031

SCOPED_KINDS = {
    "channels",
    "threads",
    "members",
    "roles",
    "voice_states",
    "scheduled_events",
    "stage_instances",
    "guild_sounds",
    "guild_emojis",
    "guild_stickers",
}
GLOBAL_KINDS = {
    "users",
    "guilds",
    "emojis",
    "app_emojis",
    "stickers",
    "polls",
    "sounds",
    "private_channels",
    "private_channels_by_user",
    "messages",
    "channel_guild",
}


def rich_guild_payload() -> dict[str, Any]:
    data = guild_payload()
    role = payload(t.role.Role, id=str(ROLE_ID), position=0)
    role.pop("tags", None)
    emoji = payload(t.emoji.Emoji, id=str(EMOJI_ID), roles=[])
    emoji.pop("user", None)
    sticker = payload(
        t.sticker.GuildSticker, id=str(STICKER_ID), guild_id=str(GUILD_ID)
    )
    sticker.pop("user", None)
    voice = payload(
        t.channel.VoiceChannel,
        id=str(VOICE_ID),
        guild_id=str(GUILD_ID),
        type=2,
        parent_id=None,
        permission_overwrites=[],
    )
    data.update(
        roles=[role],
        emojis=[emoji],
        stickers=[sticker],
        channels=[channel_payload(), voice],
    )
    return data


def message_payload(message_id: int, content: str) -> dict[str, Any]:
    message = payload(
        t.message.Message,
        id=str(message_id),
        channel_id=str(CHANNEL_ID),
        guild_id=str(GUILD_ID),
        author=user_payload(OTHER_USER_ID),
        content=content,
        type=0,
        edited_timestamp=None,
        mentions=[],
        mention_roles=[],
        reactions=[],
        attachments=[],
        embeds=[],
        sticker_items=[],
        components=[],
    )
    for key in (
        "message_reference",
        "referenced_message",
        "message_snapshots",
        "thread",
        "poll",
        "member",
        "call",
        "interaction",
        "interaction_metadata",
    ):
        message.pop(key, None)
    return message


async def populate(state: ConnectionState) -> Recorder:
    recorder = Recorder()
    state.dispatch = recorder
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](rich_guild_payload())
    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick="old"), "guild_id": str(GUILD_ID)}
    )
    await state.parsers["THREAD_CREATE"]({**thread_payload(), "newly_created": True})
    message = message_payload(MESSAGE_ID, "hello")
    await state.parsers["MESSAGE_CREATE"](message)
    event = payload(
        t.scheduled_events.ScheduledEvent,
        id=str(EVENT_ID),
        guild_id=str(GUILD_ID),
        channel_id=str(VOICE_ID),
        entity_type=2,
        entity_metadata=None,
        scheduled_end_time=None,
        status=1,
    )
    event.pop("creator", None)
    event["creator_id"] = None
    await state.parsers["GUILD_SCHEDULED_EVENT_CREATE"](event)
    await state.parsers["STAGE_INSTANCE_CREATE"](
        payload(
            t.channel.StageInstance,
            id=str(STAGE_ID),
            guild_id=str(GUILD_ID),
            channel_id=str(VOICE_ID),
            guild_scheduled_event_id=None,
        )
    )
    sound = payload(
        t.soundboard.SoundboardSound,
        sound_id=str(SOUND_ID),
        guild_id=str(GUILD_ID),
        emoji_id=None,
    )
    sound.pop("user", None)
    await state.parsers["GUILD_SOUNDBOARD_SOUND_CREATE"](sound)
    voice_state = payload(
        t.voice.VoiceState,
        user_id=str(OTHER_USER_ID),
        guild_id=str(GUILD_ID),
        channel_id=str(VOICE_ID),
        request_to_speak_timestamp=None,
    )
    voice_state.pop("member", None)
    await state.parsers["VOICE_STATE_UPDATE"](voice_state)
    return recorder


def scope_of(prefix: str) -> tuple[str, str | None]:
    parts = prefix.split(":")
    return parts[1], parts[2] if len(parts) > 2 else None


def bucket_kinds(state: ConnectionState) -> set[str]:
    return {scope_of(prefix)[0] for prefix in state._store._buckets}


@pytest.mark.asyncio
async def test_every_bucket_of_the_conventions_is_created(
    state: ConnectionState,
) -> None:
    state.member_cache_flags = MemberCacheFlags.all()
    await populate(state)
    await state.add_dm_channel(
        payload(
            t.channel.DMChannel,
            id=str(OTHER_CHANNEL_ID),
            recipients=[user_payload(OTHER_USER_ID)],
            type=1,
        )
    )
    await state.parsers["THREAD_MEMBER_UPDATE"](
        {
            "id": str(THREAD_ID),
            "guild_id": str(GUILD_ID),
            "user_id": str(OTHER_USER_ID),
            "join_timestamp": "2024-01-01T00:00:00+00:00",
            "flags": 0,
        }
    )

    kinds = bucket_kinds(state)
    assert (SCOPED_KINDS | GLOBAL_KINDS | {"thread_members"}) <= kinds
    scoped = {
        kind
        for prefix in state._store._buckets
        for kind, scope in [scope_of(prefix)]
        if scope is not None
    }
    assert scoped == SCOPED_KINDS | {"thread_members"}


@pytest.mark.asyncio
async def test_bucket_limits(loop: asyncio.AbstractEventLoop, http: HTTPClient) -> None:
    state = build_state(loop, http, max_messages=7)

    assert state._messages is not None
    assert state._messages.maxlen == 7
    assert state._messages.lru is False
    assert state._private_channels.maxlen == 128
    assert state._private_channels.lru is True
    for bucket in (
        state._users,
        state._guilds,
        state._emojis,
        state._app_emojis,
        state._stickers,
        state._polls,
        state._sounds,
        state._channel_guild,
        state._private_channels_by_user,
    ):
        assert bucket.maxlen is None
        assert bucket.lru is False

    await populate(state)
    for kind in SCOPED_KINDS:
        bucket = state._guild_bucket(kind, GUILD_ID)
        assert bucket.maxlen is None
        assert bucket.lru is False


@pytest.mark.asyncio
async def test_messages_bucket_is_disabled_without_max_messages(
    loop: asyncio.AbstractEventLoop, http: HTTPClient
) -> None:
    state = build_state(loop, http, max_messages=None)
    await populate(state)

    assert state._messages is None
    assert await state._get_message(MESSAGE_ID) is None
    assert await state.get_cached_messages() == []
    assert "messages" not in bucket_kinds(state)


@pytest.mark.asyncio
async def test_max_messages_evicts_the_oldest_message(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, backend_kind: str
) -> None:
    state = build_state(loop, http, backend_kind, max_messages=2)
    recorder = await populate(state)
    assert recorder.last("message")
    first = MESSAGE_ID

    for offset in (1, 2):
        message = message_payload(first + offset, "next")
        await state.parsers["MESSAGE_CREATE"](message)

    assert await state._get_message(first) is None
    assert [m.id for m in await state.get_cached_messages()] == [first + 1, first + 2]


@pytest.mark.asyncio
async def test_private_channels_are_a_128_entry_lru(
    state: ConnectionState,
) -> None:
    await ready(state)
    assert state.user is not None

    for index in range(128):
        await state.add_dm_channel(
            payload(
                t.channel.DMChannel,
                id=str(5_000 + index),
                recipients=[user_payload(10_000 + index)],
                type=1,
            )
        )
    assert await state._private_channels.count() == 128

    touched = await state._get_private_channel(5_000)
    assert isinstance(touched, DMChannel)

    await state.add_dm_channel(
        payload(
            t.channel.DMChannel,
            id=str(6_000),
            recipients=[user_payload(20_000)],
            type=1,
        )
    )

    assert await state._private_channels.count() == 128
    assert await state._get_private_channel(5_000) is not None
    assert await state._get_private_channel(5_001) is None
    assert await state._get_private_channel_by_user(10_001) is None
    assert await state._get_private_channel_by_user(10_000) is not None
    assert await state._get_private_channel_by_user(20_000) is not None
    assert await state._private_channels_by_user.count() == 128

    channel = await state._get_private_channel(6_000)
    assert channel is not None
    await state._remove_private_channel(channel)
    assert await state._get_private_channel_by_user(20_000) is None


@pytest.mark.asyncio
async def test_member_cache_flags_are_respected(state: ConnectionState) -> None:
    recorder = Recorder()
    state.dispatch = recorder
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None

    state.member_cache_flags = MemberCacheFlags.none()
    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick="a"), "guild_id": str(GUILD_ID)}
    )
    assert await guild.get_member(OTHER_USER_ID) is None
    assert recorder.last("member_join")

    state.member_cache_flags = MemberCacheFlags.all()
    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick="a"), "guild_id": str(GUILD_ID)}
    )
    member = await guild.get_member(OTHER_USER_ID)
    assert member is not None
    assert [m.id async for m in guild.iter_members()] == [OTHER_USER_ID]


@pytest.mark.asyncio
async def test_guild_delete_drops_the_scoped_buckets(
    cache_state: ConnectionState,
) -> None:
    state = cache_state
    await populate(state)
    other = guild_payload()
    other["id"] = str(OTHER_GUILD_ID)
    other["channels"] = [
        {
            **channel_payload(),
            "id": str(OTHER_CHANNEL_ID),
            "guild_id": str(OTHER_GUILD_ID),
        }
    ]
    await state.parsers["GUILD_CREATE"](other)
    assert await state._channel_guild.count() == 4

    await state.parsers["GUILD_DELETE"]({"id": str(GUILD_ID)})

    assert await state._get_guild(GUILD_ID) is None
    assert await state._get_message(MESSAGE_ID) is None
    assert await state._emojis.count() == 0
    assert await state._stickers.count() == 0
    assert await state._sounds.count() == 0
    assert await state._channel_guild.keys() == [OTHER_CHANNEL_ID]
    assert await state.get_channel(CHANNEL_ID) is None
    assert await state.get_channel(OTHER_CHANNEL_ID) is not None
    for prefix in state._store._buckets:
        kind, scope = scope_of(prefix)
        if kind in SCOPED_KINDS:
            assert scope == str(OTHER_GUILD_ID)
    assert not [
        k for k in state._store._buckets if k.startswith("pycord:thread_members")
    ]
    backend: Any = state._store.backend
    if hasattr(backend, "_cache"):
        assert not [k for k in backend._cache if f":{GUILD_ID}:" in k]
    else:
        keys = {k.decode() async for k in backend.client.scan_iter(match="*")}
        assert not [k for k in keys if f":{GUILD_ID}:" in k or f":{THREAD_ID}:" in k]


@pytest.mark.asyncio
async def test_get_channel_uses_the_channel_guild_index(
    state: ConnectionState,
) -> None:
    await populate(state)
    backend: Any = state._store.backend
    original = backend.get
    reads: list[str] = []

    async def spy(key: str, *args: Any, **kwargs: Any) -> Any:
        reads.append(key)
        return await original(key, *args, **kwargs)

    backend.get = spy
    try:
        channel = await state.get_channel(CHANNEL_ID)
        thread = await state.get_channel(THREAD_ID)
        voice = await state.get_channel(VOICE_ID)
        missing = await state.get_channel(1)
    finally:
        del backend.get

    assert channel is not None
    assert channel.id == CHANNEL_ID
    assert thread is not None
    assert thread.id == THREAD_ID
    assert voice is not None
    assert missing is None
    assert await state._channel_guild.get(THREAD_ID) == GUILD_ID
    assert not [key for key in reads if key.startswith("pycord:guilds")]
    assert len(reads) <= 3 * 4


@pytest.mark.asyncio
async def test_threads_leave_the_index_when_archived(
    state: ConnectionState,
) -> None:
    await populate(state)

    await state.parsers["THREAD_UPDATE"](thread_payload(name="x", archived=True))

    assert await state.get_channel(THREAD_ID) is None
    assert await state._channel_guild.get(THREAD_ID) is None


@pytest.mark.asyncio
async def test_same_gateway_sequence_on_memory_and_redis(
    loop: asyncio.AbstractEventLoop, http: HTTPClient
) -> None:
    snapshots = []
    for kind in ("memory", "redis"):
        state = build_state(loop, http, kind)
        recorder = await populate(state)
        guild = await state._get_guild(GUILD_ID)
        assert guild is not None

        await state.parsers["GUILD_MEMBER_UPDATE"](
            {
                **member_payload(OTHER_USER_ID, nick="new"),
                "guild_id": str(GUILD_ID),
            }
        )
        await state.parsers["GUILD_ROLE_CREATE"](
            {
                "guild_id": str(GUILD_ID),
                "role": payload(t.role.Role, id="2100000000000000040", position=1),
            }
        )
        await state.parsers["CHANNEL_UPDATE"]({**channel_payload(), "name": "renamed"})
        await state.parsers["MESSAGE_UPDATE"](message_payload(MESSAGE_ID, "edited"))

        member = await guild.get_member(OTHER_USER_ID)
        channel = await guild.get_channel(CHANNEL_ID)
        message = await state._get_message(MESSAGE_ID)
        assert member is not None
        assert channel is not None
        assert message is not None
        voice = await guild.get_channel(VOICE_ID)
        snapshots.append(
            {
                "events": recorder.names(),
                "member": (member.id, member.nick, member.guild_id),
                "channel": (channel.id, channel.name, channel.guild_id),
                "channel_last_message": channel.last_message_id,
                "message": (message.id, message.content, message.channel_id),
                "author": message.author.id,
                "roles": [r.id for r in await guild.get_roles()],
                "emojis": [e.id for e in await guild.get_emojis()],
                "stickers": [s.id for s in await guild.get_stickers()],
                "threads": [th.id for th in await guild.get_threads()],
                "thread_members": [
                    m.id
                    for m in await (await guild.get_thread(THREAD_ID)).get_members()  # type: ignore[union-attr]
                ],
                "events_cached": [e.id for e in await guild.get_scheduled_events()],
                "stages": [s.id for s in await guild.get_stage_instances()],
                "sounds": [s.id for s in await guild.get_sounds()],
                "voice_states": sorted(
                    await state._guild_bucket("voice_states", GUILD_ID).keys()
                ),
                "voice_channel": voice.id if voice is not None else None,
                "guild_name": guild.name,
            }
        )
        if kind == "redis":
            assert await state._get_guild(GUILD_ID) is not guild

    assert snapshots[0] == snapshots[1]


@pytest.mark.asyncio
async def test_chunk_requests_fill_the_member_cache(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, backend_kind: str
) -> None:
    state = build_state(loop, http, backend_kind)
    state.dispatch = Recorder()
    await ready(state)
    await state._guilds.clear()
    await state.parsers["GUILD_CREATE"](guild_payload())
    request = ChunkRequest(GUILD_ID, loop, state._get_guild, cache=True)
    state._chunk_requests[request.nonce] = request
    waiter = request.get_future()

    await state.parsers["GUILD_MEMBERS_CHUNK"](
        {
            "guild_id": str(GUILD_ID),
            "members": [member_payload(OTHER_USER_ID, nick="chunked")],
            "chunk_index": 0,
            "chunk_count": 1,
            "nonce": request.nonce,
        }
    )

    members = await waiter
    assert [m.id for m in members] == [OTHER_USER_ID]
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    cached = await guild.get_member(OTHER_USER_ID)
    assert cached is not None
    assert cached.nick == "chunked"
    assert request.nonce not in state._chunk_requests


@pytest.mark.asyncio
async def test_ready_waits_for_the_guild_stream_then_dispatches(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, backend_kind: str
) -> None:
    state = build_state(
        loop,
        http,
        backend_kind,
        guild_ready_timeout=0.05,
        cache_default_sounds=False,
    )
    recorder = Recorder()
    state.dispatch = recorder
    await state.parsers["READY"](
        {
            "user": {**user_payload(), "bot": True},
            "guilds": [{"id": str(GUILD_ID), "unavailable": True}],
            "application": {"id": str(OTHER_USER_ID), "flags": 0},
        }
    )
    task = state._ready_task
    assert task is not None
    assert recorder.names() == ["connect"]

    await state.parsers["GUILD_CREATE"](rich_guild_payload())
    await asyncio.wait_for(task, timeout=5)

    assert recorder.names() == ["connect", "guild_available", "ready"]
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    assert [c.id for c in await guild.get_channels()] == [CHANNEL_ID, VOICE_ID]


@pytest.mark.asyncio
async def test_ready_clears_the_previous_session(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, backend_kind: str
) -> None:
    state = build_state(loop, http, backend_kind)
    await populate(state)
    assert await state._get_message(MESSAGE_ID) is not None

    await ready(state)

    assert await state._get_message(MESSAGE_ID) is None
    assert await state._channel_guild.count() == 0
    assert [g.id for g in await state.get_guilds()] == [GUILD_ID]
    assert await state._guild_bucket("channels", GUILD_ID).count() == 0


@pytest.mark.asyncio
async def test_auto_sharded_ready_stores_the_user_and_guilds(
    loop: asyncio.AbstractEventLoop, http: HTTPClient, backend_kind: str
) -> None:
    options: dict[str, Any] = {}
    if backend_kind == "redis":
        backend = RedisCache(timeout=None)
        backend.client = FakeAsyncRedis(server=FakeServer(), max_connections=2**20)
        options["cache_backend"] = backend
    state = AutoShardedConnectionState(
        dispatch=lambda *_args, **_kwargs: None,
        handlers={},
        hooks={},
        http=http,
        loop=loop,
        cache_default_sounds=False,
        **options,
    )
    recorder = Recorder()
    state.dispatch = recorder

    await state.parsers["READY"](
        {
            "user": {**user_payload(), "bot": True},
            "guilds": [{"id": str(GUILD_ID), "unavailable": True}],
            "application": {"id": str(OTHER_USER_ID), "flags": 0},
            "__shard_id__": 3,
        }
    )
    task = state._ready_task
    assert task is not None
    task.cancel()
    await state.parsers["RESUMED"]({"__shard_id__": 3})

    assert recorder.names() == ["connect", "shard_connect", "resumed", "shard_resumed"]
    assert recorder.last("shard_connect") == (3,)
    assert state.user is not None
    assert (await state.get_user(USER_ID)) is not None
    assert [g.id for g in await state.get_guilds()] == [GUILD_ID]


@pytest.mark.asyncio
async def test_scheduled_event_subscriptions_find_the_member_and_event(
    cache_state: ConnectionState,
) -> None:
    state = cache_state
    recorder = await populate(state)
    await state.parsers["GUILD_MEMBER_ADD"](
        {**member_payload(OTHER_USER_ID, nick="old"), "guild_id": str(GUILD_ID)}
    )
    guild = await state._get_guild(GUILD_ID)
    assert guild is not None
    before = (await guild.get_scheduled_event(EVENT_ID)).subscriber_count  # type: ignore[union-attr]

    await state.parsers["GUILD_SCHEDULED_EVENT_USER_ADD"](
        {
            "guild_scheduled_event_id": str(EVENT_ID),
            "user_id": str(OTHER_USER_ID),
            "guild_id": str(GUILD_ID),
        }
    )

    event, member = recorder.last("scheduled_event_user_add")
    assert event.id == EVENT_ID
    assert member.id == OTHER_USER_ID
    assert event.subscriber_count == before + 1
    assert (await guild.get_scheduled_event(EVENT_ID)).subscriber_count == before + 1  # type: ignore[union-attr]
