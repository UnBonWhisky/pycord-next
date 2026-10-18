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

from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiocache import SimpleMemoryCache
from aiocache.backends.redis import RedisCache
from fakeredis import FakeAsyncRedis, FakeServer

import discord
from discord.channel import PartialGuildChannel, PartialMessageable
from discord.flags import MemberCacheFlags
from tests.state.test_cache_wiring import populate
from tests.state.test_parsers import (
    CHANNEL_ID,
    GUILD_ID,
    MESSAGE_ID,
    THREAD_ID,
    channel_payload,
    guild_payload,
)


def fake_redis() -> RedisCache:
    backend = RedisCache(timeout=None)
    backend.client = FakeAsyncRedis(server=FakeServer(), max_connections=2**20)
    return backend


@pytest.mark.parametrize(
    "cls", [discord.Client, discord.Bot, discord.AutoShardedClient]
)
@pytest.mark.asyncio
async def test_clients_construct_with_and_without_cache_options(cls: Any) -> None:
    plain = cls()
    assert plain._connection.cache_fetch is False
    assert plain._connection.cache.namespace == "pycord"
    assert isinstance(plain._connection.cache.backend, SimpleMemoryCache)

    custom = cls(
        cache_backend=SimpleMemoryCache(),
        cache_namespace="bot-1",
        cache_fetch=True,
        max_messages=10,
    )
    assert custom._connection.cache_fetch is True
    assert custom._connection.cache.namespace == "bot-1"
    assert custom._connection._messages.maxlen == 10
    assert await custom.get_guilds() == []
    assert await custom.get_users() == []
    assert await custom.get_cached_messages() == []

    remote = cls(cache_backend=fake_redis())
    assert remote._connection.cache.backend.serializer.__class__.__name__ == (
        "ModelSerializer"
    )


@pytest.mark.asyncio
async def test_invalid_cache_options_raise() -> None:
    with pytest.raises(TypeError, match="cache_backend"):
        discord.Client(cache_backend=object())
    with pytest.raises(ValueError, match="namespace"):
        discord.Client(cache_namespace="a:b")
    with pytest.raises(ValueError, match="namespace"):
        discord.Client(cache_namespace="")


@pytest.mark.asyncio
async def test_namespace_prefixes_every_key() -> None:
    backend = fake_redis()
    client = discord.Client(cache_backend=backend, cache_namespace="mine")
    state = client._connection
    state.member_cache_flags = MemberCacheFlags.all()
    await populate(state)

    keys = {k.decode() async for k in backend.client.scan_iter(match="*")}
    assert keys
    assert all(key.startswith("mine:") for key in keys)


@pytest.mark.asyncio
async def test_client_collection_getters_and_iterators() -> None:
    client = discord.Client()
    state = client._connection
    state.member_cache_flags = MemberCacheFlags.all()
    await populate(state)

    assert [g.id for g in await client.get_guilds()] == [GUILD_ID]
    assert [u.id for u in await client.get_users()] == []
    assert [m.id for m in await client.get_cached_messages()] == [MESSAGE_ID]
    assert [m.id async for m in client.iter_cached_messages()] == [MESSAGE_ID]
    assert [c.id async for c in client.get_all_channels()] == [
        CHANNEL_ID,
        2_100_000_000_000_000_020,
    ]
    assert [m.id async for m in client.get_all_members()] == [2_100_000_000_000_000_006]
    assert [e.id for e in await client.get_emojis()] == [2_100_000_000_000_000_010]
    assert [e.id for e in await client.get_guild_emojis()] == [
        2_100_000_000_000_000_010
    ]
    assert await client.get_app_emojis() == []
    assert [s.id for s in await client.get_stickers()] == [2_100_000_000_000_000_011]
    assert await client.get_polls() == []
    assert await client.get_private_channels() == []
    assert [s.id for s in await client.get_sounds()] == [2_100_000_000_000_000_014]
    assert (await client.get_sound(2_100_000_000_000_000_014)) is not None
    stage = await client.get_stage_instance(2_100_000_000_000_000_020)
    assert stage is None


@pytest.mark.asyncio
async def test_guild_getters() -> None:
    client = discord.Client()
    state = client._connection
    state.member_cache_flags = MemberCacheFlags.all()
    await populate(state)
    guild = await client.get_guild(GUILD_ID)
    assert guild is not None

    assert [c.id for c in await guild.get_text_channels()] == [CHANNEL_ID]
    assert [c.id for c in await guild.get_voice_channels()] == [
        2_100_000_000_000_000_020
    ]
    assert await guild.get_stage_channels() == []
    assert await guild.get_forum_channels() == []
    assert await guild.get_categories() == []
    assert [t.id for t in await guild.get_threads()] == [THREAD_ID]
    assert (await guild.get_channel_or_thread(THREAD_ID)) is not None
    assert (await guild.get_thread(THREAD_ID)) is not None
    assert (await guild.get_channel(THREAD_ID)) is None
    assert (await guild.get_default_role()) is not None
    assert [r.id for r in await guild.get_roles()] == [GUILD_ID]
    assert [e.id for e in await guild.get_scheduled_events()] == [
        2_100_000_000_000_000_012
    ]
    assert [s.id for s in await guild.get_stage_instances()] == [
        2_100_000_000_000_000_013
    ]
    assert (await guild.get_stage_instance(2_100_000_000_000_000_013)) is not None
    assert (await guild.get_scheduled_event(2_100_000_000_000_000_012)) is not None
    assert (await guild.get_emoji(2_100_000_000_000_000_010)) is not None
    assert (await guild.get_sound(2_100_000_000_000_000_014)) is not None
    assert (await guild.get_me()) is None
    assert (await guild.get_owner()) is None
    assert (await guild.get_member_named("nobody")) is None
    assert await guild.is_chunked() is True
    assert [
        type(c).__name__ for _, chans in await guild.get_by_category() for c in chans
    ]
    voice = await guild.get_channel(2_100_000_000_000_000_020)
    assert voice is not None
    assert voice.guild_id == GUILD_ID


