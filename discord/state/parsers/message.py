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

"""Message gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...channel import StageChannel, TextChannel, VoiceChannel
from ...message import Message
from ...raw_models import (
    RawBulkMessageDeleteEvent,
    RawMessageDeleteEvent,
    RawMessageUpdateEvent,
)
from ...threads import Thread

if TYPE_CHECKING:
    from ...types.message import Message as MessagePayload
    from ...types.raw_models import BulkMessageDeleteEvent, MessageDeleteEvent
    from ..state import ConnectionState


async def parse_message_create(state: ConnectionState, data: MessagePayload) -> None:
    """Handle the ``MESSAGE_CREATE`` gateway event."""
    channel, _ = await state._get_guild_channel(data)
    message = Message(channel=channel, data=data, state=state)
    await state._populate_message(message, data)
    state.dispatch("message", message)
    await state._store_message(message)
    # we ensure that the channel is either a TextChannel, VoiceChannel, StageChannel, or Thread
    if isinstance(channel, (TextChannel, VoiceChannel, StageChannel, Thread)) and (
        channel.__class__ in (TextChannel, VoiceChannel, StageChannel, Thread)
    ):
        channel.last_message_id = message.id
        if isinstance(channel, Thread):
            await state._add_thread(channel.guild_id, channel)
        else:
            await state._add_channel(channel.guild_id, channel)


async def parse_message_delete(
    state: ConnectionState, data: MessageDeleteEvent
) -> None:
    """Handle the ``MESSAGE_DELETE`` gateway event."""
    raw = RawMessageDeleteEvent(data)
    found = await state._get_message(raw.message_id)
    raw.cached_message = found
    state.dispatch("raw_message_delete", raw)
    if state._messages is not None and found is not None:
        state.dispatch("message_delete", found)
        await state._remove_message(found.id)


async def parse_message_delete_bulk(
    state: ConnectionState, data: BulkMessageDeleteEvent
) -> None:
    """Handle the ``MESSAGE_DELETE_BULK`` gateway event."""
    raw = RawBulkMessageDeleteEvent(data)
    if state._messages is not None:
        found_messages = sorted(
            (await state._messages.get_many(raw.message_ids)).values(),
            key=lambda message: message.id,
        )
    else:
        found_messages = []
    raw.cached_messages = found_messages
    state.dispatch("raw_bulk_message_delete", raw)
    if found_messages:
        state.dispatch("bulk_message_delete", found_messages)
        for msg in found_messages:
            await state._remove_message(msg.id)


async def parse_message_update(state: ConnectionState, data: MessagePayload) -> None:
    """Handle the ``MESSAGE_UPDATE`` gateway event."""
    old_message = await state._get_message(int(data["id"]))
    channel, _ = await state._get_guild_channel(data)
    message = Message(channel=channel, data=data, state=state)
    await state._populate_message(message, data)
    if state._messages is not None:
        if old_message is not None:
            await state._remove_message(old_message.id)
        await state._store_message(message)
    raw = RawMessageUpdateEvent(data, message)
    if old_message is not None:
        raw.cached_message = old_message
    state.dispatch("raw_message_edit", raw)
    if old_message is not None:
        state.dispatch("message_edit", old_message, message)
    elif poll_data := data.get("poll"):
        await state.store_raw_poll(poll_data, raw)

    if "components" in data and state._view_store.is_message_tracked(raw.message_id):
        state._view_store.update_from_message(raw.message_id, data["components"])
