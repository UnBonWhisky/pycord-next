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

"""Message reaction gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ... import utils
from ...partial_emoji import PartialEmoji
from ...raw_models import (
    RawReactionActionEvent,
    RawReactionClearEmojiEvent,
    RawReactionClearEvent,
)
from ._common import get_raw_member

if TYPE_CHECKING:
    from ...types.raw_models import (
        ReactionActionEvent,
        ReactionClearEmojiEvent,
        ReactionClearEvent,
    )
    from ..state import ConnectionState


async def parse_message_reaction_add(
    state: ConnectionState, data: ReactionActionEvent
) -> None:
    """Handle the ``MESSAGE_REACTION_ADD`` gateway event."""
    emoji_data = data["emoji"]
    emoji_id = utils._get_as_snowflake(emoji_data, "id")
    emoji = PartialEmoji.with_state(
        state,
        id=emoji_id,
        animated=emoji_data.get("animated", False),
        name=emoji_data["name"],
    )
    raw = RawReactionActionEvent(data, emoji, "REACTION_ADD")

    raw.member = await get_raw_member(state, data, raw.guild_id)
    state.dispatch("raw_reaction_add", raw)

    # rich interface here
    message = await state._get_message(raw.message_id)
    if message is not None:
        upgraded = await state._upgrade_partial_emoji(emoji)
        reaction = message._add_reaction(data, upgraded, raw.user_id)
        await state._store_message(message)
        user = raw.member or await state._get_reaction_user(
            await message.get_channel(), raw.user_id
        )

        if user:
            state.dispatch("reaction_add", reaction, user)


async def parse_message_reaction_remove_all(
    state: ConnectionState, data: ReactionClearEvent
) -> None:
    """Handle the ``MESSAGE_REACTION_REMOVE_ALL`` gateway event."""
    raw = RawReactionClearEvent(data)
    state.dispatch("raw_reaction_clear", raw)

    message = await state._get_message(raw.message_id)
    if message is not None:
        old_reactions = message.reactions.copy()
        message.reactions.clear()
        await state._store_message(message)
        state.dispatch("reaction_clear", message, old_reactions)


async def parse_message_reaction_remove(
    state: ConnectionState, data: ReactionActionEvent
) -> None:
    """Handle the ``MESSAGE_REACTION_REMOVE`` gateway event."""
    emoji_data = data["emoji"]
    emoji_id = utils._get_as_snowflake(emoji_data, "id")
    emoji = PartialEmoji.with_state(state, id=emoji_id, name=emoji_data["name"])
    raw = RawReactionActionEvent(data, emoji, "REACTION_REMOVE")

    raw.member = await get_raw_member(state, data, raw.guild_id)

    state.dispatch("raw_reaction_remove", raw)

    message = await state._get_message(raw.message_id)
    if message is not None:
        upgraded = await state._upgrade_partial_emoji(emoji)
        try:
            reaction = message._remove_reaction(data, upgraded, raw.user_id)
        except (AttributeError, ValueError):  # eventual consistency lol
            pass
        else:
            await state._store_message(message)
            user = await state._get_reaction_user(
                await message.get_channel(), raw.user_id
            )
            if user:
                state.dispatch("reaction_remove", reaction, user)


async def parse_message_reaction_remove_emoji(
    state: ConnectionState, data: ReactionClearEmojiEvent
) -> None:
    """Handle the ``MESSAGE_REACTION_REMOVE_EMOJI`` gateway event."""
    emoji_data = data["emoji"]
    emoji_id = utils._get_as_snowflake(emoji_data, "id")
    emoji = PartialEmoji.with_state(state, id=emoji_id, name=emoji_data["name"])
    raw = RawReactionClearEmojiEvent(data, emoji)
    state.dispatch("raw_reaction_clear_emoji", raw)

    message = await state._get_message(raw.message_id)
    if message is not None:
        try:
            reaction = message._clear_emoji(emoji)
        except (AttributeError, ValueError):  # eventual consistency lol
            pass
        else:
            await state._store_message(message)
            if reaction:
                state.dispatch("reaction_clear_emoji", reaction)