@pytest.mark.asyncio
async def test_partial_handles() -> None:
    client = discord.Client()
    state = client._connection
    state.member_cache_flags = MemberCacheFlags.all()
    await populate(state)

    guild = discord.PartialGuild(state=state, id=GUILD_ID)
    assert (await guild.get()).id == GUILD_ID  # type: ignore[union-attr]
    full = await guild.get()
    assert guild == full
    assert full == guild
    assert hash(guild) == hash(full)
    assert guild != discord.PartialGuild(state=state, id=GUILD_ID + 1)
    assert repr(guild) == f"<PartialGuild id={GUILD_ID}>"
    assert guild.created_at is not None
    assert hasattr(guild, "ban")
    assert hasattr(guild, "create_text_channel")
    assert discord.PartialGuild(state=state, id=1).shard_id == 0

    channel = PartialGuildChannel(state=state, id=CHANNEL_ID, guild_id=GUILD_ID)
    assert (await channel.get()).id == CHANNEL_ID  # type: ignore[union-attr]
    assert channel.guild.id == GUILD_ID
    thread = PartialGuildChannel(state=state, id=THREAD_ID, guild_id=GUILD_ID)
    assert (await thread.get()).id == THREAD_ID  # type: ignore[union-attr]

    messageable = PartialMessageable(state=state, id=CHANNEL_ID)
    assert (await messageable.get()).id == CHANNEL_ID  # type: ignore[union-attr]
    partial_message = messageable.get_partial_message(MESSAGE_ID)
    assert (await partial_message.get()).id == MESSAGE_ID  # type: ignore[union-attr]
    assert await PartialMessageable(state=state, id=1).get() is None


@pytest.mark.asyncio
async def test_relationship_attributes_memory_backend() -> None:
    client = discord.Client()
    state = client._connection
    state.member_cache_flags = MemberCacheFlags.all()
    await populate(state)

    message = await state._get_message(MESSAGE_ID)
    assert message is not None
    assert message.channel_id == CHANNEL_ID
    assert message.guild_id == GUILD_ID
    assert message.channel is await state.get_channel(CHANNEL_ID)
    assert message.guild is await state._get_guild(GUILD_ID)
    assert not isinstance(message.channel, PartialMessageable)
    assert not isinstance(message.guild, discord.PartialGuild)

    await state._guild_bucket("channels", GUILD_ID).pop(CHANNEL_ID)
    await state._guilds.pop(GUILD_ID)
    assert isinstance(message.channel, PartialMessageable)
    assert message.channel.id == CHANNEL_ID
    assert (await message.channel.get()) is None
    assert isinstance(message.guild, discord.PartialGuild)
    assert message.guild.id == GUILD_ID


@pytest.mark.asyncio
async def test_relationship_attributes_remote_backend_are_partial_handles() -> None:
    client = discord.Client(cache_backend=fake_redis())
    state = client._connection
    state.member_cache_flags = MemberCacheFlags.all()
    await populate(state)

    message = await state._get_message(MESSAGE_ID)
    assert message is not None
    assert isinstance(message.channel, PartialMessageable)
    assert message.channel.id == CHANNEL_ID
    assert isinstance(message.guild, discord.PartialGuild)
    assert message.guild.id == GUILD_ID
    assert (await message.channel.get()).id == CHANNEL_ID  # type: ignore[union-attr]
    assert (await message.get_channel()).id == CHANNEL_ID  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_partial_fetches_use_the_api() -> None:
    client = discord.Client()
    client.http = AsyncMock()
    state = client._connection
    state.http = client.http
    client.http.get_guild.return_value = guild_payload()
    client.http.get_channel.return_value = channel_payload()

    guild = await discord.PartialGuild(state=state, id=GUILD_ID).fetch()
    channel = await PartialMessageable(state=state, id=CHANNEL_ID).fetch()
    guild_channel = await PartialGuildChannel(
        state=state, id=CHANNEL_ID, guild_id=GUILD_ID
    ).fetch()

    assert guild.id == GUILD_ID
    assert channel.id == CHANNEL_ID
    assert guild_channel.id == CHANNEL_ID
    assert await state._get_guild(GUILD_ID) is None
