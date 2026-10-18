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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..abc import GuildChannel, MessageableChannel
    from ..emoji import AppEmoji, GuildEmoji
    from ..guild import Guild
    from ..state import ConnectionState
    from ..threads import Thread

__all__ = ("cached_channel", "cached_emoji", "cached_guild", "cached_guild_channel")


def cached_guild(state: ConnectionState, guild_id: int | None) -> Guild | None:
    """Return the cached guild from an in-process cache, ``None`` otherwise."""
    if guild_id is None or not state.cache.supports_sync:
        return None
    return state._guilds.get_nowait(guild_id)


def cached_guild_channel(
    state: ConnectionState, guild_id: int | None, channel_id: int | None
) -> GuildChannel | Thread | None:
    """Return the cached guild channel or thread from an in-process cache, ``None`` otherwise."""
    if guild_id is None or channel_id is None or not state.cache.supports_sync:
        return None
    return state._guild_bucket("channels", guild_id).get_nowait(
        channel_id
    ) or state._guild_bucket("threads", guild_id).get_nowait(channel_id)


def cached_channel(
    state: ConnectionState, channel_id: int | None
) -> MessageableChannel | None:
    """Return the cached channel from an in-process cache, ``None`` otherwise."""
    if channel_id is None or not state.cache.supports_sync:
        return None
    private = state._private_channels.get_nowait(channel_id)
    if private is not None:
        return private  # type: ignore[return-value]
    guild_id = state._channel_guild.get_nowait(channel_id)
    return cached_guild_channel(state, guild_id, channel_id)  # type: ignore[return-value]


def cached_emoji(
    state: ConnectionState, emoji_id: int | None
) -> GuildEmoji | AppEmoji | None:
    """Return the cached emoji from an in-process cache, ``None`` otherwise."""
    if emoji_id is None or not state.cache.supports_sync:
        return None
    return state._emojis.get_nowait(emoji_id) or state._app_emojis.get_nowait(emoji_id)
