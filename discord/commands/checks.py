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

"""Context-agnostic resolution helpers used by the command check decorators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from ..abc import GuildChannel
from ..channel import GroupChannel
from ..enums import ChannelType
from ..errors import SyncCacheAccessError
from ..guild import PartialGuild
from ..permissions import Permissions
from ..threads import Thread
from ..utils import get

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from ..channel import DMChannel
    from ..member import Member
    from ..role import Role
    from .context import BaseContext

__all__ = (
    "author_channel_permissions",
    "author_guild_permissions",
    "author_roles",
    "bot_channel_permissions",
    "bot_guild_permissions",
    "bot_roles",
    "get_author_channel_permissions",
    "get_author_guild_permissions",
    "get_author_roles",
    "get_bot_channel_permissions",
    "get_bot_guild_permissions",
    "get_bot_roles",
    "has_any_role_in",
    "missing_permissions",
    "validate_permission_names",
)


def _author_member(ctx: BaseContext) -> Member:
    # In a guild the author of a command is a member.
    return cast("Member", ctx.author)


def _bot_member(ctx: BaseContext) -> Member:
    return cast("Member", ctx.me)


def _permissions_channel(
    ctx: BaseContext,
) -> GuildChannel | Thread | GroupChannel | DMChannel:
    return cast("GuildChannel | Thread | GroupChannel | DMChannel", ctx.channel)


def _require_bot_member(ctx: BaseContext, replacement: str) -> None:
    guild = ctx.guild
    if isinstance(guild, PartialGuild) and not guild._state.cache.supports_sync:
        raise SyncCacheAccessError(
            "synchronous cache access requires the in-process cache backend; "
            f"use {replacement}() with a remote backend"
        )


def validate_permission_names(perms: Iterable[str]) -> None:
    """Raises :exc:`TypeError` if one of ``perms`` is not a permission flag."""
    invalid = set(perms) - set(Permissions.VALID_FLAGS)
    if invalid:
        raise TypeError(f"Invalid permission(s): {', '.join(invalid)}")


def missing_permissions(
    granted: Permissions, required: Mapping[str, bool]
) -> list[str]:
    """Returns the names of the permissions in ``required`` that ``granted`` does not match."""
    return [perm for perm, value in required.items() if getattr(granted, perm) != value]


def author_channel_permissions(ctx: BaseContext) -> Permissions | None:
    """Returns the permissions of the author in the channel, ``None`` in a DM."""
    channel = _permissions_channel(ctx)
    if channel.type == ChannelType.private:
        return None
    return channel.permissions_for(_author_member(ctx))


def bot_channel_permissions(ctx: BaseContext) -> Permissions | None:
    """Returns the permissions of the bot in the channel, ``None`` in a DM."""
    channel = _permissions_channel(ctx)
    if channel.type == ChannelType.private:
        return None
    app_permissions: Permissions | None = getattr(ctx, "app_permissions", None)
    if app_permissions is not None:
        return app_permissions
    _require_bot_member(ctx, "get_bot_channel_permissions")
    return channel.permissions_for(_bot_member(ctx))


def author_guild_permissions(ctx: BaseContext) -> Permissions | None:
    """Returns the guild permissions of the author, ``None`` in a DM."""
    if not ctx.guild:
        return None
    return _author_member(ctx).guild_permissions


def bot_guild_permissions(ctx: BaseContext) -> Permissions | None:
    """Returns the guild permissions of the bot, ``None`` in a DM."""
    if not ctx.guild:
        return None
    _require_bot_member(ctx, "get_bot_guild_permissions")
    return _bot_member(ctx).guild_permissions


def author_roles(ctx: BaseContext) -> list[Role] | None:
    """Returns the roles of the author, ``None`` in a DM."""
    if ctx.guild is None:
        return None
    return _author_member(ctx).roles


def bot_roles(ctx: BaseContext) -> list[Role] | None:
    """Returns the roles of the bot, ``None`` in a DM."""
    if ctx.guild is None:
        return None
    _require_bot_member(ctx, "get_bot_roles")
    return _bot_member(ctx).roles


async def _channel_permissions(ctx: BaseContext, obj: Any) -> Permissions | None:
    channel = await ctx.get_channel()
    if channel is None:
        if ctx.guild is None:
            return None
        raise ctx._check_failure("The channel of this command is not cached.")
    if channel.type == ChannelType.private:
        return None
    if isinstance(channel, GroupChannel):
        return channel.permissions_for(obj)
    if isinstance(channel, (GuildChannel, Thread)):
        return await channel.get_permissions_for(obj)
    raise ctx._check_failure("The channel of this command is not cached.")


async def get_author_channel_permissions(ctx: BaseContext) -> Permissions | None:
    """Async twin of :func:`author_channel_permissions` working with every cache backend."""
    return await _channel_permissions(ctx, ctx.author)


async def get_bot_channel_permissions(ctx: BaseContext) -> Permissions | None:
    """Async twin of :func:`bot_channel_permissions` working with every cache backend."""
    app_permissions: Permissions | None = getattr(ctx, "app_permissions", None)
    if app_permissions is not None:
        channel = await ctx.get_channel()
        if channel is None or channel.type == ChannelType.private:
            return None
        return app_permissions
    return await _channel_permissions(ctx, await ctx.get_me())


async def get_author_guild_permissions(ctx: BaseContext) -> Permissions | None:
    """Async twin of :func:`author_guild_permissions` working with every cache backend."""
    if not ctx.guild:
        return None
    return await _author_member(ctx).get_guild_permissions()


async def get_bot_guild_permissions(ctx: BaseContext) -> Permissions | None:
    """Async twin of :func:`bot_guild_permissions` working with every cache backend."""
    if not ctx.guild:
        return None
    return await cast("Member", await ctx.get_me()).get_guild_permissions()


async def get_author_roles(ctx: BaseContext) -> list[Role] | None:
    """Async twin of :func:`author_roles` working with every cache backend."""
    if ctx.guild is None:
        return None
    return await _author_member(ctx).get_roles()


async def get_bot_roles(ctx: BaseContext) -> list[Role] | None:
    """Async twin of :func:`bot_roles` working with every cache backend."""
    if ctx.guild is None:
        return None
    return await cast("Member", await ctx.get_me()).get_roles()


def has_any_role_in(roles: Iterable[Role], items: Iterable[int | str]) -> bool:
    """Whether ``roles`` contains a role matching one of the IDs or names in ``items``."""
    return any(
        get(roles, id=item) is not None
        if isinstance(item, int)
        else get(roles, name=item) is not None
        for item in items
    )
