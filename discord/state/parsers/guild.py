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

"""Guild gateway event parsers."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

from ...user import User

if TYPE_CHECKING:
    from ...types.guild import Guild as GuildPayload, UnavailableGuild
    from ...types.raw_models import GuildBanAddEvent, GuildBanRemoveEvent
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def parse_guild_create(state: ConnectionState, data: GuildPayload) -> None:
    """Handle the ``GUILD_CREATE`` gateway event."""
    unavailable = data.get("unavailable")
    if unavailable is True:
        # joined a guild with unavailable == True so..
        return

    guild = await state._get_create_guild(data)

    try:
        # Notify the on_ready state, if any, that this guild is complete.
        state._ready_state.put_nowait(guild)
    except AttributeError:
        pass
    else:
        # If we're waiting for the event, put the rest on hold
        return

    # check if it requires chunking
    if await state._guild_needs_chunking(guild):
        state._create_task(state._chunk_and_dispatch(guild, unavailable))
        return

    # Dispatch available if newly available
    if unavailable is False:
        state.dispatch("guild_available", guild)
    else:
        state.dispatch("guild_join", guild)


async def parse_guild_update(state: ConnectionState, data: GuildPayload) -> None:
    """Handle the ``GUILD_UPDATE`` gateway event."""
    guild = await state._get_guild(int(data["id"]))
    if guild is not None:
        old_guild = copy.copy(guild)
        guild._from_data(data)
        await state._populate_guild(guild, data)
        await state._add_guild(guild)
        state.dispatch("guild_update", old_guild, guild)
    else:
        _log.debug(
            "GUILD_UPDATE referencing an unknown guild ID: %s. Discarding.",
            data["id"],
        )


async def parse_guild_delete(state: ConnectionState, data: UnavailableGuild) -> None:
    """Handle the ``GUILD_DELETE`` gateway event."""
    guild = await state._get_guild(int(data["id"]))
    if guild is None:
        _log.debug(
            "GUILD_DELETE referencing an unknown guild ID: %s. Discarding.",
            data["id"],
        )
        return

    if data.get("unavailable", False):
        # GUILD_DELETE with unavailable being True means that the
        # guild that was available is now currently unavailable
        guild.unavailable = True
        await state._add_guild(guild)
        state.dispatch("guild_unavailable", guild)
        return

    await state._remove_guild(guild)
    state.dispatch("guild_remove", guild)


async def parse_guild_ban_add(state: ConnectionState, data: GuildBanAddEvent) -> None:
    """Handle the ``GUILD_BAN_ADD`` gateway event."""
    # we make the assumption that GUILD_BAN_ADD is done
    # before GUILD_MEMBER_REMOVE is called
    # hence we don't remove it from cache or do anything
    # strange with it, the main purpose of this event
    # is mainly to dispatch to another event worth listening to for logging
    guild = await state._get_guild(int(data["guild_id"]))
    if guild is not None:
        try:
            user = User(data=data["user"], state=state)
        except KeyError:
            pass
        else:
            member = await guild.get_member(user.id) or user
            state.dispatch("member_ban", guild, member)


async def parse_guild_ban_remove(
    state: ConnectionState, data: GuildBanRemoveEvent
) -> None:
    """Handle the ``GUILD_BAN_REMOVE`` gateway event."""
    guild = await state._get_guild(int(data["guild_id"]))
    if guild is not None and "user" in data:
        user = await state.store_user(data["user"])
        state.dispatch("member_unban", guild, user)
