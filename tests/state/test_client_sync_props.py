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

"""Client synchronous cache properties (decisions D11/D12)."""

from __future__ import annotations

import pytest
from aiocache import RedisCache
from fakeredis import FakeAsyncRedis

import discord

PROPERTIES = {
    "guilds": "get_guilds",
    "users": "get_users",
    "emojis": "get_emojis",
    "guild_emojis": "get_guild_emojis",
    "app_emojis": "get_app_emojis",
    "stickers": "get_stickers",
    "polls": "get_polls",
    "sounds": "get_sounds",
    "private_channels": "get_private_channels",
    "cached_messages": "get_cached_messages",
}


@pytest.mark.parametrize(("prop", "getter"), sorted(PROPERTIES.items()))
async def test_sync_property_matches_async_twin(prop: str, getter: str) -> None:
    client = discord.Client()
    assert list(getattr(client, prop)) == list(await getattr(client, getter)())


async def test_sync_property_reads_live_cache() -> None:
    client = discord.Client()
    sentinel = object()
    await client._connection._guilds.set(1, sentinel)
    assert client.guilds == [sentinel]


@pytest.mark.parametrize("prop", sorted(PROPERTIES))
async def test_sync_property_raises_with_remote_backend(prop: str) -> None:
    backend = RedisCache(timeout=None)
    backend.client = FakeAsyncRedis()
    client = discord.Client(cache_backend=backend)
    with pytest.raises(discord.SyncCacheAccessError):
        getattr(client, prop)
