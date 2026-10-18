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

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

import discord
from discord import ChannelType, Permissions
from discord.commands import checks
from discord.errors import SyncCacheAccessError
from discord.guild import PartialGuild

if TYPE_CHECKING:
    from tests.models.context import World


def perms(**flags: bool) -> Permissions:
    return Permissions(**flags)


class FakeFailureError(Exception):
    pass


def ctx(**fields: Any) -> Any:
    channel = fields.pop(
        "channel",
        SimpleNamespace(
            type=ChannelType.text,
            permissions_for=lambda who: perms(read_messages=True),
        ),
    )
    defaults = {
        "guild": SimpleNamespace(),
        "channel": channel,
        "author": SimpleNamespace(
            guild_permissions=perms(kick_members=True),
            roles=["role"],
            get_guild_permissions=AsyncMock(return_value=perms(kick_members=True)),
            get_roles=AsyncMock(return_value=["role"]),
        ),
        "me": SimpleNamespace(guild_permissions=perms(ban_members=True), roles=["bot"]),
        "_check_failure": FakeFailureError,
    }
    return SimpleNamespace(**{**defaults, **fields})


def test_missing_permissions_and_validation() -> None:
    granted = perms(read_messages=True)
    assert checks.missing_permissions(granted, {"read_messages": True}) == []
    assert checks.missing_permissions(
        granted, {"read_messages": False, "send_messages": True}
    ) == ["read_messages", "send_messages"]
    checks.validate_permission_names(["read_messages"])
    with pytest.raises(TypeError, match="Invalid permission"):
        checks.validate_permission_names(["bogus"])


def test_has_any_role_in() -> None:
    roles = [SimpleNamespace(id=1, name="a"), SimpleNamespace(id=2, name="b")]
    assert checks.has_any_role_in(roles, [2]) is True  # type: ignore[arg-type]
    assert checks.has_any_role_in(roles, ["b"]) is True  # type: ignore[arg-type]
    assert checks.has_any_role_in(roles, [3, "c"]) is False  # type: ignore[arg-type]
    assert checks.has_any_role_in([], [1]) is False


def test_sync_permissions_of_the_author_and_the_bot() -> None:
    context = ctx()
    assert checks.author_channel_permissions(context).read_messages is True
    assert checks.bot_channel_permissions(context).read_messages is True
    assert checks.author_guild_permissions(context).kick_members is True
    assert checks.bot_guild_permissions(context).ban_members is True
    assert checks.author_roles(context) == ["role"]
    assert checks.bot_roles(context) == ["bot"]


def test_sync_permissions_in_a_dm() -> None:
    dm = ctx(guild=None, channel=SimpleNamespace(type=ChannelType.private))
    assert checks.author_channel_permissions(dm) is None
    assert checks.bot_channel_permissions(dm) is None
    assert checks.author_guild_permissions(dm) is None
    assert checks.bot_guild_permissions(dm) is None
    assert checks.author_roles(dm) is None
    assert checks.bot_roles(dm) is None


def test_bot_channel_permissions_prefer_the_interaction_permissions() -> None:
    context = ctx(app_permissions=perms(embed_links=True))
    assert checks.bot_channel_permissions(context).embed_links is True


def test_remote_caches_cannot_be_read_synchronously(world: Any) -> None:
    class Remote:
        supports_sync = False

    guild = PartialGuild(state=SimpleNamespace(cache=Remote()), id=1)  # type: ignore[arg-type]
    context = ctx(guild=guild)
    for function in (
        checks.bot_channel_permissions,
        checks.bot_guild_permissions,
        checks.bot_roles,
    ):
        with pytest.raises(SyncCacheAccessError, match="remote backend"):
            function(context)


def test_async_twins_in_a_guild(world: World) -> None:
    member = world.member
    context = ctx(
        get_channel=AsyncMock(return_value=world.channel),
        get_me=AsyncMock(return_value=member),
    )
    context.author = member

    async def scenario() -> None:
        expected = await world.channel.get_permissions_for(member)
        assert await checks.get_author_channel_permissions(context) == expected
        assert await checks.get_bot_channel_permissions(context) == expected
        guild_permissions = await member.get_guild_permissions()
        assert await checks.get_author_guild_permissions(context) == guild_permissions
        assert await checks.get_bot_guild_permissions(context) == guild_permissions
        roles = await member.get_roles()
        assert await checks.get_author_roles(context) == roles
        assert await checks.get_bot_roles(context) == roles

    world.run(scenario())


async def test_async_twins_use_the_app_permissions_when_present() -> None:
    private = SimpleNamespace(type=ChannelType.private)
    text = SimpleNamespace(type=ChannelType.text)
    app = perms(embed_links=True)
    assert (
        await checks.get_bot_channel_permissions(
            ctx(app_permissions=app, get_channel=AsyncMock(return_value=text))
        )
        is app
    )
    assert (
        await checks.get_bot_channel_permissions(
            ctx(app_permissions=app, get_channel=AsyncMock(return_value=private))
        )
        is None
    )
    assert (
        await checks.get_bot_channel_permissions(
            ctx(app_permissions=app, get_channel=AsyncMock(return_value=None))
        )
        is None
    )


async def test_async_twins_without_a_guild_or_channel() -> None:
    dm = ctx(guild=None)
    assert await checks.get_author_guild_permissions(dm) is None
    assert await checks.get_bot_guild_permissions(dm) is None
    assert await checks.get_author_roles(dm) is None
    assert await checks.get_bot_roles(dm) is None

    dm_channel = ctx(guild=None, get_channel=AsyncMock(return_value=None))
    assert await checks.get_author_channel_permissions(dm_channel) is None

    uncached = ctx(get_channel=AsyncMock(return_value=None))
    with pytest.raises(FakeFailureError, match="not cached"):
        await checks.get_author_channel_permissions(uncached)

    private = ctx(
        get_channel=AsyncMock(return_value=SimpleNamespace(type=ChannelType.private))
    )
    assert await checks.get_author_channel_permissions(private) is None

    unknown = ctx(
        get_channel=AsyncMock(return_value=SimpleNamespace(type=ChannelType.text))
    )
    with pytest.raises(FakeFailureError, match="not cached"):
        await checks.get_author_channel_permissions(unknown)


def test_group_channel_permissions(world: World) -> None:
    group = discord.GroupChannel(
        me=world.me,
        state=world.state,
        data=world.payload(
            discord.types.channel.GroupDMChannel,
            recipients=[world.payload(discord.types.user.User)],
        ),
    )
    context = ctx(get_channel=AsyncMock(return_value=group))
    context.author = discord.Object(id=group.owner_id)

    result = world.run(checks.get_author_channel_permissions(context))

    assert result.kick_members is True
