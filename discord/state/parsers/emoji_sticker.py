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

"""Emoji and sticker gateway event parsers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ._common import get_guild_or_log

if TYPE_CHECKING:
    from ...cache import CacheBucket
    from ...emoji import GuildEmoji
    from ...sticker import GuildSticker
    from ...types.raw_models import GuildEmojisUpdateEvent, GuildStickersUpdateEvent
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def _evict(
    store: CacheBucket[Any, Any],
    guild_bucket: CacheBucket[Any, Any],
    items: tuple[GuildEmoji | GuildSticker, ...],
) -> None:
    for item in items:
        await store.pop(item.id)
    await guild_bucket.clear()


async def parse_guild_emojis_update(
    state: ConnectionState, data: GuildEmojisUpdateEvent
) -> None:
    """Handle the ``GUILD_EMOJIS_UPDATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_EMOJIS_UPDATE")
    if guild is None:
        return

    before_emojis = tuple(await guild.get_emojis())
    await _evict(
        state._emojis, state._guild_bucket("guild_emojis", guild.id), before_emojis
    )
    after_emojis = tuple([await state.store_emoji(guild, d) for d in data["emojis"]])
    state.dispatch("guild_emojis_update", guild, before_emojis, after_emojis)


async def parse_guild_stickers_update(
    state: ConnectionState, data: GuildStickersUpdateEvent
) -> None:
    """Handle the ``GUILD_STICKERS_UPDATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_STICKERS_UPDATE")
    if guild is None:
        return

    before_stickers = tuple(await guild.get_stickers())
    await _evict(
        state._stickers,
        state._guild_bucket("guild_stickers", guild.id),
        before_stickers,
    )
    after_stickers = tuple(
        [await state.store_sticker(guild, d) for d in data["stickers"]]
    )
    state.dispatch("guild_stickers_update", guild, before_stickers, after_stickers)
