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

"""Thread gateway event parsers."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

from ... import utils
from ...raw_models import (
    RawThreadDeleteEvent,
    RawThreadMembersUpdateEvent,
    RawThreadUpdateEvent,
)
from ...threads import Thread, ThreadMember
from ._common import get_guild_or_log

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ...guild import Guild
    from ...types.raw_models import (
        ThreadDeleteEvent,
        ThreadListSyncEvent,
        ThreadMembersUpdateEvent,
        ThreadMemberUpdateEvent,
        ThreadUpdateEvent,
    )
    from ...types.threads import Thread as ThreadPayload
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def _get_thread_or_log(
    guild: Guild, data: Mapping[str, Any], event: str
) -> Thread | None:
    thread_id = int(data["id"])
    thread = await guild.get_thread(thread_id)
    if thread is None:
        _log.debug(
            "%s referencing an unknown thread ID: %s. Discarding",
            event,
            thread_id,
        )
    return thread


async def parse_thread_create(state: ConnectionState, data: ThreadPayload) -> None:
    """Handle the ``THREAD_CREATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "THREAD_CREATE")
    if guild is None:
        return

    cached_thread = await guild.get_thread(int(data["id"]))
    if not cached_thread:
        thread = Thread(guild=guild, state=guild._state, data=data)
        await guild._add_thread(thread)
        if data.get("newly_created"):
            owner_id = data.get("owner_id")
            created_at = data["thread_metadata"].get("create_timestamp")
            if owner_id is not None and created_at is not None:
                await thread._add_member(
                    ThreadMember(
                        thread,
                        {
                            "id": thread.id,
                            "user_id": owner_id,
                            "join_timestamp": created_at,
                            "flags": utils.MISSING,
                        },
                    )
                )
            state.dispatch("thread_create", thread)
    else:
        state.dispatch("thread_join", cached_thread)


async def parse_thread_update(state: ConnectionState, data: ThreadUpdateEvent) -> None:
    """Handle the ``THREAD_UPDATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "THREAD_UPDATE")
    if guild is None:
        return
    raw = RawThreadUpdateEvent(data)
    thread = await guild.get_thread(raw.thread_id)
    if thread is not None:
        old = copy.copy(thread)
        thread._update(data)
        if thread.archived:
            await guild._remove_thread(thread)
        else:
            await guild._add_thread(thread)
        state.dispatch("thread_update", old, thread)
    else:
        thread = Thread(guild=guild, state=guild._state, data=data)
        if not thread.archived:
            await guild._add_thread(thread)
        state.dispatch("thread_join", thread)
    raw.thread = thread
    state.dispatch("raw_thread_update", raw)


async def parse_thread_delete(state: ConnectionState, data: ThreadDeleteEvent) -> None:
    """Handle the ``THREAD_DELETE`` gateway event."""
    guild_id = int(data["guild_id"])
    guild = await state._get_guild(guild_id)

    if guild is None:
        _log.debug(
            "THREAD_DELETE referencing an unknown guild ID: %s. Discarding",
            guild_id,
        )
        return

    raw = RawThreadDeleteEvent(data)
    thread = await guild.get_thread(raw.thread_id)
    raw.thread = thread

    state.dispatch("raw_thread_delete", raw)

    if thread is not None:
        await guild._remove_thread(thread)
        state.dispatch("thread_delete", thread)

        if (msg := await state._get_message(thread.id)) is not None:
            msg.thread = None
            await state._store_message(msg)


async def parse_thread_list_sync(
    state: ConnectionState, data: ThreadListSyncEvent
) -> None:
    """Handle the ``THREAD_LIST_SYNC`` gateway event."""
    guild = await get_guild_or_log(state, data, "THREAD_LIST_SYNC")
    if guild is None:
        return

    if "channel_ids" in data:
        channel_ids = {int(channel_id) for channel_id in data["channel_ids"]}
        previous_threads = await guild._filter_threads(channel_ids)
    else:
        # If not provided, then the entire guild is being synced
        # So all previous thread data should be overwritten
        previous_threads = {t.id: t for t in await guild.get_threads()}
        await guild._clear_threads()

    threads: dict[int, Thread] = {}
    for d in data.get("threads", []):
        threads[int(d["id"])] = await guild._store_thread(d)

    for member in data.get("members", []):
        # note: member['id'] is the thread_id
        thread_id = member.get("id")
        thread = threads.get(int(thread_id)) if thread_id is not None else None
        if thread is None:
            continue
        await thread._add_member(ThreadMember(thread, member))

    for thread in threads.values():
        old = previous_threads.pop(thread.id, None)
        if old is None:
            state.dispatch("thread_join", thread)

    for thread in previous_threads.values():
        state.dispatch("thread_remove", thread)


async def parse_thread_member_update(
    state: ConnectionState, data: ThreadMemberUpdateEvent
) -> None:
    """Handle the ``THREAD_MEMBER_UPDATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "THREAD_MEMBER_UPDATE")
    if guild is None:
        return

    thread = await _get_thread_or_log(guild, data, "THREAD_MEMBER_UPDATE")
    if thread is None:
        return

    member = ThreadMember(thread, data)
    thread.me = member
    await thread._add_member(member)
    await guild._add_thread(thread)


async def parse_thread_members_update(
    state: ConnectionState, data: ThreadMembersUpdateEvent
) -> None:
    """Handle the ``THREAD_MEMBERS_UPDATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "THREAD_MEMBERS_UPDATE")
    if guild is None:
        return

    thread = await _get_thread_or_log(guild, data, "THREAD_MEMBERS_UPDATE")
    if thread is None:
        return
    raw = RawThreadMembersUpdateEvent(data)

    added_members = [ThreadMember(thread, d) for d in data.get("added_members", [])]
    removed_member_ids = [int(x) for x in data.get("removed_member_ids", [])]
    self_id = state.self_id
    for member in added_members:
        await thread._add_member(member)
        if member.id != self_id:
            state.dispatch("thread_member_join", member)
        else:
            thread.me = member
            await guild._add_thread(thread)
            state.dispatch("thread_join", thread)

    for member_id in removed_member_ids:
        removed_member = await thread._pop_member(member_id)
        if member_id != self_id:
            state.dispatch("raw_thread_member_remove", raw)
            if removed_member is not None:
                state.dispatch("thread_member_remove", removed_member)
        else:
            thread.me = None
            await guild._add_thread(thread)
            state.dispatch("thread_remove", thread)
