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

import discord
from discord import types as t
from discord.flags import MemberCacheFlags
from tests.state.test_cache_wiring import message_payload
from tests.state.test_parsers import (
    CHANNEL_ID,
    GUILD_ID,
    MESSAGE_ID,
    OTHER_USER_ID,
    channel_payload,
    guild_payload,
    member_payload,
    payload,
    user_payload,
)

EMOJI_ID = 2_100_000_000_000_000_010
STICKER_ID = 2_100_000_000_000_000_011
ROLE_ID = 2_100_000_000_000_000_040


def make_client(**options: Any) -> discord.Client:
    client = discord.Client(**options)
    client.http = AsyncMock()
    client._connection.http = client.http
    return client


@pytest.fixture(params=[False, True], ids=["off", "on"])
def cache_fetch(request: pytest.FixtureRequest) -> bool:
    return request.param


@pytest.mark.asyncio
async def test_fetch_user(cache_fetch: bool) -> None:
    client = make_client(cache_fetch=cache_fetch)
    client.http.get_user.return_value = user_payload(OTHER_USER_ID)
    client._connection._cache_users = False

    user = await client.fetch_user(OTHER_USER_ID)
    cached = await client.get_user(OTHER_USER_ID)

    assert user.id == OTHER_USER_ID
    assert (cached is not None) is cache_fetch
    assert (await client.get_or_fetch(discord.User, OTHER_USER_ID)).id == OTHER_USER_ID
    assert client.http.get_user.await_count == (1 if cache_fetch else 2)


@pytest.mark.asyncio
async def test_fetch_guild_populates_the_children(cache_fetch: bool) -> None:
    client = make_client(cache_fetch=cache_fetch)
    data = guild_payload()
    role = payload(t.role.Role, id=str(GUILD_ID), position=0)
    role.pop("tags", None)
    data["roles"] = [role]
    client.http.get_guild.return_value = data

    guild = await client.fetch_guild(GUILD_ID)
    cached = await client.get_guild(GUILD_ID)

    assert guild.id == GUILD_ID
    assert (cached is not None) is cache_fetch
    roles = await guild.get_roles()
    assert [r.id for r in roles] == ([GUILD_ID] if cache_fetch else [])


@pytest.mark.asyncio
async def test_fetch_channel(cache_fetch: bool) -> None:
    client = make_client(cache_fetch=cache_fetch)
    client.http.get_channel.return_value = channel_payload()

    channel = await client.fetch_channel(CHANNEL_ID)
    cached = await client.get_channel(CHANNEL_ID)

    assert channel.id == CHANNEL_ID
    assert channel.guild_id == GUILD_ID
    assert (cached is not None) is cache_fetch
    assert (
        await client._connection._channel_guild.get(CHANNEL_ID) == GUILD_ID
    ) is cache_fetch


@pytest.mark.asyncio
async def test_fetch_message_respects_max_messages(cache_fetch: bool) -> None:
    client = make_client(cache_fetch=cache_fetch)
    client.http.get_message.return_value = message_payload(MESSAGE_ID, "fetched")
    channel = client.get_partial_messageable(CHANNEL_ID)

    message = await channel.fetch_message(MESSAGE_ID)
    cached = await client.get_message(MESSAGE_ID)

    assert message.content == "fetched"
    assert (cached is not None) is cache_fetch
    assert [m.id for m in await client.get_cached_messages()] == (
        [MESSAGE_ID] if cache_fetch else []
    )

    disabled = make_client(cache_fetch=True, max_messages=None)
    disabled.http.get_message.return_value = message_payload(MESSAGE_ID, "fetched")
    await disabled.get_partial_messageable(CHANNEL_ID).fetch_message(MESSAGE_ID)
    assert await disabled.get_message(MESSAGE_ID) is None


@pytest.mark.asyncio
async def test_fetch_member_respects_the_member_cache_flags(cache_fetch: bool) -> None:
    client = make_client(cache_fetch=cache_fetch)
    client.http.get_member.return_value = member_payload(OTHER_USER_ID, nick="n")
    guild = client._connection  # noqa: F841
    partial = discord.PartialGuild(state=client._connection, id=GUILD_ID)

    member = await partial.fetch_member(OTHER_USER_ID)
    members = client._connection._guild_bucket("members", GUILD_ID)

    assert member.nick == "n"
    assert member.guild_id == GUILD_ID
    assert (await members.contains(OTHER_USER_ID)) is (
        cache_fetch and not client._connection.member_cache_flags._empty
    )

    client._connection.member_cache_flags = MemberCacheFlags.none()
    await members.clear()
    await partial.fetch_member(OTHER_USER_ID)
    assert not await members.contains(OTHER_USER_ID)

    client._connection.member_cache_flags = MemberCacheFlags.all()
    await partial.fetch_member(OTHER_USER_ID)
    assert (await members.contains(OTHER_USER_ID)) is cache_fetch


@pytest.mark.asyncio
async def test_guild_fetchers(cache_fetch: bool) -> None:
    client = make_client(cache_fetch=cache_fetch)
    state = client._connection
    partial = discord.PartialGuild(state=state, id=GUILD_ID)
    role = payload(t.role.Role, id=str(ROLE_ID), position=1)
    role.pop("tags", None)
    emoji = payload(t.emoji.Emoji, id=str(EMOJI_ID), roles=[])
    emoji.pop("user", None)
    sticker = payload(
        t.sticker.GuildSticker, id=str(STICKER_ID), guild_id=str(GUILD_ID)
    )
    sticker.pop("user", None)
    client.http.get_roles.return_value = [role]
    client.http.get_custom_emoji.return_value = emoji
    client.http.get_guild_sticker.return_value = sticker

    fetched_roles = await partial.fetch_roles()
    fetched_emoji = await partial.fetch_emoji(EMOJI_ID)
    fetched_sticker = await partial.fetch_sticker(STICKER_ID)

    assert [r.id for r in fetched_roles] == [ROLE_ID]
    assert fetched_emoji.id == EMOJI_ID
    assert fetched_sticker.id == STICKER_ID
    assert [r.id for r in await state._guild_bucket("roles", GUILD_ID).values()] == (
        [ROLE_ID] if cache_fetch else []
    )
    assert (await client.get_emoji(EMOJI_ID) is not None) is cache_fetch
    assert (await client.get_sticker(STICKER_ID) is not None) is cache_fetch
    assert [
        e.id for e in await state._guild_bucket("guild_emojis", GUILD_ID).values()
    ] == ([EMOJI_ID] if cache_fetch else [])
