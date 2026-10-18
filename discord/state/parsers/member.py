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

"""Guild member gateway event parsers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from ...guild import PartialGuild
from ...member import Member
from ...raw_models import RawMemberRemoveEvent, RawMemberUpdateEvent
from ._common import get_guild_or_log

if TYPE_CHECKING:
    from ...types.member import MemberUpdateEvent
    from ...types.raw_models import (
        GuildMemberAddEvent,
        GuildMembersChunkEvent,
        MemberRemoveEvent,
    )
    from ...types.user import User as UserPayload
    from ..state import ConnectionState

_log = logging.getLogger(__name__)


async def parse_guild_member_add(
    state: ConnectionState, data: GuildMemberAddEvent
) -> None:
    """Handle the ``GUILD_MEMBER_ADD`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_MEMBER_ADD")
    if guild is None:
        return

    member = Member(guild=guild, data=data, state=state)
    if state._cache_users:
        await state.store_user(data["user"])
    if state.member_cache_flags.joined:
        await guild._add_member(member)

    if guild._member_count is not None:
        guild._member_count += 1
        await state._add_guild(guild)

    state.dispatch("member_join", member)


async def parse_guild_member_remove(
    state: ConnectionState, data: MemberRemoveEvent
) -> None:
    """Handle the ``GUILD_MEMBER_REMOVE`` gateway event."""
    user = await state.store_user(data["user"])
    raw = RawMemberRemoveEvent(data, user)

    guild = await state._get_guild(int(data["guild_id"]))
    if guild is not None:
        if guild._member_count is not None:
            guild._member_count -= 1
            await state._add_guild(guild)

        member = await guild.get_member(user.id)
        if member is not None:
            raw.user = member
            await guild._remove_member(member)
            state.dispatch("member_remove", member)
    else:
        _log.debug(
            "GUILD_MEMBER_REMOVE referencing an unknown guild ID: %s. Discarding.",
            data["guild_id"],
        )
    state.dispatch("raw_member_remove", raw)


async def parse_guild_member_update(
    state: ConnectionState, data: MemberUpdateEvent
) -> None:
    """Handle the ``GUILD_MEMBER_UPDATE`` gateway event."""
    guild = await get_guild_or_log(state, data, "GUILD_MEMBER_UPDATE")
    if guild is None:
        return

    user = data["user"]
    user_id = int(user["id"])

    # Try to get the old member from cache
    old_member: Member | None = await guild.get_member(user_id)
    old_member_copy: Member | None = (
        Member._copy(old_member) if old_member is not None else None
    )

    # Always create or update the member object
    if old_member is not None:
        old_member._update(data)
        new_member: Member = old_member
    else:
        new_member = Member(guild=guild, data=data, state=state)

    raw = RawMemberUpdateEvent(data, new_member)
    raw.cached_member = old_member_copy
    state.dispatch("raw_member_update", raw)

    # Update the user cache if needed
    user_update = None
    if old_member_copy is not None:
        user_update = old_member_copy._update_inner_user(user)
    else:
        user_update = new_member._update_inner_user(user)

    if user_update:
        state.dispatch("user_update", user_update[0], user_update[1])

    if old_member_copy is not None:
        await guild._add_member(new_member)
        state.dispatch("member_update", old_member_copy, new_member)
    elif state.member_cache_flags.joined:
        await guild._add_member(new_member)


async def parse_guild_members_chunk(
    state: ConnectionState, data: GuildMembersChunkEvent
) -> None:
    """Handle the ``GUILD_MEMBERS_CHUNK`` gateway event."""
    guild_id = int(data["guild_id"])
    guild = PartialGuild(state=state, id=guild_id)
    presences = data.get("presences", [])

    members = [
        Member(guild=guild, data=member, state=state)
        for member in data.get("members", [])
    ]
    if state._cache_users:
        for member in data.get("members", []):
            await state.store_user(member["user"])
    _log.debug(
        "Processed a chunk for %s members in guild ID %s.", len(members), guild_id
    )

    if presences:
        member_dict = {str(member.id): member for member in members}
        for presence in presences:
            presence_user = presence["user"]
            presence_member = member_dict.get(str(presence_user["id"]))
            if presence_member is not None:
                presence_member._presence_update(
                    presence, cast("UserPayload", presence_user)
                )

    complete = data.get("chunk_index", 0) + 1 == data.get("chunk_count")
    await state.process_chunk_requests(guild_id, data.get("nonce"), members, complete)
