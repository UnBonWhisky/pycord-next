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

"""Channel gateway event parsers."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any, cast

from ... import utils
from ...channel import _channel_factory
from ...enums import ChannelType, try_enum

if TYPE_CHECKING:
    from collections.abc import Callable

    from ...abc import GuildChannel as GuildChannelBase, PrivateChannel
    from ...channel import GroupChannel
    from ...threads import Thread
    from ...types.channel import (
        Channel as ChannelPayload,
        GroupDMChannel as GroupChannelPayload,
    )
    from ...types.raw_models import ChannelPinsUpdateEvent
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def parse_channel_delete(state: ConnectionState, data: ChannelPayload) -> None:
    """Handle the ``CHANNEL_DELETE`` gateway event."""
    guild = await state._get_guild(utils._get_as_snowflake(data, "guild_id"))
    channel_id = int(data["id"])
    if guild is not None:
        channel = await guild.get_channel(channel_id)
        if channel is not None:
            await guild._remove_channel(channel)
            state.dispatch("guild_channel_delete", channel)


async def parse_channel_update(state: ConnectionState, data: ChannelPayload) -> None:
    """Handle the ``CHANNEL_UPDATE`` gateway event."""
    channel_type = try_enum(ChannelType, data.get("type"))
    channel_id = int(data["id"])
    if channel_type is ChannelType.group:
        # the channel is a GroupChannel
        group = cast("GroupChannel", await state._get_private_channel(channel_id))
        old_group = copy.copy(group)
        group._update_group(cast("GroupChannelPayload", data))
        await state._add_private_channel(group)
        state.dispatch("private_channel_update", old_group, group)
        return

    guild_id = utils._get_as_snowflake(data, "guild_id")
    guild = await state._get_guild(guild_id)
    if guild is not None:
        channel = await guild.get_channel(channel_id)
        if channel is not None:
            old_channel = copy.copy(channel)
            channel._update(guild, cast("Any", data))
            await guild._add_channel(channel)
            state.dispatch("guild_channel_update", old_channel, channel)
        else:
            _log.debug(
                "CHANNEL_UPDATE referencing an unknown channel ID: %s. Discarding.",
                channel_id,
            )
    else:
        _log.debug(
            "CHANNEL_UPDATE referencing an unknown guild ID: %s. Discarding.",
            guild_id,
        )


async def parse_channel_create(state: ConnectionState, data: ChannelPayload) -> None:
    """Handle the ``CHANNEL_CREATE`` gateway event."""
    factory, _ = _channel_factory(data["type"])
    if factory is None:
        _log.debug(
            "CHANNEL_CREATE referencing an unknown channel type %s. Discarding.",
            data["type"],
        )
        return

    guild_id = utils._get_as_snowflake(data, "guild_id")
    guild = await state._get_guild(guild_id)
    if guild is not None:
        # the factory can't be a DMChannel or GroupChannel here
        guild_factory = cast("Callable[..., Any]", factory)
        channel = guild_factory(guild=guild, state=state, data=data)
        await guild._add_channel(channel)
        state.dispatch("guild_channel_create", channel)
    else:
        _log.debug(
            "CHANNEL_CREATE referencing an unknown guild ID: %s. Discarding.",
            guild_id,
        )
        return


async def parse_channel_pins_update(
    state: ConnectionState, data: ChannelPinsUpdateEvent
) -> None:
    """Handle the ``CHANNEL_PINS_UPDATE`` gateway event."""
    channel_id = int(data["channel_id"])
    channel: PrivateChannel | GuildChannelBase | Thread | None
    if "guild_id" in data:
        guild = await state._get_guild(int(data["guild_id"]))
        channel = await guild._resolve_channel(channel_id) if guild else None
    else:
        guild = None
        channel = await state._get_private_channel(channel_id)

    if channel is None:
        _log.debug(
            ("CHANNEL_PINS_UPDATE referencing an unknown channel ID: %s. Discarding."),
            channel_id,
        )
        return

    last_pin_timestamp = data.get("last_pin_timestamp")
    last_pin = utils.parse_time(last_pin_timestamp) if last_pin_timestamp else None

    if guild is None:
        state.dispatch("private_channel_pins_update", channel, last_pin)
    else:
        state.dispatch("guild_channel_pins_update", channel, last_pin)
