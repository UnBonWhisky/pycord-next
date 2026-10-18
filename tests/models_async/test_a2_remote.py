"""
The MIT License (MIT)

Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from discord.channel import PartialGuildChannel
from discord.errors import SyncCacheAccessError
from discord.guild import Guild, PartialGuild
from tests.models.context import World
from tests.models_async.a2_support import Scene
from tests.state.conftest import build_state

if TYPE_CHECKING:
    import asyncio

    from discord.http import HTTPClient

GUILD_PROPERTIES = {
    "channels": "get_channels",
    "threads": "get_threads",
    "voice_channels": "get_voice_channels",
    "stage_channels": "get_stage_channels",
    "forum_channels": "get_forum_channels",
    "text_channels": "get_text_channels",
    "categories": "get_categories",
    "sounds": "get_sounds",
    "members": "get_members",
    "premium_subscribers": "get_premium_subscribers",
    "me": "get_me",
    "owner": "get_owner",
    "roles": "get_roles",
    "default_role": "get_default_role",
    "premium_subscriber_role": "get_premium_subscriber_role",
    "self_role": "get_self_role",
    "stage_instances": "get_stage_instances",
    "scheduled_events": "get_scheduled_events",
    "system_channel": "get_system_channel",
    "rules_channel": "get_rules_channel",
    "public_updates_channel": "get_public_updates_channel",
    "chunked": "is_chunked",
    "by_category": "get_by_category",
}
TUPLE_PROPERTIES = {"emojis": "get_emojis", "stickers": "get_stickers"}


@pytest.fixture
def remote(loop: asyncio.AbstractEventLoop, http: HTTPClient) -> Scene:
    return Scene(World(build_state(loop, http, "redis")))


@pytest.fixture
def memory(world: World) -> Scene:
    return Scene(world)


def read(guild: Guild, name: str) -> Any:
    value = getattr(guild, name)
    return value() if callable(value) else value


def prepare(scene: Scene) -> Guild:
    guild = scene.guild
    channel_id = scene.world.channel.id
    guild._system_channel_id = channel_id
    guild._rules_channel_id = channel_id
    guild._public_updates_channel_id = channel_id
    guild._member_count = 1
    scene.add_member(1)
    scene.run(
        scene.state._guild_bucket("channels", guild.id).set(
            channel_id, scene.world.channel
        )
    )
    return guild


def same(first: Any, second: Any) -> bool:
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(
            same(a, b) for a, b in zip(first, second, strict=True)
        )
    if isinstance(first, tuple) and isinstance(second, tuple):
        return len(first) == len(second) and all(
            same(a, b) for a, b in zip(first, second, strict=True)
        )
    return first is second or first == second


@pytest.mark.parametrize(
    ("name", "getter"), [*GUILD_PROPERTIES.items(), *TUPLE_PROPERTIES.items()]
)
def test_memory_guild_accessors_equal_their_async_twin(
    memory: Scene, name: str, getter: str
) -> None:
    guild = prepare(memory)
    memory.add_role(10, position=1)
    expected = memory.run(getattr(guild, getter)())
    if name in TUPLE_PROPERTIES:
        expected = tuple(expected)
    assert same(read(guild, name), expected)


def test_memory_guild_accessors_are_not_empty(memory: Scene) -> None:
    guild = prepare(memory)
    assert len(guild.members) == 1
    assert len(guild.roles) == 1
    assert guild.default_role == memory.everyone
    assert guild.system_channel is memory.world.channel
    assert guild.chunked is True
    assert guild.me is None


@pytest.mark.parametrize(
    "name", [*GUILD_PROPERTIES, *TUPLE_PROPERTIES], ids=lambda n: n
)
def test_remote_guild_accessors_raise(remote: Scene, name: str) -> None:
    guild = prepare(remote)
    with pytest.raises(SyncCacheAccessError):
        read(guild, name)


@pytest.mark.parametrize(
    ("name", "getter"), [*GUILD_PROPERTIES.items(), *TUPLE_PROPERTIES.items()]
)
def test_remote_async_twins_work(remote: Scene, name: str, getter: str) -> None:
    guild = prepare(remote)
    del name
    remote.run(getattr(guild, getter)())


def test_afk_channel_is_the_channel_or_a_handle(memory: Scene, remote: Scene) -> None:
    for scene in (memory, remote):
        guild = scene.guild
        guild.afk_channel_id = scene.world.channel.id
    assert isinstance(memory.guild.afk_channel, PartialGuildChannel)
    assert isinstance(remote.guild.afk_channel, PartialGuildChannel)
    memory.run(
        memory.state._guild_bucket("channels", memory.guild.id).set(
            memory.world.channel.id, memory.world.channel
        )
    )
    assert memory.guild.afk_channel is memory.world.channel
    assert memory.run(memory.guild.get_afk_channel()) is memory.world.channel


def test_afk_channel_without_cached_channel_is_a_handle(memory: Scene) -> None:
    memory.guild.afk_channel_id = 123
    handle = memory.guild.afk_channel
    assert isinstance(handle, PartialGuildChannel)
    assert handle.id == 123


def test_relationship_attributes_return_the_guild_or_a_handle(
    memory: Scene, remote: Scene
) -> None:
    member = memory.add_member(1)
    role = memory.everyone
    assert member.guild is memory.guild
    assert role.guild is memory.guild
    remote_member = remote.add_member(1)
    assert isinstance(remote_member.guild, PartialGuild)
    assert isinstance(remote.everyone.guild, PartialGuild)
    assert remote_member.guild.id == remote.guild.id
    assert remote.run(remote_member.guild.get()) == remote.guild


def test_uncached_guild_falls_back_to_a_handle(memory: Scene) -> None:
    member = memory.add_member(1)
    memory.run(memory.state._remove_guild(memory.guild))
    assert isinstance(member.guild, PartialGuild)
    assert isinstance(memory.everyone.guild, PartialGuild)


def test_remote_member_role_and_user_accessors_raise(remote: Scene) -> None:
    remote.add_role(10, position=1)
    member = remote.add_member(1, roles=[10])
    for name in (
        "roles",
        "top_role",
        "guild_permissions",
        "voice",
        "colour",
        "colours",
        "color",
        "colors",
    ):
        with pytest.raises(SyncCacheAccessError):
            getattr(member, name)
    with pytest.raises(SyncCacheAccessError):
        member.get_role(10)
    with pytest.raises(SyncCacheAccessError):
        _ = remote.everyone.members
    with pytest.raises(SyncCacheAccessError):
        remote.everyone.is_assignable()
    with pytest.raises(SyncCacheAccessError):
        _ = member._user.dm_channel
    with pytest.raises(SyncCacheAccessError):
        _ = member._user.mutual_guilds


def test_remote_member_role_and_user_async_twins_work(remote: Scene) -> None:
    role = remote.add_role(10, position=1)
    member = remote.add_member(1, roles=[10])
    assert remote.run(member.get_roles()) == [remote.everyone, role]
    assert remote.run(member.get_top_role()) == role
    assert remote.run(member.get_guild_permissions()) is not None
    assert remote.run(member.get_voice_state()) is None
    assert remote.run(member.get_colour()).value == role.colours.primary.value
    assert remote.run(role.get_members()) == [member]
    assert remote.run(member.get_dm_channel()) is None
    assert remote.run(member.get_mutual_guilds()) == [remote.guild]
