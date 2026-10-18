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

"""Guild role gateway event parsers."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

from ...role import Role
from ._common import get_guild_or_log

if TYPE_CHECKING:
    from ...types.raw_models import (
        GuildRoleCreateEvent,
        GuildRoleDeleteEvent,
        GuildRoleUpdateEvent,
    )
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def parse_guild_role_create(
    state: ConnectionState, data: GuildRoleCreateEvent
) -> None:
    """Handle the ``GUILD_ROLE_CREATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_ROLE_CREATE")
    if guild is None:
        return

    role_data = data["role"]
    role = Role(guild=guild, data=role_data, state=state)
    await guild._add_role(role)
    state.dispatch("guild_role_create", role)


async def parse_guild_role_delete(
    state: ConnectionState, data: GuildRoleDeleteEvent
) -> None:
    """Handle the ``GUILD_ROLE_DELETE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_ROLE_DELETE")
    if guild is None:
        return

    role_id = int(data["role_id"])
    try:
        role = await guild._remove_role(role_id)
    except KeyError:
        return
    else:
        state.dispatch("guild_role_delete", role)


async def parse_guild_role_update(
    state: ConnectionState, data: GuildRoleUpdateEvent
) -> None:
    """Handle the ``GUILD_ROLE_UPDATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_ROLE_UPDATE")
    if guild is None:
        return

    role_data = data["role"]
    role_id = int(role_data["id"])
    role = await guild.get_role(role_id)
    if role is not None:
        old_role = copy.copy(role)
        role._update(role_data)
        await state._guild_bucket("roles", guild.id).set(role.id, role)
        state.dispatch("guild_role_update", old_role, role)
