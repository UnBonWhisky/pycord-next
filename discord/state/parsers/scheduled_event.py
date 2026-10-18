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

"""Guild scheduled event gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ... import utils
from ...enums import ScheduledEventStatus
from ...raw_models import RawScheduledEventSubscription
from ...scheduled_events import ScheduledEvent
from ._common import get_guild_or_log

if TYPE_CHECKING:
    from ...guild import Guild
    from ...types.raw_models import ScheduledEventSubscription
    from ...types.scheduled_events import ScheduledEvent as ScheduledEventPayload
    from ..state import ConnectionState


async def _build_event(
    state: ConnectionState, guild: Guild, data: ScheduledEventPayload
) -> ScheduledEvent:
    creator_id = utils._get_as_snowflake(data, "creator_id")
    creator = (
        None
        if not data.get("creator", None) or creator_id is None
        else await guild.get_member(creator_id)
    )
    return ScheduledEvent(state=state, guild=guild, creator=creator, data=data)


async def _update_subscription(
    state: ConnectionState,
    data: ScheduledEventSubscription,
    event_type: str,
    delta: int,
) -> None:
    name = event_type.lower()
    guild = await get_guild_or_log(state, data, f"GUILD_SCHEDULED_EVENT_{event_type}")
    if guild is None:
        return

    payload = RawScheduledEventSubscription(data, event_type)
    payload.guild = guild
    state.dispatch(f"raw_scheduled_event_{name}", payload)

    event = await guild.get_scheduled_event(int(data["guild_scheduled_event_id"]))
    if event is None:
        return

    user_id = int(data["user_id"])
    if delta > 0:
        event._subscriber_ids.add(user_id)
    else:
        event._subscriber_ids.discard(user_id)
    if event.subscriber_count is not None:
        event.subscriber_count = max(event.subscriber_count + delta, 0)
    await guild._add_scheduled_event(event)

    member = await guild.get_member(user_id)
    if member is not None:
        state.dispatch(f"scheduled_event_{name}", event, member)


async def parse_guild_scheduled_event_create(
    state: ConnectionState, data: ScheduledEventPayload
) -> None:
    """Handle the ``GUILD_SCHEDULED_EVENT_CREATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_SCHEDULED_EVENT_CREATE")
    if guild is None:
        return

    scheduled_event = await _build_event(state, guild, data)
    await guild._add_scheduled_event(scheduled_event)
    state.dispatch("scheduled_event_create", scheduled_event)


async def parse_guild_scheduled_event_update(
    state: ConnectionState, data: ScheduledEventPayload
) -> None:
    """Handle the ``GUILD_SCHEDULED_EVENT_UPDATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_SCHEDULED_EVENT_UPDATE")
    if guild is None:
        return

    scheduled_event = await _build_event(state, guild, data)
    old_event = await guild.get_scheduled_event(int(data["id"]))
    if old_event is not None and scheduled_event.subscriber_count is None:
        scheduled_event.subscriber_count = old_event.subscriber_count
    if old_event is not None:
        scheduled_event._subscriber_ids = old_event._subscriber_ids
    await guild._add_scheduled_event(scheduled_event)
    state.dispatch("scheduled_event_update", old_event, scheduled_event)


async def parse_guild_scheduled_event_delete(
    state: ConnectionState, data: ScheduledEventPayload
) -> None:
    """Handle the ``GUILD_SCHEDULED_EVENT_DELETE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_SCHEDULED_EVENT_DELETE")
    if guild is None:
        return

    scheduled_event = await _build_event(state, guild, data)
    cached_event = await guild.get_scheduled_event(int(data["id"]))
    if cached_event is not None and scheduled_event.subscriber_count is None:
        scheduled_event.subscriber_count = cached_event.subscriber_count
    if cached_event is not None:
        scheduled_event._subscriber_ids = cached_event._subscriber_ids
    scheduled_event.status = ScheduledEventStatus.canceled
    await guild._remove_scheduled_event(scheduled_event)
    state.dispatch("scheduled_event_delete", scheduled_event)


async def parse_guild_scheduled_event_user_add(
    state: ConnectionState, data: ScheduledEventSubscription
) -> None:
    """Handle the ``GUILD_SCHEDULED_EVENT_USER_ADD`` gateway event."""
    await _update_subscription(state, data, "USER_ADD", 1)


async def parse_guild_scheduled_event_user_remove(
    state: ConnectionState, data: ScheduledEventSubscription
) -> None:
    """Handle the ``GUILD_SCHEDULED_EVENT_USER_REMOVE`` gateway event."""
    await _update_subscription(state, data, "USER_REMOVE", -1)
